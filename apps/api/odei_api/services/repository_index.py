"""Bounded, provenance-aware local repository index primitives for NEXUS.

This module deliberately has no database or embedding-provider dependency. It builds a
project-local, in-memory index from an already-authorized workspace root. Persistence,
tenant binding and semantic retrieval must be supplied by a separately authorized
store/adapter; callers must not treat this index as an authorization boundary.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_MAX_FILES = 5_000
_MAX_FILE_BYTES = 1_048_576
_MAX_TOTAL_BYTES = 64 * 1024 * 1024
_MAX_QUERY_LENGTH = 512
_MAX_RESULTS = 100
_IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".next", ".nuxt", ".turbo", "node_modules",
    "vendor", "dist", "build", "coverage", ".venv", "venv", "target",
    ".ssh", ".aws", ".azure", ".kube", ".gnupg",
}
_IGNORED_FILES = {
    ".npmrc", ".pypirc", ".netrc", ".git-credentials", "credentials",
    "credentials.json", "secrets.json", "id_rsa", "id_ed25519",
}
_ALLOWED_ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template", ".env.dist"}
_SECRET_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})\b",
    r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b",
    r"\bAIza[0-9A-Za-z_-]{35}\b",
    r"\b(?:aws_secret_access_key|client_secret|api_key|secret_key|access_token|refresh_token|password)\s*[:=]\s*['\"]?[A-Za-z0-9/+_=-]{24,}",
))


class RepositoryIndexError(ValueError):
    """The requested repository index operation violates safety or resource limits."""


@dataclass(frozen=True)
class IndexedFile:
    path: str
    sha256: str
    size_bytes: int
    line_count: int
    _content: str


@dataclass(frozen=True)
class SearchHit:
    path: str
    line: int
    snippet: str
    sha256: str
    index_revision: int


@dataclass(frozen=True)
class IndexUpdate:
    revision: int
    indexed: int
    changed: int
    unchanged: int
    removed: int
    skipped: int
    total_bytes: int


def _excluded(relative: Path, *, is_directory: bool) -> bool:
    parts = relative.parts
    lowered = tuple(part.casefold() for part in parts)
    if any(part in _IGNORED_DIRS for part in lowered[:-1] if not is_directory):
        return True
    if is_directory and lowered[-1] in _IGNORED_DIRS:
        return True
    name = lowered[-1]
    if name in _IGNORED_FILES or name.endswith((".pem", ".key", ".p12", ".pfx", ".jks")):
        return True
    if name.startswith(".env") and name not in _ALLOWED_ENV_TEMPLATES:
        return True
    if name.startswith("service-account") and name.endswith(".json"):
        return True
    if name.endswith("-credentials.json"):
        return True
    return False


def _contains_secret(content: str) -> bool:
    return any(pattern.search(content) for pattern in _SECRET_PATTERNS)


class RepositoryIndex:
    """Incremental exact-search index rooted at one already-authorized workspace.

    The index stores bounded text in process memory. Recreate it after process restart;
    do not share instances between tenants or projects.
    """

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        max_files: int = _MAX_FILES,
        max_file_bytes: int = _MAX_FILE_BYTES,
        max_total_bytes: int = _MAX_TOTAL_BYTES,
    ) -> None:
        supplied = Path(workspace_root)
        if supplied.is_symlink() or not supplied.is_dir():
            raise RepositoryIndexError("workspace root must be an existing real directory")
        self.root = supplied.resolve(strict=True)
        if not (1 <= max_files <= _MAX_FILES):
            raise ValueError("max_files is outside the supported range")
        if not (1 <= max_file_bytes <= _MAX_FILE_BYTES):
            raise ValueError("max_file_bytes is outside the supported range")
        if not (1 <= max_total_bytes <= _MAX_TOTAL_BYTES):
            raise ValueError("max_total_bytes is outside the supported range")
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self._files: dict[str, IndexedFile] = {}
        self._revision = 0

    @property
    def revision(self) -> int:
        return self._revision

    def _walk(self) -> Iterable[Path]:
        for current, directories, filenames in os.walk(self.root, topdown=True, followlinks=False):
            current_path = Path(current)
            safe_directories = []
            for name in sorted(directories):
                candidate = current_path / name
                relative = candidate.relative_to(self.root)
                try:
                    info = candidate.lstat()
                except OSError:
                    continue
                if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not _excluded(relative, is_directory=True):
                    safe_directories.append(name)
            directories[:] = safe_directories
            for name in sorted(filenames):
                candidate = current_path / name
                relative = candidate.relative_to(self.root)
                if _excluded(relative, is_directory=False):
                    continue
                try:
                    info = candidate.lstat()
                except OSError:
                    continue
                if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                    yield candidate

    def rebuild_or_update(self) -> IndexUpdate:
        discovered: dict[str, IndexedFile] = {}
        total_bytes = 0
        skipped = 0
        changed = 0
        unchanged = 0

        for path in self._walk():
            relative = path.relative_to(self.root).as_posix()
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(self.root)
                before = path.lstat()
                if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
                    skipped += 1
                    continue
                if before.st_size > self.max_file_bytes:
                    skipped += 1
                    continue
                total_bytes += before.st_size
                if total_bytes > self.max_total_bytes or len(discovered) >= self.max_files:
                    raise RepositoryIndexError("repository exceeds configured indexing limits")
                raw = path.read_bytes()
                after = path.lstat()
                if (
                    before.st_ino != after.st_ino
                    or before.st_dev != after.st_dev
                    or before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns
                    or len(raw) != before.st_size
                ):
                    skipped += 1
                    continue
                if b"\x00" in raw:
                    skipped += 1
                    continue
                try:
                    content = raw.decode("utf-8")
                except UnicodeDecodeError:
                    skipped += 1
                    continue
                if _contains_secret(content):
                    skipped += 1
                    continue
                digest = hashlib.sha256(raw).hexdigest()
                previous = self._files.get(relative)
                if previous is not None and previous.sha256 == digest:
                    discovered[relative] = previous
                    unchanged += 1
                else:
                    discovered[relative] = IndexedFile(
                        path=relative, sha256=digest, size_bytes=len(raw),
                        line_count=len(content.splitlines()), _content=content,
                    )
                    changed += 1
            except FileNotFoundError:
                skipped += 1
                continue
            except OSError:
                skipped += 1
                continue

        removed = len(set(self._files) - set(discovered))
        if changed or removed or not self._revision:
            self._revision += 1
        self._files = discovered
        return IndexUpdate(
            revision=self._revision, indexed=len(discovered), changed=changed,
            unchanged=unchanged, removed=removed, skipped=skipped, total_bytes=total_bytes,
        )

    def search(
        self,
        query: str,
        *,
        regex: bool = False,
        case_sensitive: bool = True,
        limit: int = 20,
    ) -> list[SearchHit]:
        if not isinstance(query, str) or not query or len(query) > _MAX_QUERY_LENGTH:
            raise RepositoryIndexError("search query must contain 1 to 512 characters")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= _MAX_RESULTS:
            raise RepositoryIndexError("search limit must be between 1 and 100")
        try:
            pattern = re.compile(query if regex else re.escape(query), 0 if case_sensitive else re.IGNORECASE)
        except re.error as exc:
            raise RepositoryIndexError("search expression is invalid") from exc

        hits: list[SearchHit] = []
        for relative in sorted(self._files):
            record = self._files[relative]
            for line_number, line in enumerate(record._content.splitlines(), start=1):
                if pattern.search(line):
                    hits.append(SearchHit(
                        path=record.path, line=line_number, snippet=line[:500],
                        sha256=record.sha256, index_revision=self._revision,
                    ))
                    if len(hits) >= limit:
                        return hits
        return hits

    def file_provenance(self, path: str) -> dict[str, str | int] | None:
        """Return metadata only; never expose indexed source content."""
        record = self._files.get(path)
        if record is None:
            return None
        return {
            "path": record.path, "sha256": record.sha256,
            "size_bytes": record.size_bytes, "line_count": record.line_count,
            "index_revision": self._revision,
        }

    def clear(self) -> None:
        """Drop all indexed source text and advance the revision."""
        self._files.clear()
        self._revision += 1
