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

    if os.name == "nt":
        from odei_api.services.windows_file_handles import (
            UnsafeWindowsPath,
            open_readonly_file,
        )

        try:
            return open_readonly_file(root, parts)
        except IsADirectoryError as exc:
            raise ProjectFileError("Requested path is not a regular file") from exc
        except UnsafeWindowsPath as exc:
            raise UnsafeProjectPath(str(exc)) from exc

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



def _list_project_files_windows(
    workspace: Path,
    *,
    max_files: int,
    max_total_bytes: int,
    root_handle=None,
) -> list[ProjectFile]:
    """Enumerate a Windows workspace using held directory handles only."""
    from odei_api.services.windows_file_handles import (
        FILE_ATTRIBUTE_DIRECTORY,
        FILE_ATTRIBUTE_REPARSE_POINT,
        close_directory_handle,
        iter_directory_entries,
        open_child_directory_handle,
        open_directory_handle,
        read_child_text,
    )

    owns_root_handle = root_handle is None
    if owns_root_handle:
        kernel32, root_handle = open_directory_handle(workspace)
    found: list[ProjectFile] = []
    total_bytes = 0

    def walk(
        directory_handle,
        relative_parts: tuple[str, ...],
        inherited_specs: list[tuple[tuple[str, ...], GitIgnoreSpec]],
    ) -> bool:
        nonlocal total_bytes
        current_specs = list(inherited_specs)
        ignore_text = read_child_text(directory_handle, ".gitignore")
        if ignore_text is not None:
            current_specs.append(
                (relative_parts, GitIgnoreSpec.from_lines(ignore_text.splitlines()))
            )

        entries = sorted(
            iter_directory_entries(directory_handle),
            key=lambda item: item[0].casefold(),
        )
        for name, attributes, size in entries:
            if name in {".", ".."}:
                continue
            parts = (*relative_parts, name)
            if _is_excluded(parts):
                continue
            is_directory = bool(attributes & FILE_ATTRIBUTE_DIRECTORY)
            if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                continue

            ignored = False
            for prefix, spec in current_specs:
                relative_to_rule = PurePosixPath(*parts[len(prefix):]).as_posix()
                if is_directory:
                    relative_to_rule += "/"
                if spec.match_file(relative_to_rule):
                    ignored = True
            if ignored:
                continue

            if is_directory:
                child_handle = None
                try:
                    child_handle = open_child_directory_handle(directory_handle, name)
                    if not walk(child_handle, parts, current_specs):
                        return False
                except (OSError, UnsafeProjectPath):
                    continue
                finally:
                    if child_handle is not None:
                        close_directory_handle(kernel32, child_handle)
                continue

            if total_bytes + size > max_total_bytes:
                return False
            found.append(ProjectFile(path=PurePosixPath(*parts).as_posix(), size=size))
            total_bytes += size
            if len(found) >= max_files:
                return False
        return True

    try:
        walk(root_handle, (), [])
        return found
    finally:
        if owns_root_handle:
            close_directory_handle(kernel32, root_handle)

def _read_ignore_spec_from_fd(directory_fd: int) -> GitIgnoreSpec | None:
    """Read .gitignore relative to a held POSIX directory descriptor."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(".gitignore", flags, dir_fd=directory_fd)
    except OSError:
        return None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1_000_000:
            return None
        data = bytearray()
        while len(data) <= 1_000_000:
            chunk = os.read(descriptor, min(65536, 1_000_001 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > 1_000_000 or b"\x00" in data:
            return None
        try:
            return GitIgnoreSpec.from_lines(data.decode("utf-8").splitlines())
        except UnicodeDecodeError:
            return None
    finally:
        os.close(descriptor)


def _list_project_files_posix(
    workspace: Path,
    *,
    max_files: int,
    max_total_bytes: int,
    root_fd: int | None = None,
) -> list[ProjectFile]:
    """List files using descriptor-relative traversal on POSIX."""
    if not hasattr(os, "fwalk") or os.open not in os.supports_dir_fd:
        raise ProjectFileError("This POSIX platform lacks safe descriptor traversal")

    found: list[ProjectFile] = []
    total_bytes = 0
    specs_by_directory: dict[
        tuple[str, ...], list[tuple[tuple[str, ...], GitIgnoreSpec]]
    ] = {(): []}
    open_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )

    top = "." if root_fd is not None else workspace
    walk_kwargs = {"dir_fd": root_fd} if root_fd is not None else {}
    for current_dir, dirnames, filenames, directory_fd in os.fwalk(
        top, topdown=True, follow_symlinks=False, **walk_kwargs
    ):
        if root_fd is None:
            relative_directory = Path(current_dir).relative_to(workspace)
            directory_parts = relative_directory.parts
        else:
            directory_parts = tuple(
                part for part in PurePosixPath(current_dir).parts if part not in {".", ""}
            )
        current_specs = list(specs_by_directory.pop(directory_parts, []))
        local_spec = _read_ignore_spec_from_fd(directory_fd)
        if local_spec is not None:
            current_specs.append((directory_parts, local_spec))

        kept_directories: list[str] = []
        for name in sorted(dirnames):
            parts = (*directory_parts, name)
            if _is_excluded(parts):
                continue
            try:
                metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError:
                continue
            if not stat.S_ISDIR(metadata.st_mode):
                continue
            ignored = False
            for prefix, spec in current_specs:
                relative_name = PurePosixPath(*parts[len(prefix):]).as_posix() + "/"
                if spec.match_file(relative_name):
                    ignored = True
            if ignored:
                continue
            kept_directories.append(name)
            specs_by_directory[parts] = current_specs
        dirnames[:] = kept_directories

        for name in sorted(filenames):
            parts = (*directory_parts, name)
            if _is_excluded(parts):
                continue
            ignored = False
            for prefix, spec in current_specs:
                relative_name = PurePosixPath(*parts[len(prefix):]).as_posix()
                if spec.match_file(relative_name):
                    ignored = True
            if ignored:
                continue

            descriptor = None
            try:
                descriptor = os.open(name, open_flags, dir_fd=directory_fd)
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    continue
            except OSError:
                continue
            finally:
                if descriptor is not None:
                    os.close(descriptor)

            if total_bytes + metadata.st_size > max_total_bytes:
                return found
            found.append(
                ProjectFile(path=PurePosixPath(*parts).as_posix(), size=metadata.st_size)
            )
            total_bytes += metadata.st_size
            if len(found) >= max_files:
                return found
    return found


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
    if os.name == "nt":
        return _list_project_files_windows(
            workspace, max_files=max_files, max_total_bytes=max_total_bytes
        )
    if os.name == "posix":
        return _list_project_files_posix(
            workspace, max_files=max_files, max_total_bytes=max_total_bytes
        )
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



def list_project_files_from_windows_handle(
    root_handle,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> list[ProjectFile]:
    """List files beneath a retained, user-authorized Windows root handle."""
    if max_files < 1 or max_total_bytes < 1:
        raise ValueError("max_files and max_total_bytes must be positive")
    return _list_project_files_windows(
        Path("."), max_files=max_files, max_total_bytes=max_total_bytes,
        root_handle=root_handle,
    )


def list_project_files_from_posix_fd(
    root_fd: int,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> list[ProjectFile]:
    """List files beneath a retained, user-authorized POSIX root descriptor."""
    if max_files < 1 or max_total_bytes < 1:
        raise ValueError("max_files and max_total_bytes must be positive")
    return _list_project_files_posix(
        Path("."), max_files=max_files, max_total_bytes=max_total_bytes,
        root_fd=root_fd,
    )


def _read_open_descriptor(file_fd: int, metadata: os.stat_result, max_bytes: int) -> str:
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


def read_project_text_file_from_posix_fd(
    root_fd: int,
    relative_path: str,
    *,
    max_bytes: int = MAX_TEXT_FILE_BYTES,
) -> str:
    """Read text relative to a retained POSIX root descriptor."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    parts = _relative_parts(relative_path)
    if _is_excluded(parts):
        raise UnsafeProjectPath("This path is excluded from project indexing")
    flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    opened_directories = []
    file_fd = None
    try:
        parent_fd = root_fd
        for component in parts[:-1]:
            child_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            opened_directories.append(child_fd)
            parent_fd = child_fd
        file_fd = os.open(parts[-1], flags, dir_fd=parent_fd)
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProjectFileError("Requested path is not a regular file")
        owned_fd = file_fd
        file_fd = None
        return _read_open_descriptor(owned_fd, metadata, max_bytes)
    except OSError as exc:
        if isinstance(exc, IsADirectoryError):
            raise ProjectFileError("Requested path is not a regular file") from exc
        raise
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for descriptor in reversed(opened_directories):
            os.close(descriptor)


def read_project_text_file_from_windows_handle(
    root_handle,
    relative_path: str,
    *,
    max_bytes: int = MAX_TEXT_FILE_BYTES,
) -> str:
    """Read text relative to a retained, user-authorized Windows root handle."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    parts = _relative_parts(relative_path)
    if _is_excluded(parts):
        raise UnsafeProjectPath("This path is excluded from project indexing")
    from odei_api.services.windows_file_handles import (
        UnsafeWindowsPath,
        open_readonly_file_from_handle,
    )
    try:
        file_fd, metadata = open_readonly_file_from_handle(root_handle, parts)
    except IsADirectoryError as exc:
        raise ProjectFileError("Requested path is not a regular file") from exc
    except UnsafeWindowsPath as exc:
        raise UnsafeProjectPath(str(exc)) from exc
    return _read_open_descriptor(file_fd, metadata, max_bytes)

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
