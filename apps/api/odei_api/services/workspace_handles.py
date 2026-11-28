"""In-memory registry for explicitly selected local workspace handles.

This local-process primitive is not an HTTP authorization system. The loopback
companion registers only user-selected roots, binds opaque IDs to paired
sessions, and revokes grants on disconnect, expiry or user request. Read and
write operations remain relative to retained native root handles.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import secrets
import stat
import threading
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from odei_api.services.project_files import (
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_TOTAL_BYTES,
    MAX_TEXT_FILE_BYTES,
    ProjectFile,
    list_project_files_from_posix_fd,
    list_project_files_from_windows_handle,
    read_project_text_file_from_posix_fd,
    read_project_text_file_from_windows_handle,
)
from odei_api.services.workspace_transaction_journal import workspace_root_key


class WorkspaceHandleError(RuntimeError):
    """Base error for selected workspace handle operations."""


class WorkspaceNotFound(WorkspaceHandleError):
    """The workspace handle is unknown or has been revoked."""


@dataclass
class _WorkspaceGrant:
    platform: str
    handle: object
    label: str
    kernel32: object | None = None
    allow_patch_apply: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock)
    search_cache: OrderedDict[str, tuple[str, tuple[str, ...], int]] = field(default_factory=OrderedDict)
    search_cache_bytes: int = 0
    root_key: str = ""


class WorkspaceHandleRegistry:
    """Own and revoke native handles for explicitly selected workspace roots."""

    def __init__(self, journal: Any | None = None) -> None:
        self._lock = threading.RLock()
        self._grants: dict[str, _WorkspaceGrant] = {}
        self._journal = journal

    def register_selected_root(
        self, selected_path: str | Path, *, allow_patch_apply: bool = False
    ) -> str:
        """Open a user-selected root once and retain its native handle.

        Call only from a trusted native folder-picker flow. Never pass a raw
        absolute path supplied by a remote browser request to this method.
        """
        label = Path(selected_path).name or "Selected folder"
        if allow_patch_apply and self._journal is None:
            raise WorkspaceHandleError(
                "A durable workspace journal is required for approved patch application"
            )
        if os.name == "nt":
            from odei_api.services.windows_file_handles import open_directory_handle

            try:
                kernel32, handle = open_directory_handle(
                    selected_path, allow_patch_apply=allow_patch_apply
                )
                granted_write = allow_patch_apply
            except OSError:
                if not allow_patch_apply:
                    raise
                kernel32, handle = open_directory_handle(
                    selected_path, allow_patch_apply=False
                )
                granted_write = False
            grant = _WorkspaceGrant(
                platform="nt", handle=handle, label=label,
                kernel32=kernel32, allow_patch_apply=granted_write,
            )
        elif os.name == "posix":
            flags = (
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            handle = os.open(Path(selected_path).expanduser(), flags)
            try:
                if not stat.S_ISDIR(os.fstat(handle).st_mode):
                    raise WorkspaceHandleError("Selected root is not a directory")
            except Exception:
                os.close(handle)
                raise
            granted_write = allow_patch_apply and os.access(
                Path(selected_path).expanduser(), os.W_OK | os.X_OK
            )
            grant = _WorkspaceGrant(
                platform="posix", handle=handle, label=label,
                allow_patch_apply=granted_write,
            )
        else:
            raise WorkspaceHandleError("This platform has no supported workspace handle")

        try:
            if grant.platform == "posix":
                root_stat = os.fstat(int(grant.handle))
                identity = f"posix:{root_stat.st_dev}:{root_stat.st_ino}"
            else:
                class _FileIdInfo(ctypes.Structure):
                    _fields_ = [
                        ("VolumeSerialNumber", ctypes.c_ulonglong),
                        ("FileId", ctypes.c_ubyte * 16),
                    ]
                info = _FileIdInfo()
                if not grant.kernel32.GetFileInformationByHandleEx(
                    grant.handle, 18, ctypes.byref(info), ctypes.sizeof(info)
                ):
                    raise OSError(ctypes.get_last_error(), "Could not identify selected workspace root")
                identity = (
                    f"windows:{info.VolumeSerialNumber}:"
                    + bytes(info.FileId).hex()
                )
            grant.root_key = workspace_root_key(selected_path, identity)
            if self._journal is not None:
                from odei_api.services.workspace_patch_apply import (
                    recover_pending_patch_transactions,
                )
                recover_pending_patch_transactions(grant, self._journal, grant.root_key)
        except Exception:
            if grant.platform == "nt":
                from odei_api.services.windows_file_handles import close_directory_handle
                close_directory_handle(grant.kernel32, grant.handle)
            else:
                os.close(int(grant.handle))
            raise

        workspace_id = secrets.token_urlsafe(32)
        with self._lock:
            self._grants[workspace_id] = grant
        return workspace_id

    @contextmanager
    def _borrow(self, workspace_id: str) -> Iterator[_WorkspaceGrant]:
        with self._lock:
            grant = self._grants.get(workspace_id)
            if grant is None:
                raise WorkspaceNotFound("Workspace is unknown or has been revoked")
            grant.lock.acquire()
        try:
            yield grant
        finally:
            grant.lock.release()

    def display_name(self, workspace_id: str) -> str:
        """Return only the selected folder basename, never its full path."""
        with self._borrow(workspace_id) as grant:
            return grant.label

    def list_files(
        self,
        workspace_id: str,
        *,
        max_files: int = DEFAULT_MAX_FILES,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    ) -> list[ProjectFile]:
        with self._borrow(workspace_id) as grant:
            if grant.platform == "nt":
                return list_project_files_from_windows_handle(
                    grant.handle, kernel32=grant.kernel32,
                    max_files=max_files, max_total_bytes=max_total_bytes
                )
            return list_project_files_from_posix_fd(
                int(grant.handle), max_files=max_files, max_total_bytes=max_total_bytes
            )

    def read_text(
        self,
        workspace_id: str,
        relative_path: str,
        *,
        max_bytes: int = MAX_TEXT_FILE_BYTES,
    ) -> str:
        with self._borrow(workspace_id) as grant:
            if grant.platform == "nt":
                return read_project_text_file_from_windows_handle(
                    grant.handle, relative_path, max_bytes=max_bytes
                )
            return read_project_text_file_from_posix_fd(
                int(grant.handle), relative_path, max_bytes=max_bytes
            )


    def search_text(
        self, workspace_id: str, query: str, *, limit: int = 50
    ) -> dict[str, Any]:
        """Search eligible UTF-8 files with strict scan budgets and redacted snippets."""
        from odei_api.services.secret_redaction import redact_secrets

        max_query_chars = 200
        max_results = 50
        max_files = 1_000
        max_total_bytes = 20_000_000
        max_file_bytes = 128_000
        if (
            not isinstance(query, str) or not query.strip()
            or len(query) > max_query_chars or "\x00" in query
        ):
            raise ValueError("Search query must contain 1–200 non-NUL characters")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= max_results:
            raise ValueError("Search result limit must be between 1 and 50")

        needle = query.strip().casefold()
        matches: list[dict[str, str | int]] = []
        files_scanned = 0
        bytes_scanned = 0
        skipped_files = 0
        truncated = False
        with self._borrow(workspace_id) as grant:
            if grant.platform == "nt":
                files = list_project_files_from_windows_handle(
                    grant.handle, kernel32=grant.kernel32,
                    max_files=max_files + 1, max_total_bytes=DEFAULT_MAX_TOTAL_BYTES,
                )
            else:
                files = list_project_files_from_posix_fd(
                    int(grant.handle), max_files=max_files + 1,
                    max_total_bytes=DEFAULT_MAX_TOTAL_BYTES,
                )
            if len(files) > max_files:
                truncated = True
            files = files[:max_files]
            seen_paths = {item.path for item in files}

            for item in files:
                if len(matches) >= limit:
                    truncated = True
                    break
                if item.size > max_file_bytes:
                    skipped_files += 1
                    stale = grant.search_cache.pop(item.path, None)
                    if stale is not None:
                        grant.search_cache_bytes -= stale[2]
                    continue
                if bytes_scanned + item.size > max_total_bytes:
                    truncated = True
                    break
                try:
                    if grant.platform == "nt":
                        content = read_project_text_file_from_windows_handle(
                            grant.handle, item.path, max_bytes=max_file_bytes
                        )
                    else:
                        content = read_project_text_file_from_posix_fd(
                            int(grant.handle), item.path, max_bytes=max_file_bytes
                        )
                except (ValueError, OSError, UnicodeError):
                    skipped_files += 1
                    stale = grant.search_cache.pop(item.path, None)
                    if stale is not None:
                        grant.search_cache_bytes -= stale[2]
                    continue

                encoded = content.encode("utf-8")
                if len(encoded) > max_file_bytes:
                    skipped_files += 1
                    continue
                if bytes_scanned + len(encoded) > max_total_bytes:
                    truncated = True
                    break
                files_scanned += 1
                bytes_scanned += len(encoded)
                digest = hashlib.sha256(encoded).hexdigest()
                cached = grant.search_cache.pop(item.path, None)
                if cached is not None and cached[0] == digest:
                    lines = cached[1]
                    grant.search_cache[item.path] = cached
                else:
                    if cached is not None:
                        grant.search_cache_bytes -= cached[2]
                    lines = tuple(content.splitlines())
                    cache_size = len(encoded)
                    if cache_size <= 256 * 1024:
                        grant.search_cache[item.path] = (digest, lines, cache_size)
                        grant.search_cache_bytes += cache_size
                        while grant.search_cache_bytes > 8 * 1024 * 1024:
                            _old_path, old_entry = grant.search_cache.popitem(last=False)
                            grant.search_cache_bytes -= old_entry[2]

                for line_number, line in enumerate(lines, start=1):
                    if needle not in line.casefold():
                        continue
                    if len(matches) >= limit:
                        truncated = True
                        break
                    matches.append({
                        "path": item.path,
                        "line": line_number,
                        "snippet": redact_secrets(line)[:500],
                        "content_sha256": digest,
                        "index_version": "literal-search-v2",
                    })
                if truncated:
                    break

            for cached_path in tuple(grant.search_cache):
                if cached_path not in seen_paths:
                    removed = grant.search_cache.pop(cached_path)
                    grant.search_cache_bytes -= removed[2]

        return {
            "matches": matches,
            "scanned_files": files_scanned,
            "bytes_scanned": bytes_scanned,
            "skipped_files": skipped_files,
            "truncated": truncated,
            "index_version": "literal-search-v2",
        }

    def can_apply_patch(self, workspace_id: str) -> bool:
        """Report whether the selected root was opened with patch-write rights."""
        with self._borrow(workspace_id) as grant:
            return grant.allow_patch_apply

    def transaction_receipt(
        self, workspace_id: str, transaction_id: str
    ) -> dict[str, Any] | None:
        """Read a durable transaction receipt scoped to the selected workspace."""
        with self._borrow(workspace_id) as grant:
            if self._journal is None:
                return None
            return self._journal.receipt(grant.root_key, transaction_id)

    def apply_patch(self, workspace_id: str, file: dict) -> dict[str, str | bool]:
        """Apply one signed, pre-authorized file operation beneath its held root."""
        from odei_api.services.workspace_patch_apply import apply_single_file_patch

        with self._borrow(workspace_id) as grant:
            if not grant.allow_patch_apply:
                raise WorkspaceHandleError("Workspace was opened read-only")
            return apply_single_file_patch(grant, file)

    def apply_patch_batch(self, workspace_id: str, files: list[dict]) -> dict:
        """Apply a signed multi-file batch under one workspace lock.

        Individual filesystem operations are atomic; a later failure triggers
        reverse-order, hash-guarded compensation before this lock is released.
        """
        from odei_api.services.workspace_patch_apply import apply_file_patch_batch

        with self._borrow(workspace_id) as grant:
            if not grant.allow_patch_apply:
                raise WorkspaceHandleError("Workspace was opened read-only")
            return apply_file_patch_batch(
                grant, files, journal=self._journal, root_key=grant.root_key
            )

    def revoke(self, workspace_id: str) -> bool:
        with self._lock:
            grant = self._grants.pop(workspace_id, None)
            if grant is None:
                return False
            grant.lock.acquire()
        try:
            if grant.platform == "nt":
                from odei_api.services.windows_file_handles import close_directory_handle

                close_directory_handle(grant.kernel32, grant.handle)
            else:
                os.close(int(grant.handle))
            return True
        finally:
            grant.lock.release()

    def close(self) -> None:
        with self._lock:
            workspace_ids = list(self._grants)
        for workspace_id in workspace_ids:
            self.revoke(workspace_id)
