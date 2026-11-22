from __future__ import annotations

import io
import stat
import zipfile

import pytest

from odei_api.services.workspace_snapshots import SnapshotError, WorkspaceSnapshotIngestor


def make_zip(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return stream.getvalue()


def test_ingests_regular_files_and_hashes_content_deterministically(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    ingestor = WorkspaceSnapshotIngestor(root)
    archive = make_zip([("src/main.py", b"print('ok')"), ("README.md", b"hello")])
    first = ingestor.ingest(archive)
    second = ingestor.ingest(archive)
    assert first.file_count == 2
    assert first.total_bytes == len(b"print('ok')") + len(b"hello")
    assert first.sha256 == second.sha256
    assert (first.path / "src" / "main.py").read_bytes() == b"print('ok')"


@pytest.mark.parametrize("name", [
    "../escape.txt", "/absolute.txt", "C:/drive.txt", "a//b.txt",
    "a/./b.txt", "a/../b.txt", "folder\\\\evil.txt", "NUL.txt", "bad?.txt",
])
def test_rejects_unsafe_or_nonportable_paths(tmp_path, name):
    root = tmp_path / "workspaces"
    root.mkdir()
    with pytest.raises(SnapshotError):
        WorkspaceSnapshotIngestor(root).ingest(make_zip([(name, b"x")]))


def test_rejects_case_insensitive_duplicate_paths(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    archive = make_zip([("Readme.txt", b"a"), ("README.TXT", b"b")])
    with pytest.raises(SnapshotError, match="duplicate"):
        WorkspaceSnapshotIngestor(root).ingest(archive)


def test_rejects_file_directory_prefix_conflict(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    archive = make_zip([("node", b"file"), ("node/index.js", b"child")])
    with pytest.raises(SnapshotError, match="conflicts"):
        WorkspaceSnapshotIngestor(root).ingest(archive)


def test_rejects_symlink_metadata(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target")
    with pytest.raises(SnapshotError, match="link or special"):
        WorkspaceSnapshotIngestor(root).ingest(stream.getvalue())


def test_rejects_compression_bomb_ratio_and_expanded_limits(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    archive = make_zip([("large.txt", b"A" * 100_000)])
    with pytest.raises(SnapshotError, match="compression-ratio"):
        WorkspaceSnapshotIngestor(root, max_compression_ratio=5).ingest(archive)
    with pytest.raises(SnapshotError, match="per-file"):
        WorkspaceSnapshotIngestor(root, max_file_bytes=100).ingest(make_zip([("large.txt", b"x" * 101)]))


def test_rejects_invalid_zip_and_archive_size(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    ingestor = WorkspaceSnapshotIngestor(root, max_archive_bytes=10)
    with pytest.raises(SnapshotError, match="compressed-size"):
        ingestor.ingest(b"x" * 11)
    with pytest.raises(SnapshotError, match="valid ZIP"):
        WorkspaceSnapshotIngestor(root).ingest(b"not a zip")
