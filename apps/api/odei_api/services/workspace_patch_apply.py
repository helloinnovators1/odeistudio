"""One-file atomic patch application beneath a retained workspace root handle.

The companion accepts only a signed, single-file capability. Paths are resolved
relative to held directory handles; no caller-supplied absolute paths are used.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import stat
from pathlib import PurePosixPath
from typing import Any

from odei_api.services.patch_proposals import (
    MAX_FILE_BYTES,
    PatchProposalError,
    validate_patch_path,
)


class WorkspacePatchApplyError(ValueError):
    """A patch cannot be safely applied to the current workspace snapshot."""


def _validate_file(item: dict[str, Any]) -> tuple[tuple[str, ...], str, str | None, str | None]:
    if not isinstance(item, dict) or set(item) != {
        "path", "operation", "base_sha256", "result_sha256", "content",
    }:
        raise WorkspacePatchApplyError("Patch file fields are invalid")
    path = item["path"]
    try:
        validate_patch_path(path)
    except PatchProposalError as exc:
        raise WorkspacePatchApplyError("Patch path is not permitted") from exc
    parts = PurePosixPath(path).parts
    operation = item["operation"]
    base_hash = item["base_sha256"]
    result_hash = item["result_sha256"]
    content = item["content"]
    if operation not in {"create", "update", "delete"}:
        raise WorkspacePatchApplyError("Patch operation is invalid")
    if operation == "create":
        if base_hash is not None or not isinstance(content, str):
            raise WorkspacePatchApplyError("Create operation fields are inconsistent")
    elif operation == "update":
        if not isinstance(base_hash, str) or len(base_hash) != 64 or not isinstance(content, str):
            raise WorkspacePatchApplyError("Update operation fields are inconsistent")
    elif not isinstance(base_hash, str) or len(base_hash) != 64 or content is not None or result_hash is not None:
        raise WorkspacePatchApplyError("Delete operation fields are inconsistent")
    if content is not None:
        if "\x00" in content:
            raise WorkspacePatchApplyError("Binary patch content is not supported")
        try:
            encoded = content.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise WorkspacePatchApplyError("Patch content must be valid UTF-8") from exc
        if len(encoded) > MAX_FILE_BYTES:
            raise WorkspacePatchApplyError("Patch content exceeds the per-file limit")
        actual_hash = hashlib.sha256(encoded).hexdigest()
        if not isinstance(result_hash, str) or actual_hash != result_hash:
            raise WorkspacePatchApplyError("Replacement content hash does not match the approved patch")
    return parts, operation, base_hash, result_hash


def _read_posix(parent_fd: int, name: str) -> tuple[str, os.stat_result] | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise WorkspacePatchApplyError("Target is unavailable for safe reading") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_FILE_BYTES:
            raise WorkspacePatchApplyError("Target is not a bounded regular file")
        chunks = bytearray()
        while len(chunks) <= MAX_FILE_BYTES:
            chunk = os.read(descriptor, min(65_536, MAX_FILE_BYTES + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        if len(chunks) > MAX_FILE_BYTES or b"\x00" in chunks:
            raise WorkspacePatchApplyError("Target is binary or exceeds the safe read limit")
        # A retained descriptor prevents path substitution, but it does not
        # prevent another process from modifying the same inode while we read.
        # Compare stable file identity/metadata before and after the read so a
        # hash is never calculated over a torn or mixed-version snapshot.
        after = os.fstat(descriptor)
        stable_fields = (
            "st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns",
        )
        if (
            any(getattr(metadata, field) != getattr(after, field) for field in stable_fields)
            or len(chunks) != after.st_size
        ):
            raise WorkspacePatchApplyError("Target changed while being read")
        try:
            return chunks.decode("utf-8"), metadata
        except UnicodeDecodeError as exc:
            raise WorkspacePatchApplyError("Target is not UTF-8 text") from exc
    finally:
        os.close(descriptor)


def _open_posix_parent(root_fd: int, parts: tuple[str, ...]) -> tuple[int, str]:
    descriptor = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            child = os.open(
                component,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1]
    except Exception:
        os.close(descriptor)
        raise


def _apply_posix(root_fd: int, item: dict[str, Any], parsed) -> dict[str, str | bool]:
    parts, operation, base_hash, result_hash = parsed
    parent_fd, name = _open_posix_parent(root_fd, parts)
    temp_name: str | None = None
    try:
        current = _read_posix(parent_fd, name)
        if operation == "create":
            if current is not None:
                raise WorkspacePatchApplyError("A file already exists at the approved create path")
        else:
            if current is None:
                raise WorkspacePatchApplyError("The approved base file no longer exists")
            current_hash = hashlib.sha256(current[0].encode("utf-8")).hexdigest()
            if current_hash != base_hash:
                raise WorkspacePatchApplyError("The file changed after the proposal was approved")

        if operation == "delete":
            latest = _read_posix(parent_fd, name)
            if latest is None or hashlib.sha256(latest[0].encode("utf-8")).hexdigest() != base_hash:
                raise WorkspacePatchApplyError("The file changed immediately before deletion")
            os.unlink(name, dir_fd=parent_fd)
        else:
            content = item["content"]
            encoded = content.encode("utf-8")
            temp_name = ".odei-" + secrets.token_hex(16) + ".tmp"
            flags = (
                os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            )
            temp_fd = os.open(temp_name, flags, 0o600, dir_fd=parent_fd)
            try:
                if operation == "update" and current is not None:
                    os.fchmod(temp_fd, stat.S_IMODE(current[1].st_mode))
                offset = 0
                while offset < len(encoded):
                    offset += os.write(temp_fd, encoded[offset:])
                os.fsync(temp_fd)
            finally:
                os.close(temp_fd)

            # Recheck the base snapshot after staging and immediately before rename.
            latest = _read_posix(parent_fd, name)
            if operation == "create":
                if latest is not None:
                    raise WorkspacePatchApplyError("A file appeared at the approved create path")
                # link() is atomic and refuses to replace a concurrently-created path.
                os.link(temp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
                os.unlink(temp_name, dir_fd=parent_fd)
            else:
                if latest is None or hashlib.sha256(latest[0].encode("utf-8")).hexdigest() != base_hash:
                    raise WorkspacePatchApplyError("The file changed immediately before replacement")
                os.replace(temp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            temp_name = None
        try:
            os.fsync(parent_fd)
            durability_confirmed = True
        except OSError:
            # The namespace operation already committed atomically. Do not
            # report it as unapplied when only directory durability is unknown.
            durability_confirmed = False
        return {
            "path": item["path"],
            "operation": operation,
            "result_sha256": result_hash or "",
            "applied": True,
            "durability_confirmed": durability_confirmed,
        }
    except WorkspacePatchApplyError:
        raise
    except (OSError, ValueError) as exc:
        raise WorkspacePatchApplyError("The approved patch could not be applied safely") from exc
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except OSError:
                pass
        try:
            os.close(parent_fd)
        except OSError:
            pass


def apply_single_file_patch(grant: Any, item: dict[str, Any]) -> dict[str, str | bool]:
    """Apply exactly one approved file operation atomically or fail closed."""
    parsed = _validate_file(item)
    if grant.platform == "posix":
        return _apply_posix(int(grant.handle), item, parsed)
    if grant.platform == "nt":
        from odei_api.services.windows_file_handles import apply_single_file_patch_from_handle

        return apply_single_file_patch_from_handle(grant.handle, item, parsed)
    raise WorkspacePatchApplyError("This platform does not support safe patch application")
