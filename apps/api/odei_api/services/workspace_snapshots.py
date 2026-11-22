"""Safe ingestion of bounded ZIP workspace snapshots for trusted workers."""
from __future__ import annotations

import hashlib
import io
import os
import pathlib
import shutil
import stat
import zipfile
from dataclasses import dataclass
from uuid import uuid4

_MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
_MAX_FILES = 10_000
_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_RATIO = 100
_ALLOWED_COMPRESSION = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
_RESERVED_WINDOWS = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}
_SENSITIVE_DIRECTORIES = {".git", ".ssh", ".aws", ".azure", ".kube", ".gnupg"}
_ALLOWED_ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template", ".env.dist"}
_SENSITIVE_NAMES = {
    ".npmrc", ".pypirc", ".netrc", ".git-credentials", "credentials",
    "credentials.json", "secrets.json", "id_rsa", "id_ed25519",
}


class SnapshotError(ValueError):
    """The supplied archive is malformed, unsafe or exceeds snapshot policy."""


@dataclass(frozen=True)
class SnapshotRecord:
    id: str
    path: pathlib.Path
    sha256: str
    file_count: int
    total_bytes: int


class WorkspaceSnapshotIngestor:
    """Extract only regular files into a fresh direct child of a trusted worker root."""

    def __init__(
        self,
        workspace_root: str | pathlib.Path,
        *,
        max_archive_bytes: int = _MAX_ARCHIVE_BYTES,
        max_files: int = _MAX_FILES,
        max_file_bytes: int = _MAX_FILE_BYTES,
        max_total_bytes: int = _MAX_TOTAL_BYTES,
        max_compression_ratio: int = _MAX_RATIO,
    ) -> None:
        supplied = pathlib.Path(workspace_root)
        if supplied.is_symlink() or not supplied.is_dir():
            raise ValueError("workspace root must be an existing real directory")
        self.root = supplied.resolve(strict=True)
        self.max_archive_bytes = max_archive_bytes
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.max_compression_ratio = max_compression_ratio
        if not (1 <= max_archive_bytes <= _MAX_ARCHIVE_BYTES):
            raise ValueError("archive byte limit is invalid")
        if not (1 <= max_files <= _MAX_FILES):
            raise ValueError("file-count limit is invalid")
        if not (1 <= max_file_bytes <= _MAX_FILE_BYTES):
            raise ValueError("per-file byte limit is invalid")
        if not (1 <= max_total_bytes <= _MAX_TOTAL_BYTES):
            raise ValueError("aggregate byte limit is invalid")
        if not (1 <= max_compression_ratio <= _MAX_RATIO):
            raise ValueError("compression-ratio limit is invalid")

    @staticmethod
    def _safe_parts(name: str, *, is_directory: bool) -> tuple[str, ...]:
        if not isinstance(name, str) or not name or len(name) > 1024:
            raise SnapshotError("archive entry name is invalid")
        if "\x00" in name or "\\" in name or name.startswith("/"):
            raise SnapshotError("archive entry uses an unsafe path")
        raw = name[:-1] if is_directory and name.endswith("/") else name
        parts = raw.split("/")
        if not raw or any(part in {"", ".", ".."} for part in parts):
            raise SnapshotError("archive entry contains traversal or empty path segments")
        lowered = tuple(part.casefold() for part in parts)
        basename = lowered[-1]
        if any(part in _SENSITIVE_DIRECTORIES for part in lowered):
            raise SnapshotError("snapshot contains a sensitive metadata or credential directory")
        if basename in _SENSITIVE_NAMES or basename.endswith((".pem", ".key", ".p12", ".pfx", ".jks")):
            raise SnapshotError("snapshot contains a credential or private-key file")
        if basename.startswith(".env") and basename not in _ALLOWED_ENV_TEMPLATES:
            raise SnapshotError("snapshot contains an environment file that may hold secrets")
        if basename.startswith("service-account") and basename.endswith(".json"):
            raise SnapshotError("snapshot contains a service-account credential file")
        if basename.endswith("-credentials.json"):
            raise SnapshotError("snapshot contains a credential file")
        if lowered[:2] == (".docker", "config.json"):
            raise SnapshotError("snapshot contains Docker registry credentials")
        for part in parts:
            if (
                part.endswith((".", " "))
                or any(char in part for char in '<>:"|?*')
                or part.split(".", 1)[0].upper() in _RESERVED_WINDOWS
            ):
                raise SnapshotError("archive entry contains a non-portable path component")
        return tuple(parts)

    def _inspect(self, archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, tuple[str, ...], bool]]:
        infos = archive.infolist()
        if len(infos) > self.max_files:
            raise SnapshotError("archive contains too many entries")
        entries: list[tuple[zipfile.ZipInfo, tuple[str, ...], bool]] = []
        seen: set[str] = set()
        file_paths: set[tuple[str, ...]] = set()
        total = 0
        for info in infos:
            is_directory = info.is_dir()
            parts = self._safe_parts(info.filename, is_directory=is_directory)
            normalized = "/".join(parts).casefold()
            if normalized in seen:
                raise SnapshotError("archive contains duplicate normalized paths")
            seen.add(normalized)
            mode = (info.external_attr >> 16) & 0xFFFF
            kind = stat.S_IFMT(mode)
            if kind == stat.S_IFLNK or kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise SnapshotError("archive contains a link or special filesystem entry")
            if is_directory and info.file_size:
                raise SnapshotError("directory entries must be empty")
            if not is_directory:
                if kind == stat.S_IFDIR:
                    raise SnapshotError("file entry has directory metadata")
                if info.file_size < 0 or info.file_size > self.max_file_bytes:
                    raise SnapshotError("archive file exceeds the per-file size limit")
                if info.file_size and (
                    info.compress_size <= 0
                    or info.file_size / info.compress_size > self.max_compression_ratio
                ):
                    raise SnapshotError("archive entry exceeds the compression-ratio limit")
                if info.flag_bits & 0x1:
                    raise SnapshotError("encrypted ZIP entries are not supported")
                if info.compress_type not in _ALLOWED_COMPRESSION:
                    raise SnapshotError("archive uses an unsupported compression method")
                total += info.file_size
                if total > self.max_total_bytes:
                    raise SnapshotError("archive exceeds the aggregate expanded-size limit")
                file_paths.add(parts)
            entries.append((info, parts, is_directory))
        for _info, parts, is_directory in entries:
            if is_directory:
                continue
            for index in range(1, len(parts)):
                if parts[:index] in file_paths:
                    raise SnapshotError("archive path conflicts with a regular file")
        return entries

    def ingest(self, archive_bytes: bytes) -> SnapshotRecord:
        if not isinstance(archive_bytes, bytes) or not archive_bytes:
            raise SnapshotError("snapshot archive must be non-empty bytes")
        if len(archive_bytes) > self.max_archive_bytes:
            raise SnapshotError("snapshot archive exceeds the compressed-size limit")
        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_bytes), mode="r")
        except (zipfile.BadZipFile, OSError) as exc:
            raise SnapshotError("snapshot archive is not a valid ZIP file") from exc

        snapshot_id = uuid4().hex
        destination = self.root / snapshot_id
        file_digests: list[tuple[str, int, str]] = []
        total_written = 0
        destination_created = False
        try:
            entries = self._inspect(archive)
            destination.mkdir(mode=0o700, parents=False, exist_ok=False)
            destination_created = True
            for info, parts, is_directory in entries:
                target = destination.joinpath(*parts)
                if is_directory:
                    target.mkdir(mode=0o700, parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                for parent in (target.parent, *target.parent.parents):
                    if parent == destination.parent:
                        break
                    if parent.is_symlink() or not parent.is_dir():
                        raise SnapshotError("snapshot destination changed during extraction")
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(target, flags, 0o600)
                digest = hashlib.sha256()
                written = 0
                try:
                    with archive.open(info, "r") as source, os.fdopen(descriptor, "wb") as output:
                        while True:
                            chunk = source.read(64 * 1024)
                            if not chunk:
                                break
                            written += len(chunk)
                            total_written += len(chunk)
                            if written > self.max_file_bytes or total_written > self.max_total_bytes:
                                raise SnapshotError("expanded snapshot exceeded its size limit")
                            digest.update(chunk)
                            output.write(chunk)
                    if written != info.file_size:
                        raise SnapshotError("archive entry size did not match its metadata")
                except Exception:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                    raise
                file_digests.append(("/".join(parts), written, digest.hexdigest()))

            manifest = hashlib.sha256()
            for name, size, digest in sorted(file_digests):
                manifest.update(name.encode("utf-8"))
                manifest.update(b"\0")
                manifest.update(str(size).encode("ascii"))
                manifest.update(b"\0")
                manifest.update(digest.encode("ascii"))
                manifest.update(b"\n")
            return SnapshotRecord(
                id=snapshot_id, path=destination, sha256=manifest.hexdigest(),
                file_count=len(file_digests), total_bytes=total_written,
            )
        except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
            if destination_created:
                shutil.rmtree(destination, ignore_errors=True)
            raise SnapshotError("snapshot archive could not be safely extracted") from exc
        except Exception:
            if destination_created:
                shutil.rmtree(destination, ignore_errors=True)
            raise
        finally:
            archive.close()
