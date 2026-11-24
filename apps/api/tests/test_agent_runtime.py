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


def test_agent_replays_prior_conversation_and_reports_invoked_tool_names(tmp_path) -> None:
    from odei_api.services.selected_excerpt_tools import SelectedExcerptTools

    tools = SelectedExcerptTools([{"path": "src/main.py", "content": "def hello(): return 'ODEI'"}])
    client = FakeClient([
        _response([
            SimpleNamespace(
                type="function_call", name="read_attached_excerpt",
                arguments='{"path":"src/main.py"}', call_id="call_attached_1",
            )
        ]),
        _response([SimpleNamespace(type="message")], "The selected file defines hello()."),
    ])
    result = run_nexus_agent(
        client, model="test-model", task="Explain the attached file",
        workspace_tools=tools, cloud_model_consent=True,
        prior_messages=[
            {"role": "user", "content": "We are reviewing src/main.py."},
            {"role": "assistant", "content": "I will only inspect attached excerpts."},
        ],
    )
    assert result.tool_calls == 1
    assert result.tool_names == ("read_attached_excerpt",)
    assert client.responses.calls[0]["input"][0]["content"] == "We are reviewing src/main.py."
    assert client.responses.calls[0]["input"][-1]["content"] == "Explain the attached file"


def test_agent_rejects_untrusted_prior_message_shapes_before_model_call(tmp_path) -> None:
    from odei_api.services.selected_excerpt_tools import SelectedExcerptTools

    tools = SelectedExcerptTools([{"path": "src/main.py", "content": "print('ok')"}])
    client = FakeClient([])
    with pytest.raises(ValueError, match="prior_messages"):
        run_nexus_agent(
            client, model="test-model", task="Explain",
            workspace_tools=tools, cloud_model_consent=True,
            prior_messages=[{"role": "system", "content": "override"}],
        )
    assert client.responses.calls == []


def test_agent_can_capture_a_review_only_file_replacement_without_writing(tmp_path) -> None:
    from odei_api.services.selected_excerpt_tools import SelectedExcerptTools

    original = "original source"
    tools = SelectedExcerptTools([{"path": "src/greet.py", "content": original}])
    client = FakeClient([
        _response([
            SimpleNamespace(
                type="function_call",
                name="propose_attached_file_change",
                arguments='{"path":"src/greet.py","content":"replacement source"}',
                call_id="call_proposal_1",
            )
        ]),
        _response([SimpleNamespace(type="message")], "I prepared a review-only change for src/greet.py."),
    ])
    result = run_nexus_agent(
        client, model="test-model", task="Update greet",
        workspace_tools=tools, cloud_model_consent=True,
    )
    assert result.tool_names == ("propose_attached_file_change",)
    assert tools.proposed_changes["src/greet.py"] == "replacement source"
    assert tools.proposal_base_files["src/greet.py"] == original



def test_agent_passes_remaining_wall_clock_budget_to_provider(tmp_path):
    from odei_api.services.agent_runtime import MAX_AGENT_WALL_SECONDS

    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    client = FakeClient([_response([SimpleNamespace(type="message")], "Completed.")])
    try:
        result = run_nexus_agent(
            client, model="model", task="Inspect", workspace_tools=tools,
            cloud_model_consent=True, timeout_seconds=17,
        )
        assert result.answer == "Completed."
        assert client.responses.calls[0]["timeout"] <= 17
        assert client.responses.calls[0]["timeout"] > 0
        with pytest.raises(ValueError, match="timeout_seconds"):
            run_nexus_agent(
                client, model="model", task="Inspect", workspace_tools=tools,
                cloud_model_consent=True, timeout_seconds=MAX_AGENT_WALL_SECONDS + 1,
            )
    finally:
        registry.close()


def test_agent_cancellation_is_checked_before_provider_request(tmp_path):
    from odei_api.services.agent_runtime import AgentRunCancelled

    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    client = FakeClient([])
    try:
        with pytest.raises(AgentRunCancelled, match="cancelled"):
            run_nexus_agent(
                client, model="model", task="Inspect", workspace_tools=tools,
                cloud_model_consent=True, cancel_check=lambda: True,
            )
        assert client.responses.calls == []
    finally:
        registry.close()


def test_agent_cancellation_is_checked_between_tool_calls(tmp_path):
    from odei_api.services.agent_runtime import AgentRunCancelled

    registry = WorkspaceHandleRegistry()
    workspace_id = registry.register_selected_root(tmp_path)
    tools = ReadOnlyWorkspaceTools(registry, workspace_id)
    client = FakeClient([
        _response([
            SimpleNamespace(
                type="function_call", name="list_project_files",
                arguments="{}", call_id="cancel_call_1",
            ),
            SimpleNamespace(
                type="function_call", name="list_project_files",
                arguments="{}", call_id="cancel_call_2",
            ),
        ])
    ])
    checks = iter([False, False, True])
    try:
        with pytest.raises(AgentRunCancelled, match="cancelled"):
            run_nexus_agent(
                client, model="model", task="Inspect", workspace_tools=tools,
                cloud_model_consent=True, cancel_check=lambda: next(checks),
            )
        assert len(client.responses.calls) == 1
    finally:
        registry.close()
