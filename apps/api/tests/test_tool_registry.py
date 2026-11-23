from pathlib import Path

import pytest

from odei_api.services.tool_registry import ReadOnlyWorkspaceTools, ToolExecutionError
from odei_api.services.workspace_handles import WorkspaceHandleRegistry


def test_read_only_workspace_tools_list_read_and_search(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    secret = "ghp_" + "A" * 32
    (tmp_path / "src" / "main.py").write_text(
        "def hello():\n    return 'ODEI'\napi_key = \"" + secret + "\"\n",
        encoding="utf-8",
    )
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    try:
        listed = tools.execute("list_project_files", {})
        assert "src/main.py" in listed
        read = tools.execute("read_project_file", {"path": "src/main.py"})
        assert "def hello" in read
        assert secret not in read
        assert "[REDACTED]" in read
        search = tools.execute("search_project_files", {"query": "ODEI"})
        assert '"line":2' in search
        assert secret not in search
        secret_search = tools.execute("search_project_files", {"query": "api_key"})
        assert '"line":3' in secret_search
        assert secret not in secret_search
        assert (tmp_path / "src" / "main.py").read_text(encoding="utf-8").endswith('api_key = "' + secret + '"\n')
    finally:
        registry.close()


def test_read_only_workspace_tools_reject_unknown_and_extra_arguments(tmp_path: Path) -> None:
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    try:
        with pytest.raises(ToolExecutionError):
            tools.execute("run_shell", {"command": "whoami"})
        with pytest.raises(ToolExecutionError):
            tools.execute("list_project_files", {"workspace_id": "attacker"})
    finally:
        registry.close()


def test_tool_schemas_are_strict_and_do_not_accept_workspace_ids() -> None:
    schemas = ReadOnlyWorkspaceTools.schemas()
    assert {item["name"] for item in schemas} == {
        "list_project_files", "read_project_file", "search_project_files"
    }
    assert all(item["strict"] for item in schemas)
    assert all("workspace_id" not in item["parameters"]["properties"] for item in schemas)
