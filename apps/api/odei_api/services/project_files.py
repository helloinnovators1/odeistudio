"""Safe, read-only project file access for a user-selected workspace.

This module deliberately does not expose an HTTP route yet. The API must add
authentication, tenant authorization and workspace ownership before exposing it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DEFAULT_EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules",
    "__pycache__", ".next", "dist", "build", "coverage",
    ".ssh", ".aws", ".azure", ".gnupg",
}
DEFAULT_EXCLUDED_NAMES = {
    ".env", ".env.local", ".env.development", ".env.production",
    "id_rsa", "id_ed25519", "credentials", "credentials.json",
    ".npmrc", ".pypirc", ".envrc",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
MAX_TEXT_FILE_BYTES = 1_000_000


class ProjectFileError(ValueError):
    """Base exception for rejected project file operations."""


class UnsafeProjectPath(ProjectFileError):
    """Raised when a path escapes the selected workspace or targets a symlink."""


class ProjectFileTooLarge(ProjectFileError):
    """Raised when a file exceeds the configured read limit."""


class BinaryProjectFile(ProjectFileError):
    """Raised when a requested file is not valid UTF-8 text."""


@dataclass(frozen=True)
class ProjectFile:
    path: str
    size: int


def _workspace_root(root: str | Path) -> Path:
    resolved = Path(root).expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise ProjectFileError("Workspace root must be a directory")
    return resolved


def _relative_parts(relative_path: str) -> tuple[str, ...]:
    normalized = relative_path.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if candidate.is_absolute() or not candidate.parts:
        raise UnsafeProjectPath("Only non-empty relative paths are allowed")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise UnsafeProjectPath("Path traversal is not allowed")
    if ":" in candidate.parts[0]:
        raise UnsafeProjectPath("Drive-qualified paths are not allowed")
    return candidate.parts


def _is_excluded(parts: tuple[str, ...]) -> bool:
    for part in parts:
        lowered = part.lower()
        if lowered in DEFAULT_EXCLUDED_DIRS or lowered in DEFAULT_EXCLUDED_NAMES:
            return True
        if lowered.endswith(tuple(SENSITIVE_SUFFIXES)):
            return True
        if lowered.startswith(".env."):
            return True
    return False


def _safe_target(root: Path, relative_path: str) -> Path:
    parts = _relative_parts(relative_path)
    if _is_excluded(parts):
        raise UnsafeProjectPath("This path is excluded from project indexing")

    target = root.joinpath(*parts)
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise UnsafeProjectPath("Symbolic links are not followed")

    resolved = target.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise UnsafeProjectPath("Path escapes the selected workspace")
    return resolved


def list_project_files(
    root: str | Path,
    *,
    max_files: int = 5_000,
) -> list[ProjectFile]:
    """List eligible regular files beneath an explicitly selected workspace."""
    if max_files < 1:
        raise ValueError("max_files must be positive")
    workspace = _workspace_root(root)
    found: list[ProjectFile] = []

    for current_dir, dirnames, filenames in os.walk(
        workspace, topdown=True, followlinks=False
    ):
        current = Path(current_dir)
        relative_dir = current.relative_to(workspace)
        dirnames[:] = sorted(
            name for name in dirnames
            if name.lower() not in DEFAULT_EXCLUDED_DIRS
            and not (current / name).is_symlink()
            and not _is_excluded((*relative_dir.parts, name))
        )

        for filename in sorted(filenames):
            candidate = current / filename
            relative = candidate.relative_to(workspace)
            parts = relative.parts
            if candidate.is_symlink() or _is_excluded(parts):
                continue
            if not candidate.is_file():
                continue
            found.append(ProjectFile(path=relative.as_posix(), size=candidate.stat().st_size))
            if len(found) >= max_files:
                return found

    return found


def read_project_text_file(
    root: str | Path,
    relative_path: str,
    *,
    max_bytes: int = MAX_TEXT_FILE_BYTES,
) -> str:
    """Read one bounded UTF-8 text file; secret-like paths are excluded."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    workspace = _workspace_root(root)
    target = _safe_target(workspace, relative_path)
    if not target.is_file():
        raise ProjectFileError("Requested path is not a regular file")
    size = target.stat().st_size
    if size > max_bytes:
        raise ProjectFileTooLarge(f"File exceeds the {max_bytes}-byte read limit")

    data = target.read_bytes()
    if b"\x00" in data:
        raise BinaryProjectFile("Binary files are not returned as text")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BinaryProjectFile("File is not valid UTF-8 text") from exc


def search_project_text(
    root: str | Path,
    query: str,
    *,
    max_results: int = 100,
    max_file_bytes: int = MAX_TEXT_FILE_BYTES,
) -> list[dict[str, str | int]]:
    """Case-insensitive literal search over eligible UTF-8 text files."""
    if not query:
        raise ValueError("query must not be empty")
    if max_results < 1:
        raise ValueError("max_results must be positive")

    matches: list[dict[str, str | int]] = []
    for item in list_project_files(root):
        if item.size > max_file_bytes:
            continue
        try:
            content = read_project_text_file(
                root, item.path, max_bytes=max_file_bytes
            )
        except (BinaryProjectFile, ProjectFileTooLarge, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            if query.casefold() in line.casefold():
                matches.append({
                    "path": item.path,
                    "line": line_number,
                    "text": line[:500],
                })
                if len(matches) >= max_results:
                    return matches
    return matches
