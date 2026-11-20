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


def _response(output, output_text=""):
    return SimpleNamespace(output=output, output_text=output_text)


def test_agent_executes_only_registered_read_tools_and_replays_stateless_history(tmp_path) -> None:
    source = tmp_path / "main.py"
    source.write_text("print('ODEI')\n", encoding="utf-8")
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    client = FakeClient([
        _response([
            SimpleNamespace(
                type="function_call", name="read_project_file",
                arguments='{"path":"main.py"}', call_id="call_1",
            )
        ]),
        _response([SimpleNamespace(type="message")], "The project prints ODEI."),
    ])
    try:
        result = run_nexus_agent(
            client, model="test-model", task="Explain main.py",
            workspace_tools=tools, cloud_model_consent=True,
        )
        assert result.answer == "The project prints ODEI."
        assert result.tool_calls == 1
        assert result.tool_rounds == 1
        first, second = client.responses.calls
        assert "tools" in first and first["store"] is False
        assert second["store"] is False
        assert "previous_response_id" not in second
        assert second["instructions"] == first["instructions"]
        history = second["input"]
        assert any(getattr(item, "type", None) == "function_call" for item in history)
        outputs = [item for item in history if isinstance(item, dict) and item.get("type") == "function_call_output"]
        assert len(outputs) == 1
        assert "print('ODEI')" in outputs[0]["output"]
        assert source.read_text(encoding="utf-8") == "print('ODEI')\n"
    finally:
        registry.close()


def test_agent_requires_explicit_cloud_consent_before_model_call(tmp_path) -> None:
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    client = FakeClient([])
    try:
        with pytest.raises(AgentRuntimeError, match="consent"):
            run_nexus_agent(client, model="model", task="Explain", workspace_tools=tools)
        assert client.responses.calls == []
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
    client = FakeClient([_response([SimpleNamespace(type="message")], " ")])
    try:
        with pytest.raises(AgentRuntimeError, match="no final answer"):
            run_nexus_agent(client, model="model", task="Explain", workspace_tools=tools, cloud_model_consent=True)
    finally:
        registry.close()


def test_agent_redacts_secrets_from_final_answer(tmp_path) -> None:
    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    secret = "sk-proj-" + "A" * 28
    client = FakeClient([_response([SimpleNamespace(type="message")], "I found " + secret)])
    try:
        result = run_nexus_agent(client, model="model", task="Explain", workspace_tools=tools, cloud_model_consent=True)
        assert secret not in result.answer
        assert "[REDACTED]" in result.answer
    finally:
        registry.close()
