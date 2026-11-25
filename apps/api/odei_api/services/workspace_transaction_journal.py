"""Durable, crash-recoverable journal for approved workspace patch batches.

The journal stores bounded before-images only in a private local state directory.
It never resolves workspace paths or performs filesystem writes itself; callers
must recover through the retained native workspace handle and hash-guarded patch
primitive. A pending record is durable before the first workspace mutation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import time
from contextlib import closing
from pathlib import Path
from typing import Any

MAX_FILES = 20
MAX_TOTAL_BYTES = 5 * 1024 * 1024
_SCHEMA = """
CREATE TABLE IF NOT EXISTS patch_transactions (
    transaction_id TEXT PRIMARY KEY,
    root_key TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'committed', 'recovered', 'conflict')),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    payload_json TEXT NOT NULL,
    receipt_json TEXT
);
CREATE INDEX IF NOT EXISTS patch_transactions_root_state
    ON patch_transactions(root_key, state, created_at);
"""


class WorkspaceJournalError(RuntimeError):
    """The durable workspace journal is unavailable or inconsistent."""


class WorkspaceJournalConflict(WorkspaceJournalError):
    """A pending transaction cannot be safely recovered without overwriting edits."""


def default_journal_path() -> Path:
    """Return the per-user companion state path without creating it."""
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if not base:
            raise WorkspaceJournalError("A per-user application data directory is unavailable")
        return Path(base) / "ODEI" / "companion" / "workspace-journal.sqlite3"
    base = os.getenv("XDG_STATE_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".local" / "state"
    return root / "odei" / "companion" / "workspace-journal.sqlite3"


def workspace_root_key(selected_path: str | os.PathLike[str], identity: str) -> str:
    """Hash a canonical selected-root locator and native identity; never persist its path."""
    if not isinstance(identity, str) or not identity or len(identity) > 512:
        raise ValueError("A bounded native workspace identity is required")
    canonical = os.path.normcase(os.path.abspath(os.path.expanduser(os.fspath(selected_path))))
    material = (os.name + "\\0" + canonical + "\\0" + identity).encode("utf-8", "strict")
    return hashlib.sha256(material).hexdigest()


class DurableWorkspaceJournal:
    """SQLite-backed write-ahead journal with FULL synchronous durability."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser()
        self._prepare_parent()
        self._initialize()

    def _prepare_parent(self) -> None:
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            metadata = os.lstat(parent)
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise WorkspaceJournalError("Journal state directory is not a safe directory")
            os.chmod(parent, 0o700)
        if self.path.is_symlink():
            raise WorkspaceJournalError("Journal database must not be a symbolic link")

    def _connect(self) -> sqlite3.Connection:
        if self.path.is_symlink():
            raise WorkspaceJournalError("Journal database must not be a symbolic link")
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        if os.name != "nt":
            os.chmod(self.path, 0o600)
        return connection

    def _initialize(self) -> None:
        try:
            with closing(self._connect()) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(_SCHEMA)
        except (OSError, sqlite3.Error) as exc:
            raise WorkspaceJournalError("Could not initialize the durable workspace journal") from exc

    @staticmethod
    def _validate_payload(files: list[dict[str, Any]], before_images: list[str | None]) -> str:
        """Validate the complete write-ahead manifest before persisting any source text."""
        if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
            raise ValueError("A journal transaction must contain between 1 and 20 files")
        if not isinstance(before_images, list) or len(files) != len(before_images):
            raise ValueError("Every journaled file must have exactly one before-image")
        from odei_api.services.patch_proposals import validate_patch_path

        aggregate_bytes = 0
        normalized = []
        seen_paths: set[str] = set()
        for item, before in zip(files, before_images, strict=True):
            if not isinstance(item, dict) or set(item) != {
                "path", "operation", "base_sha256", "result_sha256", "content",
            }:
                raise ValueError("Journal patch fields are invalid")
            if not isinstance(item["path"], str) or len(item["path"]) > 1024:
                raise ValueError("Journal patch path is invalid")
            try:
                validate_patch_path(item["path"])
            except (TypeError, ValueError) as exc:
                raise ValueError("Journal patch path is invalid") from exc
            path_key = item["path"].casefold()
            if path_key in seen_paths:
                raise ValueError("Journal transaction contains duplicate paths")
            seen_paths.add(path_key)

            operation = item["operation"]
            base_hash = item["base_sha256"]
            result_hash = item["result_sha256"]
            content = item["content"]
            if before is not None and not isinstance(before, str):
                raise ValueError("Journal before-image must be UTF-8 text or null")
            if content is not None and not isinstance(content, str):
                raise ValueError("Journal patch content must be UTF-8 text or null")
            for value in (before, content):
                if value is not None:
                    try:
                        encoded = value.encode("utf-8", errors="strict")
                    except UnicodeEncodeError as exc:
                        raise ValueError("Journal content must be valid UTF-8") from exc
                    if "\\x00" in value or len(encoded) > 1_048_576:
                        raise ValueError("Journal content is binary or exceeds the per-file limit")
                    aggregate_bytes += len(encoded)

            valid_hash = lambda value: isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)
            before_hash = hashlib.sha256(before.encode("utf-8")).hexdigest() if before is not None else None
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest() if content is not None else None
            if operation == "create":
                valid = before is None and base_hash is None and content is not None and result_hash == content_hash
            elif operation == "update":
                valid = (
                    before is not None and valid_hash(base_hash) and base_hash == before_hash
                    and content is not None and valid_hash(result_hash) and result_hash == content_hash
                )
            elif operation == "delete":
                valid = (
                    before is not None and valid_hash(base_hash) and base_hash == before_hash
                    and content is None and result_hash is None
                )
            else:
                valid = False
            if not valid:
                raise ValueError("Journal patch operation or content hashes are inconsistent")
            normalized.append({"patch": item, "before": before})

        if aggregate_bytes > MAX_TOTAL_BYTES:
            raise ValueError("Journal transaction exceeds the aggregate before-image and patch limit")
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))

    def prepare(
        self, root_key: str, files: list[dict[str, Any]], before_images: list[str | None]
    ) -> str:
        """Commit the complete write-ahead record before any target file is changed."""
        if not isinstance(root_key, str) or len(root_key) != 64:
            raise ValueError("Workspace root key is invalid")
        payload = self._validate_payload(files, before_images)
        transaction_id = secrets.token_urlsafe(24)
        now = time.time()
        try:
            with closing(self._connect()) as connection:
                connection.execute(
                    "INSERT INTO patch_transactions "
                    "(transaction_id, root_key, state, created_at, updated_at, payload_json) "
                    "VALUES (?, ?, 'pending', ?, ?, ?)",
                    (transaction_id, root_key, now, now, payload),
                )
        except sqlite3.Error as exc:
            raise WorkspaceJournalError("Could not durably prepare workspace transaction") from exc
        return transaction_id

    def finish(self, transaction_id: str, *, state: str, receipt: dict[str, Any]) -> None:
        """Persist a terminal transaction state and compact away source before-images."""
        if state not in {"committed", "recovered", "conflict"}:
            raise ValueError("Journal terminal state is invalid")
        receipt_json = json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))
        if len(receipt_json.encode("utf-8")) > 64 * 1024:
            raise ValueError("Transaction receipt exceeds its size limit")
        try:
            with closing(self._connect()) as connection:
                cursor = connection.execute(
                    "UPDATE patch_transactions SET state=?, updated_at=?, "
                    "payload_json=CASE WHEN ?='conflict' THEN payload_json ELSE '[]' END, "
                    "receipt_json=? WHERE transaction_id=? AND state IN ('pending', 'conflict')",
                    (state, time.time(), state, receipt_json, transaction_id),
                )
                if cursor.rowcount != 1:
                    raise WorkspaceJournalError("Pending transaction was not found")
        except sqlite3.Error as exc:
            raise WorkspaceJournalError("Could not finalize workspace transaction") from exc

    def pending(self, root_key: str) -> list[dict[str, Any]]:
        """Return verified pending records for one exact selected workspace identity."""
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT transaction_id, payload_json FROM patch_transactions "
                    "WHERE root_key=? AND state IN ('pending', 'conflict') ORDER BY created_at",
                    (root_key,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise WorkspaceJournalError("Could not read pending workspace transactions") from exc
        results = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
                if not isinstance(payload, list) or not 1 <= len(payload) <= MAX_FILES:
                    raise ValueError("invalid payload")
                for entry in payload:
                    if not isinstance(entry, dict) or set(entry) != {"patch", "before"}:
                        raise ValueError("invalid entry")
                results.append({"transaction_id": row["transaction_id"], "files": payload})
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise WorkspaceJournalError("Pending workspace journal record is corrupt") from exc
        return results

    def receipt(self, root_key: str, transaction_id: str) -> dict[str, Any] | None:
        """Read one transaction receipt only within the matching selected root."""
        if not isinstance(transaction_id, str) or not 1 <= len(transaction_id) <= 128:
            raise ValueError("Transaction ID is invalid")
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT state, receipt_json FROM patch_transactions "
                    "WHERE root_key=? AND transaction_id=?",
                    (root_key, transaction_id),
                ).fetchone()
        except sqlite3.Error as exc:
            raise WorkspaceJournalError("Could not read workspace transaction receipt") from exc
        if row is None:
            return None
        receipt = json.loads(row["receipt_json"]) if row["receipt_json"] else None
        return {"transaction_id": transaction_id, "state": row["state"], "receipt": receipt}

    def close(self) -> None:
        """Connections are short-lived; provided for lifecycle symmetry."""

