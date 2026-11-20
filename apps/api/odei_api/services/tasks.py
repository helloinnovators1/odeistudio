"""NEXUS durable-task domain model and guarded state transitions.

Persistence and HTTP exposure are intentionally separate. Callers must enforce
identity, organization membership, task ownership and approval policy before
invoking these transitions or persisting their results.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json


class TaskStatus(str, Enum):
    CREATED = "created"
    CONTEXT_GATHERING = "context_gathering"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    VALIDATING = "validating"
    REPAIRING = "repairing"
    REVIEW_READY = "review_ready"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


TERMINAL_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.EXPIRED,
}

ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.CONTEXT_GATHERING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.CONTEXT_GATHERING: {TaskStatus.PLANNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.PLANNING: {TaskStatus.AWAITING_APPROVAL, TaskStatus.EXECUTING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.AWAITING_APPROVAL: {TaskStatus.APPROVED, TaskStatus.CANCELLED, TaskStatus.EXPIRED},
    TaskStatus.APPROVED: {TaskStatus.EXECUTING, TaskStatus.CANCELLED, TaskStatus.EXPIRED},
    TaskStatus.EXECUTING: {TaskStatus.VALIDATING, TaskStatus.REPAIRING, TaskStatus.REVIEW_READY, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.VALIDATING: {TaskStatus.REPAIRING, TaskStatus.REVIEW_READY, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.REPAIRING: {TaskStatus.EXECUTING, TaskStatus.VALIDATING, TaskStatus.REVIEW_READY, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.REVIEW_READY: {TaskStatus.COMPLETED, TaskStatus.EXECUTING, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
    TaskStatus.EXPIRED: set(),
}


def identity_owner_key(issuer: str, subject: str) -> str:
    """Return a stable, unambiguous owner key for a verified external identity."""
    if not issuer.strip() or not subject.strip():
        raise ValueError("issuer and subject must not be empty")
    return json.dumps([issuer, subject], ensure_ascii=False, separators=(",", ":"))


class InvalidTaskTransition(ValueError):
    """Raised when a task attempts an illegal lifecycle transition."""


@dataclass(frozen=True)
class TaskRecord:
    id: str
    organization_id: str
    project_id: str
    owner_id: str
    goal: str
    status: TaskStatus = TaskStatus.CREATED
    plan: str | None = None
    version: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("id", "organization_id", "project_id", "owner_id", "goal"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.version < 0:
            raise ValueError("version must not be negative")


def transition_task(
    task: TaskRecord,
    next_status: TaskStatus,
    *,
    expected_version: int,
    plan: str | None = None,
) -> TaskRecord:
    """Apply one optimistic, legal state transition to an immutable record."""
    if task.version != expected_version:
        raise InvalidTaskTransition("Task version conflict; reload before retrying")
    if next_status not in ALLOWED_TRANSITIONS[task.status]:
        raise InvalidTaskTransition(
            f"Transition from {task.status.value} to {next_status.value} is not allowed"
        )
    if next_status == TaskStatus.AWAITING_APPROVAL and not (plan or task.plan):
        raise InvalidTaskTransition("A task plan is required before requesting approval")

    now = datetime.now(timezone.utc)
    return replace(
        task,
        status=next_status,
        plan=plan if plan is not None else task.plan,
        version=task.version + 1,
        created_at=task.created_at or now,
        updated_at=now,
    )
