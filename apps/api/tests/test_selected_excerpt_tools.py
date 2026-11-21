import json

import pytest

from odei_api.services.selected_excerpt_tools import SelectedExcerptToolError, SelectedExcerptTools


def test_selected_excerpt_tools_list_read_search_only_user_attached_files():
    secret = "sk-proj-" + "A" * 28
    tools = SelectedExcerptTools([
        {"path": "src/main.py", "content": "def hello():\n    return 'ODEI'\napi_key=" + secret},
        {"path": "README.md", "content": "# ODEI Studio\nRead-only workspace"},
    ])
    listed = json.loads(tools.execute("list_attached_excerpts", {}))
    assert {item["path"] for item in listed["files"]} == {"src/main.py", "README.md"}
    assert listed["scope"] == "user_attached_excerpts_only"

    read = json.loads(tools.execute("read_attached_excerpt", {"path": "src/main.py"}))
    assert "def hello" in read["content"]
    assert secret not in read["content"]
    assert "[REDACTED]" in read["content"]

    search = json.loads(tools.execute("search_attached_excerpts", {"query": "odei"}))
    assert len(search["matches"]) == 2
    assert all(item["path"] in {"src/main.py", "README.md"} for item in search["matches"])


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "C:/secret.txt", "src\\..\\outside.txt", ""])
def test_selected_excerpt_tools_reject_unsafe_paths(path):
    with pytest.raises(SelectedExcerptToolError):
        SelectedExcerptTools([{"path": path, "content": "x"}])


def test_selected_excerpt_tools_reject_unattached_paths_and_unregistered_tools():
    tools = SelectedExcerptTools([{"path": "src/main.py", "content": "print('ok')"}])
    with pytest.raises(SelectedExcerptToolError, match="not attached"):
        tools.execute("read_attached_excerpt", {"path": "src/secret.env"})
    with pytest.raises(SelectedExcerptToolError, match="not registered"):
        tools.execute("run_shell", {"command": "whoami"})
    with pytest.raises(SelectedExcerptToolError):
        tools.execute("list_attached_excerpts", {"workspace_id": "attacker"})


def test_selected_excerpt_tool_schemas_are_strict_and_do_not_accept_workspace_ids():
    schemas = SelectedExcerptTools.schemas()
    assert {item["name"] for item in schemas} == {
        "list_attached_excerpts", "read_attached_excerpt", "search_attached_excerpts",
        "propose_attached_file_change",
    }
    assert all(item["strict"] for item in schemas)
    assert all("workspace_id" not in item["parameters"]["properties"] for item in schemas)


def test_selected_excerpt_tools_capture_review_only_replacement_without_mutating_base():
    original = "def greet():\\n    return 'hello'\\n"
    tools = SelectedExcerptTools([{"path": "src/greet.py", "content": original}])
    captured = json.loads(tools.execute(
        "propose_attached_file_change",
        {"path": "src/greet.py", "content": "def greet():\\n    return 'hello, ODEI'\\n"},
    ))
    assert captured["proposal_captured"] is True
    assert captured["mode"] == "review_only"
    assert captured["writes_performed"] is False
    assert tools.proposal_base_files == {"src/greet.py": original}
    assert tools.proposed_changes == {"src/greet.py": "def greet():\\n    return 'hello, ODEI'\\n"}
    assert tools.execute("read_attached_excerpt", {"path": "src/greet.py"})
    assert tools.proposal_base_files["src/greet.py"] == original


def test_selected_excerpt_tools_cannot_propose_unattached_or_duplicate_paths():
    tools = SelectedExcerptTools([{"path": "src/greet.py", "content": "print('hello')"}])
    with pytest.raises(SelectedExcerptToolError, match="Only an explicitly attached"):
        tools.execute("propose_attached_file_change", {
            "path": "src/other.py", "content": "print('changed')",
        })
    tools.execute("propose_attached_file_change", {
        "path": "src/greet.py", "content": "print('changed')",
    })
    with pytest.raises(SelectedExcerptToolError, match="already exists"):
        tools.execute("propose_attached_file_change", {
            "path": "src/greet.py", "content": "print('changed again')",
        })
