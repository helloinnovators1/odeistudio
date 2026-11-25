from __future__ import annotations

import pytest

from odei_api.services.repository_index import RepositoryIndex, RepositoryIndexError


def test_indexes_text_and_returns_exact_search_provenance(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("alpha\nneedle here\nomega\n", encoding="utf-8")
    index = RepositoryIndex(tmp_path)
    update = index.rebuild_or_update()

    assert update.indexed == 1
    assert update.changed == 1
    hit, = index.search("needle")
    assert (hit.path, hit.line, hit.snippet) == ("src/main.py", 2, "needle here")
    assert hit.sha256 == index.file_provenance("src/main.py")["sha256"]
    assert hit.index_revision == update.revision


def test_incremental_update_skips_unchanged_and_removes_deleted_files(tmp_path):
    file = tmp_path / "a.py"
    file.write_text("one\n", encoding="utf-8")
    index = RepositoryIndex(tmp_path)
    first = index.rebuild_or_update()
    second = index.rebuild_or_update()
    assert second.changed == 0
    assert second.unchanged == 1
    assert second.revision == first.revision

    file.write_text("two\n", encoding="utf-8")
    third = index.rebuild_or_update()
    assert third.changed == 1
    assert third.revision > second.revision
    file.unlink()
    fourth = index.rebuild_or_update()
    assert fourth.removed == 1
    assert index.search("two") == []


def test_excludes_generated_credentials_and_likely_secret_content(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("ignored", encoding="utf-8")
    (tmp_path / ".env").write_text("PASSWORD=do-not-index-this-value", encoding="utf-8")
    (tmp_path / ".env.example").write_text("API_URL=https://example.invalid", encoding="utf-8")
    (tmp_path / "private.py").write_text(
        'token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"\n', encoding="utf-8"
    )
    (tmp_path / "safe.py").write_text("print('safe')\n", encoding="utf-8")

    index = RepositoryIndex(tmp_path)
    result = index.rebuild_or_update()
    assert result.indexed == 2
    assert index.search("safe")
    assert index.search("ghp_") == []
    assert index.file_provenance(".env") is None
    assert index.file_provenance("node_modules/dep.js") is None


def test_skips_binary_and_oversized_files(tmp_path):
    (tmp_path / "binary.dat").write_bytes(b"hello\x00world")
    (tmp_path / "large.txt").write_text("x" * 100, encoding="utf-8")
    index = RepositoryIndex(tmp_path, max_file_bytes=10)
    result = index.rebuild_or_update()
    assert result.indexed == 0
    assert result.skipped == 2


def test_rejects_symlink_workspace_and_does_not_follow_file_symlinks(tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("outside marker", encoding="utf-8")
    root = tmp_path / "workspace"
    root.mkdir()
    try:
        (root / "linked.txt").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")
    index = RepositoryIndex(root)
    index.rebuild_or_update()
    assert index.search("outside marker") == []
    with pytest.raises(RepositoryIndexError):
        RepositoryIndex(root / "linked.txt")


def test_search_validates_limits_and_invalid_regex(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    index = RepositoryIndex(tmp_path)
    index.rebuild_or_update()
    with pytest.raises(RepositoryIndexError):
        index.search("")
    with pytest.raises(RepositoryIndexError):
        index.search("[", regex=True)
    with pytest.raises(RepositoryIndexError):
        index.search("hello", limit=101)


def test_clear_drops_content_and_advances_revision(tmp_path):
    (tmp_path / "a.txt").write_text("classified source", encoding="utf-8")
    index = RepositoryIndex(tmp_path)
    index.rebuild_or_update()
    previous = index.revision
    index.clear()
    assert index.revision == previous + 1
    assert index.search("classified") == []
    assert index.file_provenance("a.txt") is None


def test_rejects_hard_linked_files_to_avoid_indexing_external_content(tmp_path):
    source = tmp_path.parent / "outside-sensitive.txt"
    source.write_text("external private material", encoding="utf-8")
    root = tmp_path / "workspace"
    root.mkdir()
    try:
        (root / "linked.txt").hardlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("hard links are unavailable on this platform")

    index = RepositoryIndex(root)
    result = index.rebuild_or_update()

    assert result.indexed == 0
    assert result.skipped == 1
    assert index.search("external private material") == []


def test_descriptor_reader_rejects_final_symlink_even_when_target_is_inside_root(tmp_path):
    from odei_api.services.repository_index import _read_index_file

    target = tmp_path / "target.txt"
    target.write_text("must not be reached through a link", encoding="utf-8")
    link = tmp_path / "linked.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")

    with pytest.raises(OSError):
        _read_index_file(tmp_path, link, 1024)
