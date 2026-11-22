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

@pytest.mark.parametrize("name", [
    ".env", ".env.production", ".aws/credentials", ".ssh/id_rsa",
    "private.pem", "signing.key", ".docker/config.json", "service-account-prod.json",
])
def test_rejects_known_secret_and_credential_paths(tmp_path, name):
    root = tmp_path / "workspaces"
    root.mkdir()
    with pytest.raises(SnapshotError, match="credential|private-key|environment|sensitive"):
        WorkspaceSnapshotIngestor(root).ingest(make_zip([(name, b"secret material")]))


def test_allows_documented_environment_templates(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    record = WorkspaceSnapshotIngestor(root).ingest(
        make_zip([(".env.example", b"API_URL=https://example.invalid")])
    )
    assert (record.path / ".env.example").is_file()


def test_enforces_entry_count_and_aggregate_expanded_size(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    too_many = make_zip([("a.txt", b"a"), ("b.txt", b"b")])
    with pytest.raises(SnapshotError, match="too many"):
        WorkspaceSnapshotIngestor(root, max_files=1).ingest(too_many)
    expanded = make_zip([("a.txt", b"a" * 40), ("b.txt", b"b" * 40)])
    with pytest.raises(SnapshotError, match="aggregate"):
        WorkspaceSnapshotIngestor(root, max_total_bytes=64).ingest(expanded)

@pytest.mark.parametrize("secret", [
    b"AKIA1234567890ABCDEF",
    b"github_pat_abcdefghijklmnopqrstuvwxyz1234567890",
    b"client_secret=super_secret_value_that_is_long_enough",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"xoxb-12345678901234567890",
])
def test_rejects_likely_credential_material_inside_file_content(tmp_path, secret):
    root = tmp_path / "workspaces"
    root.mkdir()
    archive = make_zip([("src/config.txt", secret)])
    with pytest.raises(SnapshotError, match="likely credential"):
        WorkspaceSnapshotIngestor(root).ingest(archive)
    assert list(root.iterdir()) == []


def test_secret_scanner_detects_patterns_split_across_stream_chunks(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as zipped:
        zipped.writestr("src/config.txt", b" " * 65_533 + b"api_key=" + b"x" * 40)
    archive = stream.getvalue()
    with pytest.raises(SnapshotError, match="likely credential"):
        WorkspaceSnapshotIngestor(root).ingest(archive)
    assert list(root.iterdir()) == []


def test_secret_scanner_allows_short_documentation_placeholders(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    record = WorkspaceSnapshotIngestor(root).ingest(
        make_zip([(".env.example", b"API_KEY=replace-me")])
    )
    assert record.file_count == 1
