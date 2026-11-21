"""Bounded, read-only validation of multi-file NEXUS patch proposals.

This module creates review artifacts only. It never opens or mutates workspace files;
callers must supply an already-authorized, bounded base snapshot.
"""
from __future__ import annotations

import difflib
import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass
from collections.abc import Mapping

MAX_PATCH_FILES = 20
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 5_000_000
MAX_DIFF_BYTES = 8_000_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul"}
_EXCLUDED_PARTS = {
    ".git", ".ssh", ".aws", ".azure", ".gnupg", "node_modules",
    ".venv", "venv", "__pycache__",
}
_EXCLUDED_NAMES = {
    ".env", ".env.local", ".env.development", ".env.production",
    "id_rsa", "id_ed25519", "credentials", "credentials.json",
    ".npmrc", ".pypirc", ".envrc",
}


class PatchProposalError(ValueError):
    """A patch proposal violates path, snapshot, or resource constraints."""


@dataclass(frozen=True)
class ProposedFileChange:
    path: str
    operation: str
    base_sha256: str | None
    result_sha256: str | None
    content: str | None
    unified_diff: str


@dataclass(frozen=True)
class PatchProposal:
    files: tuple[ProposedFileChange, ...]
    total_content_bytes: int
    total_diff_bytes: int


def _validate_path(path: str) -> tuple[str, ...]:
    if not isinstance(path, str) or not path or len(path) > 1024:
        raise PatchProposalError("Patch paths must be non-empty relative paths")
    if path.startswith(("/", "\\\\")) or "\x00" in path or "\\" in path:
        raise PatchProposalError("Absolute, NUL and backslash paths are not allowed")
    if path != unicodedata.normalize("NFC", path):
        raise PatchProposalError("Paths must use Unicode NFC normalization")
    parts = tuple(path.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise PatchProposalError("Path traversal and empty path components are not allowed")
    for part in parts:
        lowered = part.casefold()
        device_name = lowered.split(".", 1)[0].rstrip(" .")
        if (
            ":" in part
            or part.endswith((".", " "))
            or any(ord(character) < 32 or character in '<>:"|?*' for character in part)
            or device_name in _WINDOWS_RESERVED
            or sum(2 if ord(character) > 0xFFFF else 1 for character in part) > 255
            or re.fullmatch(r"(?:com|lpt)[1-9]", device_name)
            or re.fullmatch(r"(?:com|lpt)[¹²³]", device_name)
        ):
            raise PatchProposalError("Path contains a Windows-reserved or invalid component")
        if (
            lowered in _EXCLUDED_PARTS
            or lowered in _EXCLUDED_NAMES
            or lowered.startswith(".env.")
            or lowered.endswith((".pem", ".key", ".p12", ".pfx"))
        ):
            raise PatchProposalError("Sensitive or excluded paths cannot be patched")
    return parts


def sha256_text(content: str) -> str:
    if not isinstance(content, str):
        raise PatchProposalError("File content must be UTF-8 text")
    try:
        encoded = content.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise PatchProposalError("File content must be valid UTF-8 text") from exc
    return hashlib.sha256(encoded).hexdigest()


def build_patch_proposal(
    base_files: Mapping[str, str],
    changes: Mapping[str, str | None],
    expected_base_hashes: Mapping[str, str | None],
) -> PatchProposal:
    """Validate a complete proposed snapshot transition and return review diffs.

    New files use an expected base hash of None; updates/deletes must match the
    SHA-256 of the supplied base snapshot. Deletion is represented by None.
    """
    if (
        not isinstance(base_files, Mapping)
        or not isinstance(changes, Mapping)
        or not isinstance(expected_base_hashes, Mapping)
    ):
        raise PatchProposalError("Base snapshot and changes must be mappings")
    if not changes or len(changes) > MAX_PATCH_FILES:
        raise PatchProposalError("A proposal must contain between 1 and 20 file changes")
    if set(expected_base_hashes) != set(changes):
        raise PatchProposalError("Every changed path requires exactly one expected base hash")

    normalized: dict[str, tuple[str, ...]] = {}
    for path in changes:
        parts = _validate_path(path)
        key = path.casefold()
        if key in normalized:
            raise PatchProposalError("Case-insensitive duplicate paths are not allowed")
        normalized[key] = parts

    base_paths: dict[str, str] = {}
    for base_path in base_files:
        _validate_path(base_path)
        base_key = base_path.casefold()
        if base_key in base_paths:
            raise PatchProposalError("Base snapshot contains case-insensitive duplicate paths")
        base_paths[base_key] = base_path
    for key, parts in normalized.items():
        existing_path = base_paths.get(key)
        if existing_path is not None and existing_path != next(
            path for path in changes if path.casefold() == key
        ):
            raise PatchProposalError("Changed path collides with an existing case-insensitive path")
        for index in range(1, len(parts)):
            if "/".join(parts[:index]).casefold() in base_paths:
                raise PatchProposalError("A changed path has an existing file as a parent")
        if any(candidate.startswith(key + "/") for candidate in base_paths):
            raise PatchProposalError("A new file path would replace an existing directory")

    # A file cannot simultaneously be another changed file's parent directory.
    keys = set(normalized)
    for key, parts in normalized.items():
        for index in range(1, len(parts)):
            if "/".join(parts[:index]).casefold() in keys:
                raise PatchProposalError("A changed file cannot also be a parent directory")

    total_content = 0
    total_base = 0
    total_diff = 0
    proposed: list[ProposedFileChange] = []
    for path in sorted(changes):
        _validate_path(path)
        new_content = changes[path]
        old_content = base_files.get(path)
        expected = expected_base_hashes[path]

        if old_content is None:
            if path in base_files:
                raise PatchProposalError("Base files must contain text, not null values")
            if expected is not None:
                raise PatchProposalError("New files must use a null base hash")
            if new_content is None:
                raise PatchProposalError("A missing file cannot be deleted")
            operation = "create"
            old_hash = None
        else:
            if not isinstance(old_content, str):
                raise PatchProposalError("Base snapshot values must be UTF-8 text")
            try:
                old_encoded = old_content.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise PatchProposalError("Base files must contain valid UTF-8 text") from exc
            old_size = len(old_encoded)
            if old_size > MAX_FILE_BYTES:
                raise PatchProposalError("A base file exceeds the 1 MB limit")
            old_hash = hashlib.sha256(old_encoded).hexdigest()
            total_base += old_size
            if total_base > MAX_TOTAL_BYTES:
                raise PatchProposalError("Base snapshot exceeds the 5 MB aggregate budget")
            if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
                raise PatchProposalError("Existing files require a valid SHA-256 base hash")
            if not hmac.compare_digest(old_hash, expected):
                raise PatchProposalError("Base hash mismatch; refresh the workspace snapshot")
            operation = "delete" if new_content is None else "update"

        if new_content is not None:
            if not isinstance(new_content, str):
                raise PatchProposalError("New content must be UTF-8 text or null for deletion")
            if "\x00" in new_content:
                raise PatchProposalError("Binary content is not supported by text patch proposals")
            try:
                new_encoded = new_content.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise PatchProposalError("New content must be valid UTF-8 text") from exc
            new_size = len(new_encoded)
            if new_size > MAX_FILE_BYTES:
                raise PatchProposalError("A changed file exceeds the 1 MB limit")
            total_content += new_size
            result_hash = hashlib.sha256(new_encoded).hexdigest()
        else:
            result_hash = None

        old_text = old_content or ""
        new_text = new_content or ""
        diff = "".join(difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile="a/" + path,
            tofile="b/" + path,
        ))
        total_diff += len(diff.encode("utf-8"))
        if total_content > MAX_TOTAL_BYTES or total_diff > MAX_DIFF_BYTES:
            raise PatchProposalError("Proposal exceeds the aggregate content or diff budget")
        proposed.append(ProposedFileChange(
            path=path,
            operation=operation,
            base_sha256=old_hash,
            result_sha256=result_hash,
            content=new_content,
            unified_diff=diff,
        ))

    return PatchProposal(tuple(proposed), total_content, total_diff)
