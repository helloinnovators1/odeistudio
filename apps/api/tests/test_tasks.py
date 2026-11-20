import pytest

from odei_api.services.tasks import (
    InvalidTaskTransition,
    TaskRecord,
    TaskStatus,
    transition_task,
)


def make_task() -> TaskRecord:
    return TaskRecord(
        id="task-1", organization_id="org-1", project_id="project-1",
        owner_id="user-1", goal="Add a health endpoint",
    )


def test_task_can_progress_through_planning_and_approval() -> None:
    task = make_task()
    task = transition_task(task, TaskStatus.CONTEXT_GATHERING, expected_version=0)
    task = transition_task(task, TaskStatus.PLANNING, expected_version=1)
    task = transition_task(
        task, TaskStatus.AWAITING_APPROVAL, expected_version=2,
        plan="Inspect API, implement route, add tests",
    )
    assert task.status is TaskStatus.AWAITING_APPROVAL
    assert task.version == 3
    assert task.plan


def test_approval_cannot_be_requested_without_a_plan() -> None:
    task = transition_task(make_task(), TaskStatus.CONTEXT_GATHERING, expected_version=0)
    task = transition_task(task, TaskStatus.PLANNING, expected_version=1)
    with pytest.raises(InvalidTaskTransition, match="plan is required"):
        transition_task(task, TaskStatus.AWAITING_APPROVAL, expected_version=2)


def test_rejects_illegal_transition() -> None:
    with pytest.raises(InvalidTaskTransition, match="not allowed"):
        transition_task(make_task(), TaskStatus.COMPLETED, expected_version=0)


def test_rejects_stale_version() -> None:
    with pytest.raises(InvalidTaskTransition, match="version conflict"):
        transition_task(make_task(), TaskStatus.CONTEXT_GATHERING, expected_version=4)


def test_terminal_task_cannot_be_reopened() -> None:
    task = make_task()
    task = transition_task(task, TaskStatus.CONTEXT_GATHERING, expected_version=0)
    task = transition_task(task, TaskStatus.PLANNING, expected_version=1)
    task = transition_task(task, TaskStatus.EXECUTING, expected_version=2)
    task = transition_task(task, TaskStatus.REVIEW_READY, expected_version=3)
    task = transition_task(task, TaskStatus.COMPLETED, expected_version=4)
    with pytest.raises(InvalidTaskTransition):
        transition_task(task, TaskStatus.EXECUTING, expected_version=5)
