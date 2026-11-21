"""In-memory registry for explicitly selected local workspace handles.

This is a local-process primitive, not an HTTP authorization system. A future
companion must call register_selected_root only after its native folder picker
returns a user-approved folder, then bind the opaque ID to the authenticated
user/session and revoke it on disconnect, expiry or user request.
"""
from __future__ import annotations

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
    list_project_files_from_posix_fd,
    list_project_files_from_windows_handle,
    read_project_text_file_from_posix_fd,
    read_project_text_file_from_windows_handle,
)


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
    lock: threading.RLock = field(default_factory=threading.RLock)


class WorkspaceHandleRegistry:
    """Own and revoke native handles for explicitly selected workspace roots."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._grants: dict[str, _WorkspaceGrant] = {}

    def register_selected_root(self, selected_path: str | Path) -> str:
        """Open a user-selected root once and retain its native handle.

        Call only from a trusted native folder-picker flow. Never pass a raw
        absolute path supplied by a remote browser request to this method.
        """
        label = Path(selected_path).name or "Selected folder"
        if os.name == "nt":
            from odei_api.services.windows_file_handles import open_directory_handle

            kernel32, handle = open_directory_handle(selected_path)
            grant = _WorkspaceGrant(platform="nt", handle=handle, label=label, kernel32=kernel32)
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
            grant = _WorkspaceGrant(platform="posix", handle=handle, label=label)
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

    def apply_patch(self, workspace_id: str, file: dict) -> dict[str, str | bool]:
        """Apply one signed, pre-authorized file operation beneath its held root."""
        from odei_api.services.workspace_patch_apply import apply_single_file_patch

        with self._borrow(workspace_id) as grant:
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
