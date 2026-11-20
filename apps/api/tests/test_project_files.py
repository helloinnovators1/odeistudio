from pathlib import Path

import pytest

from odei_api.services.project_files import (
    BinaryProjectFile,
    ProjectFileError,
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


def test_respects_root_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.log\nignored_dir/\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("ok", encoding="utf-8")
    (tmp_path / "debug.log").write_text("skip", encoding="utf-8")
    (tmp_path / "ignored_dir").mkdir()
    (tmp_path / "ignored_dir" / "secret.txt").write_text("skip", encoding="utf-8")
    assert {item.path for item in list_project_files(tmp_path)} == {".gitignore", "keep.py"}


def test_respects_nested_gitignore(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / ".gitignore").write_text("generated/\n*.tmp\n", encoding="utf-8")
    (source / "main.py").write_text("ok", encoding="utf-8")
    (source / "temp.tmp").write_text("skip", encoding="utf-8")
    (source / "generated").mkdir()
    (source / "generated" / "bundle.js").write_text("skip", encoding="utf-8")
    assert {item.path for item in list_project_files(tmp_path)} == {
        "src/.gitignore", "src/main.py"
    }


def test_enforces_total_scan_byte_budget(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("12345", encoding="utf-8")
    (tmp_path / "b.txt").write_text("67890", encoding="utf-8")
    files = list_project_files(tmp_path, max_total_bytes=5)
    assert sum(item.size for item in files) <= 5


def test_does_not_follow_symlink_directory(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-odei-dir"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside", encoding="utf-8")
    link = tmp_path / "linked-dir"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable in this environment")
    assert list_project_files(tmp_path) == []
    with pytest.raises(UnsafeProjectPath):
        read_project_text_file(tmp_path, "linked-dir/secret.txt")


def test_rejects_directory_as_text_file(tmp_path: Path) -> None:
    (tmp_path / "folder").mkdir()
    with pytest.raises(ProjectFileError, match="regular file"):
        read_project_text_file(tmp_path, "folder")


def test_windows_native_open_rejects_junction_directory(tmp_path: Path) -> None:
    import os
    import subprocess

    if os.name != "nt":
        pytest.skip("Windows-only junction test")
    from odei_api.services.windows_file_handles import (
        UnsafeWindowsPath,
        open_readonly_file,
    )

    outside = tmp_path.parent / "odei-outside-junction"
    outside.mkdir()
    (outside / "secret.txt").write_text("must not be read", encoding="utf-8")
    junction = tmp_path / "junction"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("Junction creation is unavailable")
    try:
        with pytest.raises(UnsafeWindowsPath):
            open_readonly_file(tmp_path, ("junction", "secret.txt"))
    finally:
        junction.rmdir()


def test_windows_directory_handle_stays_bound_after_path_swap(tmp_path: Path) -> None:
    import os

    if os.name != "nt":
        pytest.skip("Windows-only handle enumeration test")
    from odei_api.services.windows_file_handles import (
        close_directory_handle,
        iter_directory_entries,
        open_directory_handle,
    )

    original = tmp_path / "workspace"
    original.mkdir()
    (original / "original.txt").write_text("original", encoding="utf-8")
    kernel32, handle = open_directory_handle(original)
    moved = tmp_path / "workspace-moved"
    try:
        original.rename(moved)
        original.mkdir()
        (original / "attacker.txt").write_text("attacker", encoding="utf-8")
        names = {name for name, _attributes, _size in iter_directory_entries(handle)}
        assert "original.txt" in names
        assert "attacker.txt" not in names
    finally:
        close_directory_handle(kernel32, handle)


def test_windows_listing_skips_junctions(tmp_path: Path) -> None:
    import os
    import subprocess

    if os.name != "nt":
        pytest.skip("Windows-only junction test")
    outside = tmp_path.parent / "odei-list-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    junction = tmp_path / "linked"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("Junction creation is unavailable")
    try:
        listed = list_project_files(tmp_path)
        assert all(not item.path.startswith("linked/") for item in listed)
    finally:
        junction.rmdir()


def test_posix_listing_skips_fifo_without_blocking(tmp_path: Path) -> None:
    import os

    if os.name != "posix" or not hasattr(os, "mkfifo"):
        pytest.skip("POSIX FIFO test")
    fifo = tmp_path / "named-pipe"
    os.mkfifo(fifo)
    (tmp_path / "regular.txt").write_text("safe", encoding="utf-8")
    listed = {item.path for item in list_project_files(tmp_path)}
    assert listed == {"regular.txt"}


def test_posix_retained_root_descriptor_survives_path_replacement(tmp_path: Path) -> None:
    import os

    if os.name != "posix":
        pytest.skip("POSIX retained-root test")
    from odei_api.services.project_files import (
        list_project_files_from_posix_fd,
        read_project_text_file_from_posix_fd,
    )

    selected = tmp_path / "selected"
    selected.mkdir()
    (selected / "main.py").write_text("original", encoding="utf-8")
    root_fd = os.open(selected, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    moved = tmp_path / "selected-moved"
    try:
        selected.rename(moved)
        selected.mkdir()
        (selected / "attacker.py").write_text("replacement", encoding="utf-8")
        assert {item.path for item in list_project_files_from_posix_fd(root_fd)} == {
            "main.py"
        }
        assert read_project_text_file_from_posix_fd(root_fd, "main.py") == "original"
    finally:
        os.close(root_fd)


def test_windows_retained_root_handle_survives_path_replacement(tmp_path: Path) -> None:
    import os

    if os.name != "nt":
        pytest.skip("Windows retained-root test")
    from odei_api.services.project_files import (
        list_project_files_from_windows_handle,
        read_project_text_file_from_windows_handle,
    )
    from odei_api.services.windows_file_handles import (
        close_directory_handle,
        open_directory_handle,
    )

    selected = tmp_path / "selected"
    selected.mkdir()
    (selected / "main.py").write_text("original", encoding="utf-8")
    kernel32, root_handle = open_directory_handle(selected)
    moved = tmp_path / "selected-moved"
    try:
        selected.rename(moved)
        selected.mkdir()
        (selected / "attacker.py").write_text("replacement", encoding="utf-8")
        assert {item.path for item in list_project_files_from_windows_handle(root_handle)} == {
            "main.py"
        }
        assert read_project_text_file_from_windows_handle(root_handle, "main.py") == "original"
    finally:
        close_directory_handle(kernel32, root_handle)


def test_workspace_handle_registry_survives_root_replacement_and_revokes(
    tmp_path: Path,
) -> None:
    from odei_api.services.workspace_handles import (
        WorkspaceHandleRegistry,
        WorkspaceNotFound,
    )

    selected = tmp_path / "selected-workspace"
    selected.mkdir()
    (selected / "main.py").write_text("trusted source", encoding="utf-8")
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(selected)
    moved = tmp_path / "selected-workspace-moved"
    try:
        selected.rename(moved)
        selected.mkdir()
        (selected / "attacker.py").write_text("replacement", encoding="utf-8")
        assert {item.path for item in registry.list_files(workspace_id)} == {"main.py"}
        assert registry.read_text(workspace_id, "main.py") == "trusted source"
        assert registry.revoke(workspace_id) is True
        assert registry.revoke(workspace_id) is False
        with pytest.raises(WorkspaceNotFound):
            registry.list_files(workspace_id)
    finally:
        registry.close()
