from pathlib import Path

import pytest

from odei_api.services.project_files import (
    BinaryProjectFile,
    ProjectFileTooLarge,
    UnsafeProjectPath,
    list_project_files,
    read_project_text_file,
    search_project_text,
)


def test_lists_files_and_excludes_secrets_and_dependencies(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "node_modules" / "dep.js").write_text("ignored", encoding="utf-8")
    (tmp_path / ".env").write_text("API_KEY=do-not-index", encoding="utf-8")
    (tmp_path / "id_rsa").write_text("private key", encoding="utf-8")

    listed = {item.path for item in list_project_files(tmp_path)}
    assert listed == {"src/main.py"}


def test_reads_utf8_text_file(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("ODEI NEXUS", encoding="utf-8")
    assert read_project_text_file(tmp_path, "hello.txt") == "ODEI NEXUS"


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "C:/Windows/win.ini"])
def test_rejects_unsafe_paths(tmp_path: Path, path: str) -> None:
    with pytest.raises(UnsafeProjectPath):
        read_project_text_file(tmp_path, path)


def test_rejects_secret_path(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")
    with pytest.raises(UnsafeProjectPath):
        read_project_text_file(tmp_path, ".env")


def test_rejects_oversized_file(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("x" * 20, encoding="utf-8")
    with pytest.raises(ProjectFileTooLarge):
        read_project_text_file(tmp_path, "large.txt", max_bytes=10)


def test_rejects_binary_file(tmp_path: Path) -> None:
    (tmp_path / "image.bin").write_bytes(b"\x00\x01\x02")
    with pytest.raises(BinaryProjectFile):
        read_project_text_file(tmp_path, "image.bin")


def test_search_returns_path_and_line(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("first\nODEI agent loop\nlast", encoding="utf-8")
    results = search_project_text(tmp_path, "agent")
    assert results == [{"path": "app.py", "line": 2, "text": "ODEI agent loop"}]


def test_does_not_follow_symlinks(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-odei.txt"
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "linked.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are unavailable in this environment")
    assert list_project_files(tmp_path) == []
    with pytest.raises(UnsafeProjectPath):
        read_project_text_file(tmp_path, "linked.txt")
