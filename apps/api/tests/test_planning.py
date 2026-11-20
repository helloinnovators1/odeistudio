from types import SimpleNamespace

import pytest

from odei_api.services.planning import (
    MAX_CONTEXT_CHARS,
    MAX_TASK_CHARS,
    PlanningError,
    create_task_plan,
)


class FakeResponses:
    def __init__(self, output: str):
        self.output = output
        self.last_call = None

    def create(self, **kwargs):
        self.last_call = kwargs
        return SimpleNamespace(output_text=self.output)


class FakeClient:
    def __init__(self, output: str):
        self.responses = FakeResponses(output)


def test_creates_plan_using_responses_without_tools() -> None:
    client = FakeClient("Goal\nImplement safe indexing")
    plan = create_task_plan(
        client, model="test-model", task="Improve project indexing",
        project_context="FastAPI project",
    )
    assert plan.text == "Goal\nImplement safe indexing"
    assert plan.model == "test-model"
    assert "tools" not in client.responses.last_call
    assert client.responses.last_call["model"] == "test-model"


def test_rejects_empty_task() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        create_task_plan(FakeClient("plan"), model="model", task=" ")


def test_rejects_oversized_task() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        create_task_plan(
            FakeClient("plan"), model="model", task="x" * (MAX_TASK_CHARS + 1)
        )


def test_bounds_repository_context() -> None:
    client = FakeClient("plan")
    create_task_plan(
        client, model="model", task="task",
        project_context="x" * (MAX_CONTEXT_CHARS + 100),
    )
    assert len(client.responses.last_call["input"]) < MAX_CONTEXT_CHARS + 500


def test_rejects_empty_model_output() -> None:
    with pytest.raises(PlanningError):
        create_task_plan(FakeClient("  "), model="model", task="task")
