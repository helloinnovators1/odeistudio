"""Safe, read-only project file access for a user-selected workspace.

This module deliberately does not expose an HTTP route yet. The API must add
authentication, tenant authorization and workspace ownership before exposing it.
"""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pathspec import GitIgnoreSpec

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
DEFAULT_MAX_FILES = 5_000
DEFAULT_MAX_TOTAL_BYTES = 100_000_000


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


def _is_link_or_junction(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(metadata.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if getattr(metadata, "st_file_attributes", 0) & reparse_flag:
        return True
    is_junction = getattr(os.path, "isjunction", None)
    return bool(is_junction and is_junction(path))


def _open_verified_file(root: Path, relative_path: str, target: Path) -> tuple[int, os.stat_result]:
    """Open a file without following path components on POSIX.

    Windows uses file identity and post-open containment checks; a native
    CreateFileW handle implementation is still required before hostile,
    concurrently mutable workspaces are treated as a production trust boundary.
    """
    parts = _relative_parts(relative_path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)

    if (
        os.name == "posix"
        and nofollow
        and directory
        and os.open in os.supports_dir_fd
    ):
        root_fd = os.open(root, flags | directory)
        opened_directories: list[int] = []
        try:
            current_fd = root_fd
            for part in parts[:-1]:
                next_fd = os.open(
                    part,
                    flags | directory | nofollow,
                    dir_fd=current_fd,
                )
                opened_directories.append(next_fd)
                current_fd = next_fd
            file_fd = os.open(parts[-1], flags | nofollow, dir_fd=current_fd)
            metadata = os.fstat(file_fd)
            if not stat.S_ISREG(metadata.st_mode):
                os.close(file_fd)
                raise ProjectFileError("Requested path is not a regular file")
            return file_fd, metadata
        finally:
            for directory_fd in reversed(opened_directories):
                os.close(directory_fd)
            os.close(root_fd)

    before = target.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ProjectFileError("Requested path is not a regular file")
    try:
        file_fd = os.open(target, flags)
    except OSError as exc:
        current = target.stat()
        if not stat.S_ISREG(current.st_mode):
            raise ProjectFileError("Requested path is not a regular file") from exc
        raise
    try:
        metadata = os.fstat(file_fd)
        after = target.stat()
        resolved_after_open = target.resolve(strict=True)
        identity_before = (before.st_dev, before.st_ino)
        identity_open = (metadata.st_dev, metadata.st_ino)
        identity_after = (after.st_dev, after.st_ino)
        if (
            not resolved_after_open.is_relative_to(root)
            or not stat.S_ISREG(metadata.st_mode)
            or identity_before != identity_open
            or identity_open != identity_after
        ):
            raise UnsafeProjectPath("File identity or workspace containment changed during open")
        return file_fd, metadata
    except Exception:
        os.close(file_fd)
        raise


def _load_ignore_spec(directory: Path) -> GitIgnoreSpec | None:
    ignore_file = directory / ".gitignore"
    if not ignore_file.is_file() or ignore_file.is_symlink():
        return None
    try:
        lines = ignore_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    return GitIgnoreSpec.from_lines(lines)


def _ignored_by_gitignore(root: Path, directory: Path, name: str, *, is_dir: bool) -> bool:
    """Apply each ancestor .gitignore relative to its own directory."""
    candidate = directory / name
    is_ignored = False
    ancestors = [root]
    ancestors.extend(
        ancestor for ancestor in reversed(directory.parents)
        if ancestor.is_relative_to(root) and ancestor != root
    )
    if directory != root:
        ancestors.append(directory)

    for ancestor in ancestors:
        spec = _load_ignore_spec(ancestor)
        if spec is None:
            continue
        relative = candidate.relative_to(ancestor).as_posix()
        check_path = relative + ("/" if is_dir else "")
        if spec.match_file(check_path):
            is_ignored = True
    return is_ignored


def list_project_files(
    root: str | Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> list[ProjectFile]:
    """List eligible regular files beneath an explicitly selected workspace."""
    if max_files < 1 or max_total_bytes < 1:
        raise ValueError("max_files and max_total_bytes must be positive")
    workspace = _workspace_root(root)
    found: list[ProjectFile] = []
    total_bytes = 0

    for current_dir, dirnames, filenames in os.walk(
        workspace, topdown=True, followlinks=False
    ):
        current = Path(current_dir)
        relative_dir = current.relative_to(workspace)
        dirnames[:] = sorted(
            name for name in dirnames
            if name.lower() not in DEFAULT_EXCLUDED_DIRS
            and not _is_link_or_junction(current / name)
            and not _is_excluded((*relative_dir.parts, name))
            and not _ignored_by_gitignore(workspace, current, name, is_dir=True)
        )

        for filename in sorted(filenames):
            candidate = current / filename
            relative = candidate.relative_to(workspace)
            parts = relative.parts
            if _is_link_or_junction(candidate) or _is_excluded(parts):
                continue
            if _ignored_by_gitignore(workspace, current, filename, is_dir=False):
                continue
            try:
                metadata = candidate.lstat()
            except OSError:
                continue
            if not stat.S_ISREG(metadata.st_mode):
                continue
            size = metadata.st_size
            if total_bytes + size > max_total_bytes:
                return found
            found.append(ProjectFile(path=relative.as_posix(), size=size))
            total_bytes += size
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
    file_fd, metadata = _open_verified_file(workspace, relative_path, target)
    with os.fdopen(file_fd, "rb") as file_handle:
        if metadata.st_size > max_bytes:
            raise ProjectFileTooLarge(f"File exceeds the {max_bytes}-byte read limit")
        data = file_handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ProjectFileTooLarge(f"File exceeds the {max_bytes}-byte read limit")
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
