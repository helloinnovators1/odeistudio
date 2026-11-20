from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal
from odei_api.services.tasks import TaskRecord, TaskStatus, identity_owner_key, transition_task


class Collection:
    def __init__(self, document=None):
        self.document = document
        self.query = None

    async def find_one(self, query):
        self.query = query
        return self.document


class Database:
    def __init__(self):
        self.collections = {
            "organization_memberships": Collection({"status": "active"}),
            "projects": Collection({
                "organization_id": "org-1", "project_id": "project-1",
                "status": "active", "owner_issuer": "https://identity.example/",
                "owner_subject": "user-1",
            }),
            "project_memberships": Collection(None),
        }

    def __getitem__(self, name):
        return self.collections[name]


class Audit:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)


class TaskStore:
    def __init__(self, audit):
        self.tasks = {}
        self.audit = audit

    async def create_planned(self, task, *, plan, audit_event=None):
        current = task
        for status in (TaskStatus.CONTEXT_GATHERING, TaskStatus.PLANNING, TaskStatus.AWAITING_APPROVAL):
            current = transition_task(
                current, status, expected_version=current.version,
                plan=plan if status is TaskStatus.AWAITING_APPROVAL else None,
            )
        self.tasks[current.id] = current
        if audit_event is not None:
            await self.audit.append(**audit_event)
        return current

    async def list_events(self, *, organization_id, task_id, after_version=-1, limit=50):
        task = await self.get(organization_id=organization_id, task_id=task_id)
        if task is None:
            return [], False
        rows = [
            {"event_id": f"event-{version}", "type": "task.status_changed",
             "version": version, "from_status": "planning",
             "to_status": "awaiting_approval", "occurred_at": datetime.now(timezone.utc)}
            for version in range(4) if version > after_version
        ]
        return rows[:limit], len(rows) > limit

    async def get(self, *, organization_id, task_id):
        task = self.tasks.get(task_id)
        return task if task and task.organization_id == organization_id else None

    async def transition(self, *, organization_id, task_id, next_status, expected_version, actor_id=None, audit_event=None):
        current = await self.get(organization_id=organization_id, task_id=task_id)
        if current is None:
            raise KeyError("Task not found")
        updated = transition_task(current, next_status, expected_version=expected_version)
        self.tasks[task_id] = updated
        if audit_event is not None:
            await self.audit.append(**audit_event)
        return updated


@pytest.fixture
def route_state():
    previous = {
        key: getattr(app.state, key, None)
        for key in ("mongo_database", "audit_event_store", "task_store")
    }
    database, audit = Database(), Audit()
    tasks = TaskStore(audit)
    app.state.mongo_database = database
    app.state.audit_event_store = audit
    app.state.task_store = tasks
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="user-1", issuer="https://identity.example/",
    )
    try:
        yield database, audit, tasks
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        for key, value in previous.items():
            setattr(app.state, key, value)


def test_project_task_requires_cloud_consent(route_state):
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks",
        json={"task": "Add tests", "cloud_model_consent": False},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "CLOUD_MODEL_CONSENT_REQUIRED"


def test_project_task_requires_active_project_access(route_state, monkeypatch):
    database, audit, _ = route_state
    database.collections["projects"].document = None
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks",
        json={"task": "Add tests", "cloud_model_consent": True},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert len(audit.events) == 1
    assert audit.events[0]["action"] == "nexus.project.access"
    assert audit.events[0]["outcome"] == "denied"
    assert audit.events[0]["target_id"] == "project-1"


def test_project_task_is_persisted_for_approval_and_audited(route_state, monkeypatch):
    _, audit, tasks = route_state
    monkeypatch.setattr("odei_api.services.nexus_tasks.get_openai_client", lambda: (object(), "model"))
    monkeypatch.setattr(
        "odei_api.services.nexus_tasks.create_task_plan",
        lambda *_args, **_kwargs: SimpleNamespace(text="Inspect, implement, verify", model="model"),
    )
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks",
        json={"task": "Add tests", "cloud_model_consent": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_approval"
    assert body["version"] == 3
    assert body["plan"] == "Inspect, implement, verify"
    assert tasks.tasks[body["task_id"]].status is TaskStatus.AWAITING_APPROVAL
    assert audit.events[0]["action"] == "nexus.task.create"
    assert audit.events[0]["outcome"] == "success"
    assert "Add tests" not in str(audit.events)


def test_approval_records_approval_without_starting_execution(route_state, monkeypatch):
    _, audit, tasks = route_state
    task = TaskRecord(
        id="task-1", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://identity.example/", "user-1"), goal="Add tests", plan="Inspect and test",
        status=TaskStatus.AWAITING_APPROVAL, version=3,
        created_at=datetime.now(timezone.utc),
    )
    tasks.tasks[task.id] = task
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/approve",
        json={"expected_version": 3},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["version"] == 4
    assert audit.events[0]["action"] == "nexus.task.approve"


def test_stale_approval_version_returns_conflict(route_state):
    _, _, tasks = route_state
    task = TaskRecord(
        id="task-1", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://identity.example/", "user-1"), goal="Add tests", plan="Inspect and test",
        status=TaskStatus.AWAITING_APPROVAL, version=3,
    )
    tasks.tasks[task.id] = task
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/approve",
        json={"expected_version": 2},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TASK_VERSION_OR_STATE_CONFLICT"

  
def test_project_member_cannot_approve_another_users_task(route_state):
    database, _, tasks = route_state
    database.collections["projects"].document = {
        "organization_id": "org-1", "project_id": "project-1",
        "status": "active", "owner_issuer": "https://identity.example/",
        "owner_subject": "project-owner",
    }
    database.collections["project_memberships"].document = {"status": "active"}
    task = TaskRecord(
        id="task-2", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://identity.example/", "user-1"), goal="Add tests", plan="Inspect and test",
        status=TaskStatus.AWAITING_APPROVAL, version=3,
    )
    tasks.tasks[task.id] = task
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-2/approve",
        json={"expected_version": 3},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PROJECT_OWNER_APPROVAL_REQUIRED"
    assert tasks.tasks[task.id].status is TaskStatus.AWAITING_APPROVAL


def test_same_subject_from_different_issuer_cannot_read_task(route_state):
    database, _, tasks = route_state
    database.collections["projects"].document = {
        "organization_id": "org-1", "project_id": "project-1",
        "status": "active", "owner_issuer": "https://identity.example/",
        "owner_subject": "project-owner",
    }
    database.collections["project_memberships"].document = {"status": "active"}
    task = TaskRecord(
        id="task-cross-issuer", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://issuer-a.example/", "same-subject"),
        goal="Private task", status=TaskStatus.AWAITING_APPROVAL, version=3,
        plan="Inspect and test",
    )
    tasks.tasks[task.id] = task
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="same-subject", issuer="https://issuer-b.example/",
    )
    response = TestClient(app).get(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-cross-issuer"
    )
    assert response.status_code == 404


def test_task_events_are_project_authorized_and_cursor_paginated(route_state):
    _, _, tasks = route_state
    task = TaskRecord(
        id="task-1", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://identity.example/", "user-1"),
        goal="Task events", plan="Plan", status=TaskStatus.AWAITING_APPROVAL, version=3,
    )
    tasks.tasks[task.id] = task
    response = TestClient(app).get(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/events",
        params={"after_version": 1, "limit": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert [event["version"] for event in body["events"]] == [2, 3]
    assert body["next_after_version"] == 3
    assert body["has_more"] is False
