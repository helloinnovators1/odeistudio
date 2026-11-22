from __future__ import annotations

import base64
import io
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from odei_api.config import Settings
from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal
from odei_api.services.execution_profiles import load_execution_profiles
from odei_api.services.tasks import TaskRecord, TaskStatus, identity_owner_key


class Collection:
    def __init__(self, document):
        self.document = document

    async def find_one(self, query):
        if self.document is None:
            return None
        if all(self.document.get(key) == value for key, value in query.items()):
            return self.document
        return None


class Database:
    def __init__(self):
        self.collections = {
            "organization_memberships": Collection({
                "organization_id": "org-1",
                "identity_issuer": "https://identity.example/",
                "identity_subject": "task-owner",
                "status": "active",
            }),
            "projects": Collection({
                "organization_id": "org-1", "project_id": "project-1",
                "status": "active", "owner_issuer": "https://identity.example/",
                "owner_subject": "project-owner",
            }),
            "project_memberships": Collection({
                "organization_id": "org-1", "project_id": "project-1",
                "identity_issuer": "https://identity.example/",
                "identity_subject": "task-owner", "status": "active",
            }),
            "tasks": Collection(None),
            "task_events": Collection(None),
        }

    def __getitem__(self, key):
        return self.collections[key]


class Audit:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)


class Tasks:
    def __init__(self, task):
        self.task = task

    async def get(self, *, organization_id, task_id):
        if self.task and self.task.organization_id == organization_id and self.task.id == task_id:
            return self.task
        return None


class Snapshots:
    def __init__(self):
        self.documents = {}

    async def put(self, **values):
        item = {
            "snapshot_id": "snapshot-1", "organization_id": values["organization_id"],
            "project_id": values["project_id"], "task_id": values["task_id"],
            "sha256": values["sha256"], "file_count": values["file_count"],
            "total_bytes": values["total_bytes"], "archive_bytes": len(values["archive"]),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": datetime.now(timezone.utc).isoformat(),
        }
        self.documents[item["snapshot_id"]] = item
        return item

    async def delete_for_tenant(self, **values):
        return self.documents.pop(values["snapshot_id"], None) is not None


class Artifacts:
    async def get_for_tenant(self, **_values):
        return {
            "artifact_id": "artifact-1", "run_id": "run-1",
            "exit_code": 0, "duration_ms": 12, "timed_out": False,
            "stdout_truncated": False, "stderr_truncated": False,
            "stdout_bytes": 2, "stderr_bytes": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "stdout": "ok", "stderr": "",
        }


class Runs:
    def __init__(self):
        self.run = None
        self.created = None
        self.cancelled = False

    async def create_approved_task_run(self, run, **values):
        self.run = run
        self.created = values
        return run

    async def get(self, *, organization_id, run_id):
        if self.run and self.run.organization_id == organization_id and self.run.id == run_id:
            return self.run
        return None

    async def list_for_project(self, **values):
        self.history_query = values
        if self.run is None:
            return [], False
        return [self.run], False

    async def list_events(self, **_values):
        return ([{"event_id": "event-1", "type": "execution.queued", "version": 0,
                  "occurred_at": datetime.now(timezone.utc)}], False)

    async def request_cancel(self, *, organization_id, run_id, **_values):
        self.cancelled = True
        return SimpleNamespace(
            id=run_id, organization_id=organization_id, project_id="project-1",
            task_id="task-1", profile_id="python-tests", snapshot_sha256="a" * 64,
            status=SimpleNamespace(value="cancelled"), version=1, attempts=0,
            max_attempts=3, cancel_requested=True, created_at=None, updated_at=None,
        )


def archive_base64():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("README.md", b"safe project snapshot")
    return base64.b64encode(stream.getvalue()).decode("ascii")


@pytest.fixture
def execution_state():
    previous = {
        key: getattr(app.state, key, None)
        for key in ("mongo_database", "audit_event_store", "task_store",
                    "execution_run_store", "workspace_snapshot_store",
                    "execution_profile_registry", "execution_artifact_store")
    }
    previous_overrides = dict(app.dependency_overrides)
    database = Database()
    audit = Audit()
    task = TaskRecord(
        id="task-1", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://identity.example/", "task-owner"),
        goal="Run approved tests", status=TaskStatus.APPROVED,
        plan="Run the test suite", version=4,
    )
    tasks, snapshots, runs = Tasks(task), Snapshots(), Runs()
    app.state.mongo_database = database
    app.state.audit_event_store = audit
    app.state.task_store = tasks
    app.state.workspace_snapshot_store = snapshots
    app.state.execution_run_store = runs
    app.state.execution_artifact_store = Artifacts()
    app.state.execution_profile_registry = load_execution_profiles(Settings(
        execution_profiles_json='[{"name":"python-tests","image":"registry.example/odei/python@sha256:' + "a" * 64 + '","command":["python","-m","pytest"]}]'
    ))
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="task-owner", issuer="https://identity.example/",
    )
    yield database, audit, tasks, snapshots, runs
    app.dependency_overrides = previous_overrides
    for key, value in previous.items():
        if value is None and hasattr(app.state, key):
            delattr(app.state, key)
        else:
            setattr(app.state, key, value)


def payload(**overrides):
    value = {
        "profile_id": "python-tests", "expected_task_version": 4,
        "workspace_upload_consent": True, "execution_consent": True,
        "snapshot_zip_base64": archive_base64(),
    }
    value.update(overrides)
    return value


def test_profile_loader_requires_digest_pinned_server_owned_profiles():
    with pytest.raises(ValueError):
        load_execution_profiles(Settings(execution_profiles_json='[{"name":"bad","image":"latest","command":["sh"]}]'))


def test_project_execution_history_is_scoped_to_requester_and_audited(execution_state):
    _database, audit, _tasks, _snapshots, runs = execution_state
    created = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(),
    ).json()
    response = TestClient(app).get(
        "/api/v1/organizations/org-1/projects/project-1/executions?limit=25"
    )
    assert response.status_code == 200, response.text
    assert [row["run_id"] for row in response.json()["runs"]] == [created["run_id"]]
    assert runs.history_query["requester_issuer"] == "https://identity.example/"
    assert runs.history_query["requester_subject"] == "task-owner"
    assert runs.history_query["limit"] == 25
    assert audit.events[-1]["action"] == "nexus.execution.history.read"
    assert audit.events[-1]["metadata"]["owner_scope"] is False


def test_project_execution_history_rejects_partial_cursor(execution_state):
    response = TestClient(app).get(
        "/api/v1/organizations/org-1/projects/project-1/executions?before_run_id=run-1"
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_EXECUTION_CURSOR"


def test_execution_requires_both_explicit_consents(execution_state):
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(execution_consent=False),
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXECUTION_CONSENT_REQUIRED"


def test_execution_requires_project_owner_approved_task(execution_state):
    _database, _audit, tasks, _snapshots, runs = execution_state
    tasks.task = TaskRecord(
        id="task-1", organization_id="org-1", project_id="project-1",
        owner_id=identity_owner_key("https://identity.example/", "task-owner"),
        goal="Not approved", status=TaskStatus.AWAITING_APPROVAL, plan="Plan", version=4,
    )
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TASK_APPROVAL_REQUIRED"
    assert runs.created is None


def test_execution_upload_is_validated_and_atomically_enqueued(execution_state):
    _database, audit, _tasks, snapshots, runs = execution_state
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["profile_id"] == "python-tests"
    assert body["snapshot"]["snapshot_id"] == "snapshot-1"
    assert runs.created["expected_task_version"] == 4
    assert runs.created["tasks"] is _database["tasks"]
    assert runs.run.arguments == ()
    assert snapshots.documents
    assert audit.events == []


def test_invalid_archive_never_creates_snapshot_or_run(execution_state):
    _database, _audit, _tasks, snapshots, runs = execution_state
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(snapshot_zip_base64=base64.b64encode(b"not a zip").decode("ascii")),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "UNSAFE_WORKSPACE_SNAPSHOT"
    assert snapshots.documents == {}
    assert runs.created is None


def test_execution_read_and_cancel_are_task_scoped_and_audited(execution_state):
    _database, audit, _tasks, _snapshots, runs = execution_state
    client = TestClient(app)
    created = client.post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(),
    ).json()
    run_id = created["run_id"]
    read = client.get(
        f"/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions/{run_id}"
    )
    assert read.status_code == 200
    assert "lease_token" not in read.text
    cancelled = client.post(
        f"/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions/{run_id}/cancel"
    )
    assert cancelled.status_code == 200
    assert runs.cancelled is True
    assert [event["action"] for event in audit.events] == [
        "nexus.execution.read", "nexus.execution.cancel",
    ]


def test_cross_identity_cannot_access_execution(execution_state):
    _database, _audit, _tasks, _snapshots, _runs = execution_state
    created = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(),
    ).json()
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="intruder", issuer="https://identity.example/",
    )
    response = TestClient(app).get(
        f"/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions/{created['run_id']}"
    )
    assert response.status_code == 403

def test_execution_artifact_route_is_tenant_and_task_scoped(execution_state):
    _database, audit, _tasks, _snapshots, _runs = execution_state
    client = TestClient(app)
    created = client.post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(),
    ).json()
    response = client.get(
        f"/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions/{created['run_id']}/artifacts"
    )
    assert response.status_code == 200
    assert response.json()["stdout"] == "ok"
    assert audit.events[-1]["action"] == "nexus.execution.artifacts.read"
