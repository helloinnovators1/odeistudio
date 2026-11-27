"""Atomic local patch operations beneath a retained workspace root handle.

The companion accepts only signed, owner-approved file batches. Each file
operation is atomic; batches use hash-guarded compensation if a later step fails.
Paths are resolved relative to held directory handles, never caller paths.
"""
from __future__ import annotations

import hashlib
import logging
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

logger = logging.getLogger(__name__)


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
        if getattr(metadata, "st_nlink", 1) != 1:
            raise WorkspacePatchApplyError("Hard-linked patch targets are not permitted")
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



class WorkspacePatchBatchError(WorkspacePatchApplyError):
    """A multi-file patch failed; exposes whether compensation restored prior files."""

    def __init__(self, message: str, *, applied_paths: list[str], rolled_back_paths: list[str], rollback_failures: list[str]):
        super().__init__(message)
        self.applied_paths = applied_paths
        self.rolled_back_paths = rolled_back_paths
        self.rollback_failures = rollback_failures
        self.rollback_complete = not rollback_failures


def _read_for_batch(grant: Any, item: dict[str, Any], parsed) -> str | None:
    parts = parsed[0]
    if grant.platform == "posix":
        parent_fd = None
        try:
            parent_fd, name = _open_posix_parent(int(grant.handle), parts)
            current = _read_posix(parent_fd, name)
            return None if current is None else current[0]
        except FileNotFoundError:
            return None
        finally:
            if parent_fd is not None:
                os.close(parent_fd)
    if grant.platform == "nt":
        from odei_api.services.windows_file_handles import _read_windows_file

        return _read_windows_file(grant.handle, parts)
    raise WorkspacePatchApplyError("This platform does not support safe patch application")


def apply_file_patch_batch(
    grant: Any, items: list[dict[str, Any]], *, journal: Any | None = None,
    root_key: str | None = None,
) -> dict[str, Any]:
    """Apply a bounded batch with preflight checks and reverse-order compensation.

    Each individual filesystem operation is atomic. A batch is not a single
    filesystem transaction: if a later operation fails, earlier operations are
    reversed using hash-guarded inverse patches. A failed compensation is
    surfaced explicitly and must never be reported as a clean rollback.
    """
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise WorkspacePatchApplyError("A patch batch must contain between 1 and 20 files")
    parsed_items = [_validate_file(item) for item in items]
    paths = ["/".join(parsed[0]).casefold() for parsed in parsed_items]
    if len(set(paths)) != len(paths):
        raise WorkspacePatchApplyError("Patch batch contains duplicate paths")
    total_bytes = sum(len(item["content"].encode("utf-8")) for item in items if item["content"] is not None)
    if total_bytes > 5 * 1024 * 1024:
        raise WorkspacePatchApplyError("Patch batch exceeds the aggregate content limit")

    originals: list[str | None] = []
    for item, parsed in zip(items, parsed_items, strict=True):
        current = _read_for_batch(grant, item, parsed)
        operation, base_hash = parsed[1], parsed[2]
        if operation == "create":
            if current is not None:
                raise WorkspacePatchApplyError("A file already exists at an approved create path")
        elif current is None or hashlib.sha256(current.encode("utf-8")).hexdigest() != base_hash:
            raise WorkspacePatchApplyError("A file changed after the approved batch was prepared")
        originals.append(current)

    transaction_id = None
    if journal is not None:
        if not isinstance(root_key, str) or len(root_key) != 64:
            raise WorkspacePatchApplyError("A durable workspace root identity is required")
        # This write-ahead record must be durable before the first filesystem mutation.
        transaction_id = journal.prepare(root_key, items, originals)

    applied: list[tuple[dict[str, Any], str | None]] = []
    results: list[dict[str, Any]] = []
    in_flight: tuple[dict[str, Any], str | None, Any] | None = None
    try:
        for item, original, parsed in zip(items, originals, parsed_items, strict=True):
            in_flight = (item, original, parsed)
            result = apply_single_file_patch(grant, item)
            applied.append((item, original))
            in_flight = None
            results.append(result)
    except (OSError, ValueError) as failure:
        uncertain_paths: list[str] = []
        # A native operation can mutate the directory and then fail during
        # temporary-name cleanup or a durability step. Detect that exact
        # post-image before deciding which operations need compensation.
        if in_flight is not None:
            item, original, parsed = in_flight
            operation, base_hash, result_hash = parsed[1], parsed[2], parsed[3]
            try:
                current = _read_for_batch(grant, item, parsed)
                current_hash = (
                    hashlib.sha256(current.encode("utf-8")).hexdigest()
                    if current is not None else None
                )
                applied_after_error = (
                    (operation == "create" and current_hash == result_hash)
                    or (operation == "update" and current_hash == result_hash)
                    or (operation == "delete" and current is None)
                )
                unchanged_after_error = (
                    (operation == "create" and current is None)
                    or (operation in {"update", "delete"} and current_hash == base_hash)
                )
                if applied_after_error:
                    applied.append((item, original))
                elif not unchanged_after_error:
                    uncertain_paths.append(item["path"])
            except (OSError, ValueError, WorkspacePatchApplyError):
                uncertain_paths.append(item["path"])
        applied_paths = [item["path"] for item, _original in applied]
        rolled_back: list[str] = []
        rollback_failures: list[str] = list(uncertain_paths)
        for item, original in reversed(applied):
            operation = item["operation"]
            if operation == "create":
                inverse = {
                    "path": item["path"], "operation": "delete",
                    "base_sha256": item["result_sha256"],
                    "result_sha256": None, "content": None,
                }
            elif operation == "update":
                restored_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
                inverse = {
                    "path": item["path"], "operation": "update",
                    "base_sha256": item["result_sha256"],
                    "result_sha256": restored_hash, "content": original,
                }
            else:
                restored_hash = hashlib.sha256(original.encode("utf-8")).hexdigest()
                inverse = {
                    "path": item["path"], "operation": "create",
                    "base_sha256": None,
                    "result_sha256": restored_hash, "content": original,
                }
            try:
                apply_single_file_patch(grant, inverse)
                rolled_back.append(item["path"])
            except (OSError, ValueError) as rollback_error:
                rollback_failures.append(item["path"])
                # Do not include file contents, absolute paths or secrets.
                logger.error(
                    "Compensation failed for %s (%s)",
                    item["path"], type(rollback_error).__name__,
                )
        if transaction_id is not None:
            journal.finish(
                transaction_id,
                state="recovered" if not rollback_failures else "conflict",
                receipt={
                    "applied_paths": applied_paths,
                    "rolled_back_paths": rolled_back,
                    "rollback_failures": rollback_failures,
                },
            )
        raise WorkspacePatchBatchError(
            "Patch batch failed; " + (
                "all earlier file operations were rolled back"
                if not rollback_failures else
                "one or more rollback operations failed and workspace recovery is required"
            ),
            applied_paths=applied_paths,
            rolled_back_paths=rolled_back,
            rollback_failures=rollback_failures,
        ) from failure

    receipt = {
        "applied_paths": [item["path"] for item in items],
        "file_count": len(items),
        "rollback_required": False,
    }
    if transaction_id is not None:
        # If this commit record cannot be persisted, leave the durable pending
        # before-images intact; startup recovery will safely reverse the batch.
        journal.finish(transaction_id, state="committed", receipt=receipt)

    return {
        "applied": True,
        "transaction_id": transaction_id,
        "transaction_semantics": (
            "durable-write-ahead-journal-with-crash-recovery"
            if transaction_id is not None else
            "per-file-atomic-with-compensating-rollback"
        ),
        "rollback_required": False,
        "files": results,
    }


class WorkspacePatchRecoveryRequired(RuntimeError):
    """A pending transaction conflicts with current workspace contents."""


def recover_pending_patch_transactions(
    grant: Any, journal: Any, root_key: str
) -> list[dict[str, Any]]:
    """Recover pending batches through the selected native root handle.

    Each target is restored only when its current hash is either the recorded
    pre-transaction hash or the approved post-transaction hash. Any third value
    is treated as an external edit and blocks recovery without overwriting it.
    """
    recovered: list[dict[str, Any]] = []
    for transaction in journal.pending(root_key):
        transaction_id = transaction["transaction_id"]
        restored_paths: list[str] = []
        conflicts: list[str] = []
        for entry in reversed(transaction["files"]):
            item = entry["patch"]
            before = entry["before"]
            parsed = _validate_file(item)
            operation, base_hash, result_hash = parsed[1], parsed[2], parsed[3]
            try:
                current = _read_for_batch(grant, item, parsed)
                current_hash = (
                    hashlib.sha256(current.encode("utf-8")).hexdigest()
                    if current is not None else None
                )
                inverse = None
                if operation == "create":
                    if current is None:
                        continue
                    if current_hash != result_hash:
                        conflicts.append(item["path"])
                        continue
                    inverse = {
                        "path": item["path"], "operation": "delete",
                        "base_sha256": result_hash, "result_sha256": None,
                        "content": None,
                    }
                elif operation == "update":
                    if before is None:
                        conflicts.append(item["path"])
                        continue
                    if current_hash == base_hash:
                        continue
                    if current_hash != result_hash:
                        conflicts.append(item["path"])
                        continue
                    inverse = {
                        "path": item["path"], "operation": "update",
                        "base_sha256": result_hash,
                        "result_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
                        "content": before,
                    }
                else:  # delete
                    if before is None:
                        conflicts.append(item["path"])
                        continue
                    if current is not None:
                        if current_hash == base_hash:
                            continue
                        conflicts.append(item["path"])
                        continue
                    inverse = {
                        "path": item["path"], "operation": "create",
                        "base_sha256": None,
                        "result_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
                        "content": before,
                    }
                if inverse is not None:
                    apply_single_file_patch(grant, inverse)
                    restored_paths.append(item["path"])
            except (OSError, ValueError, WorkspacePatchApplyError):
                conflicts.append(item["path"])

        if conflicts:
            journal.finish(
                transaction_id, state="conflict",
                receipt={"recovery_conflicts": sorted(set(conflicts)),
                         "restored_paths": restored_paths},
            )
            raise WorkspacePatchRecoveryRequired(
                "A pending workspace transaction conflicts with external file changes: "
                + ", ".join(sorted(set(conflicts)))
            )
        journal.finish(
            transaction_id, state="recovered",
            receipt={"recovered": True, "restored_paths": restored_paths},
        )
        recovered.append({
            "transaction_id": transaction_id,
            "restored_paths": restored_paths,
        })
    return recovered
