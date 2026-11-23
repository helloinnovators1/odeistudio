"""In-memory registry for explicitly selected local workspace handles.

This local-process primitive is not an HTTP authorization system. The loopback
companion registers only user-selected roots, binds opaque IDs to paired
sessions, and revokes grants on disconnect, expiry or user request. Read and
write operations remain relative to retained native root handles.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import stat
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from odei_api.services.project_files import (
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_TOTAL_BYTES,
    MAX_TEXT_FILE_BYTES,
    ProjectFile,
    ProjectFileError,
    list_project_files_from_posix_fd,
    list_project_files_from_windows_handle,
    read_project_text_file_from_posix_fd,
    read_project_text_file_from_windows_handle,
)
from odei_api.services.secret_redaction import redact_secrets

MAX_SEARCH_QUERY_CHARS = 200
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_FILES = 1_000
MAX_SEARCH_TOTAL_BYTES = 20_000_000
MAX_SEARCH_FILE_BYTES = 128_000


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


class WorkspaceHandleRegistry:
    """Own and revoke native handles for explicitly selected workspace roots."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._grants: dict[str, _WorkspaceGrant] = {}

    def register_selected_root(
        self, selected_path: str | Path, *, allow_patch_apply: bool = False
    ) -> str:
        """Open a user-selected root once and retain its native handle.

        Call only from a trusted native folder-picker flow. Never pass a raw
        absolute path supplied by a remote browser request to this method.
        """
        label = Path(selected_path).name or "Selected folder"
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
        self,
        workspace_id: str,
        query: str,
        *,
        max_results: int = MAX_SEARCH_RESULTS,
    ) -> dict[str, object]:
        """Search bounded, eligible UTF-8 files under a selected workspace handle."""
        if (
            not isinstance(query, str)
            or not query.strip()
            or len(query) > MAX_SEARCH_QUERY_CHARS
            or "\\x00" in query
        ):
            raise ValueError("Search query must contain 1–200 non-NUL characters")
        if not isinstance(max_results, int) or not 1 <= max_results <= MAX_SEARCH_RESULTS:
            raise ValueError("Search result limit is invalid")

        files = self.list_files(
            workspace_id,
            max_files=MAX_SEARCH_FILES,
            max_total_bytes=MAX_SEARCH_TOTAL_BYTES,
        )
        listed_bytes = sum(item.size for item in files)
        truncated = len(files) >= MAX_SEARCH_FILES or listed_bytes >= MAX_SEARCH_TOTAL_BYTES
        needle = query.casefold()
        results: list[dict[str, str | int]] = []
        files_scanned = 0
        bytes_scanned = 0
        skipped_files = 0

        for item in files:
            if len(results) >= max_results:
                truncated = True
                break
            if item.size > MAX_SEARCH_FILE_BYTES:
                skipped_files += 1
                continue
            if bytes_scanned + item.size > MAX_SEARCH_TOTAL_BYTES:
                truncated = True
                break
            try:
                content = self.read_text(
                    workspace_id, item.path, max_bytes=MAX_SEARCH_FILE_BYTES
                )
            except (ProjectFileError, OSError, UnicodeError):
                skipped_files += 1
                continue

            encoded = content.encode("utf-8")
            if len(encoded) > MAX_SEARCH_FILE_BYTES:
                skipped_files += 1
                continue
            files_scanned += 1
            bytes_scanned += len(encoded)
            digest = hashlib.sha256(encoded).hexdigest()
            for line_number, line in enumerate(content.splitlines(), start=1):
                if needle in line.casefold():
                    results.append({
                        "path": item.path,
                        "line": line_number,
                        "text": redact_secrets(line)[:500],
                        "sha256": digest,
                    })
                    if len(results) >= max_results:
                        truncated = True
                        break

        return {
            "results": results,
            "files_scanned": files_scanned,
            "bytes_scanned": bytes_scanned,
            "skipped_files": skipped_files,
            "truncated": truncated,
        }

    def can_apply_patch(self, workspace_id: str) -> bool:
        """Report whether the selected root was opened with patch-write rights."""
        with self._borrow(workspace_id) as grant:
            return grant.allow_patch_apply

    def apply_patch(self, workspace_id: str, file: dict) -> dict[str, str | bool]:
        """Apply one signed, pre-authorized file operation beneath its held root."""
        from odei_api.services.workspace_patch_apply import apply_single_file_patch

        with self._borrow(workspace_id) as grant:
            if not grant.allow_patch_apply:
                raise WorkspaceHandleError("Workspace was opened read-only")
            return apply_single_file_patch(grant, file)

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
