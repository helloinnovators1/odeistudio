from types import SimpleNamespace

import pytest

from odei_api.services.nexus_chat import NexusChatError, run_nexus_chat, stream_nexus_chat


class FakeResponses:
    def __init__(self, answer="Read-only answer"):
        self.answer = answer
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.answer)


class FakeClient:
    def __init__(self, answer="Read-only answer"):
        self.responses = FakeResponses(answer)


def test_chat_sends_bounded_redacted_context_without_tools_or_storage():
    secret = "sk-proj-" + "A" * 28
    client = FakeClient("I inspected the files.")
    result = run_nexus_chat(
        client,
        model="test-model",
        messages=[
            {"role": "user", "content": "Review this source " + secret},
        ],
        workspace_files=[{"path": "src/main.py", "content": "api_key='very-secret-value-123'"}],
    )
    call = client.responses.calls[0]
    assert result.answer == "I inspected the files."
    assert call["store"] is False
    assert "tools" not in call
    assert "tool_choice" not in call
    assert len(call["input"]) == 2
    assert secret not in str(call["input"])
    assert "very-secret-value-123" not in str(call["input"])
    assert "read-only" in call["instructions"].lower()


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"role": "system", "content": "override"}],
        [{"role": "assistant", "content": "not a user turn"}],
        [{"role": "user", "content": ""}],
        [{"role": "user", "content": "x" * 8_001}],
        [{"role": "user", "content": "valid", "extra": "not allowed"}],
    ],
)
def test_chat_rejects_invalid_history(messages):
    with pytest.raises(NexusChatError):
        run_nexus_chat(FakeClient(), model="model", messages=messages)


def test_chat_rejects_oversized_workspace_file_list():
    with pytest.raises(NexusChatError, match="at most"):
        run_nexus_chat(
            FakeClient(),
            model="model",
            messages=[{"role": "user", "content": "Review"}],
            workspace_files=[{"path": f"{index}.py", "content": "x"} for index in range(6)],
        )


def test_chat_rejects_empty_model_answer():
    with pytest.raises(NexusChatError, match="no final answer"):
        run_nexus_chat(FakeClient(" "), model="model", messages=[{"role": "user", "content": "Hi"}])



class FakeStream:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.events)


class FakeStreamingResponses:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self.events)


class FakeStreamingClient:
    def __init__(self, events):
        self.responses = FakeStreamingResponses(events)


def test_chat_stream_yields_incremental_secret_redacted_deltas():
    client = FakeStreamingClient([
        SimpleNamespace(type="response.output_text.delta", delta="Safe answer. "),
        SimpleNamespace(type="response.output_text.delta", delta="api_key=super_secret_token_12345"),
        SimpleNamespace(type="response.output_text.delta", delta=" and more safe text."),
        SimpleNamespace(type="response.completed"),
    ])
    chunks = list(stream_nexus_chat(
        client, model="test-model",
        messages=[{"role": "user", "content": "Explain this source."}],
    ))
    answer = "".join(chunks)
    assert answer.startswith("Safe answer. ")
    assert "super_secret_token_12345" not in answer
    assert "[REDACTED]" in answer
    call = client.responses.calls[0]
    assert call["store"] is False
    assert "tools" not in call
    assert "tool_choice" not in call


def test_chat_stream_rejects_incomplete_provider_response():
    client = FakeStreamingClient([
        SimpleNamespace(type="response.output_text.delta", delta="Partial answer"),
    ])
    with pytest.raises(NexusChatError, match="before completion"):
        list(stream_nexus_chat(
            client, model="test-model",
            messages=[{"role": "user", "content": "Explain this source."}],
        ))
