from types import SimpleNamespace

import pytest

from odei_api.services.agent_runtime import AgentRuntimeError, run_nexus_agent
from odei_api.services.tool_registry import ReadOnlyWorkspaceTools
from odei_api.services.workspace_handles import WorkspaceHandleRegistry


class FakeResponses:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self._responses)


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


def _response(response_id, output, output_text=""):
    return SimpleNamespace(id=response_id, output=output, output_text=output_text)


def test_agent_executes_only_registered_read_tools_and_returns_final_answer(tmp_path) -> None:
    source = tmp_path / "main.py"
    source.write_text("print('ODEI')\n", encoding="utf-8")
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    client = FakeClient([
        _response("resp_1", [
            SimpleNamespace(
                type="function_call", name="read_project_file",
                arguments='{"path":"main.py"}', call_id="call_1",
            )
        ]),
        _response("resp_2", [SimpleNamespace(type="message")], "The project prints ODEI."),
    ])
    try:
        result = run_nexus_agent(
            client, model="test-model", task="Explain main.py", workspace_tools=tools
        )
        assert result.answer == "The project prints ODEI."
        assert result.tool_calls == 1
        assert result.tool_rounds == 1
        assert "tools" in client.responses.calls[0]
        assert client.responses.calls[1]["previous_response_id"] == "resp_1"
        outputs = client.responses.calls[1]["input"]
        assert outputs[0]["type"] == "function_call_output"
        assert "print('ODEI')" in outputs[0]["output"]
        assert source.read_text(encoding="utf-8") == "print('ODEI')\n"
    finally:
        registry.close()


def test_agent_rejects_empty_and_oversized_tasks(tmp_path) -> None:
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    try:
        with pytest.raises(ValueError):
            run_nexus_agent(FakeClient([]), model="model", task=" ", workspace_tools=tools)
        with pytest.raises(ValueError):
            run_nexus_agent(FakeClient([]), model="model", task="x" * 8001, workspace_tools=tools)
    finally:
        registry.close()


def test_agent_rejects_missing_final_answer(tmp_path) -> None:
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    client = FakeClient([_response("resp_final", [SimpleNamespace(type="message")], " ")])
    try:
        with pytest.raises(AgentRuntimeError, match="no final answer"):
            run_nexus_agent(client, model="model", task="Explain", workspace_tools=tools)
    finally:
        registry.close()


def test_agent_fails_closed_on_missing_response_id(tmp_path) -> None:
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    client = FakeClient([
        _response(None, [
            SimpleNamespace(type="function_call", name="list_project_files", arguments="{}", call_id="call_1")
        ])
    ])
    try:
        with pytest.raises(AgentRuntimeError, match="response ID"):
            run_nexus_agent(client, model="model", task="List files", workspace_tools=tools)
    finally:
        registry.close()
