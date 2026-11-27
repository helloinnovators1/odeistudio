from __future__ import annotations

import base64
import io
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from odei_api.config import Settings
from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal
from odei_api.services.execution_profiles import load_execution_profiles
from odei_api.services.execution_runs import ExecutionRunStatus
from odei_api.services.github_app import VerifiedGitHubRepository
from odei_api.services.tasks import TaskRecord, TaskStatus, identity_owner_key


class FakeSession:
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_):
        return False
    async def start_transaction(self):
        return self


class FakeClient:
    def start_session(self):
        return FakeSession()


class Collection:
    def __init__(self, document):
        self.document = document

    def _value(self, key):
        value = self.document
        for part in key.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    def _matches(self, query):
        if self.document is None:
            return False
        for key, expected in query.items():
            actual = self._value(key)
            if isinstance(expected, dict) and "$exists" in expected:
                if (actual is not None) != expected["$exists"]:
                    return False
            elif isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif isinstance(expected, dict) and "$gt" in expected:
                if actual is None or actual <= expected["$gt"]:
                    return False
            elif isinstance(expected, dict) and "$lte" in expected:
                if actual is None or actual > expected["$lte"]:
                    return False
            elif actual != expected:
                return False
        return True

    async def find_one(self, query):
        return self.document if self._matches(query) else None

    async def update_one(self, query, update, **_kwargs):
        if not self._matches(query):
            return SimpleNamespace(modified_count=0)
        for key, value in update.get("$set", {}).items():
            self.document[key] = value
        for key in update.get("$unset", {}):
            self.document.pop(key, None)
        for key, amount in update.get("$inc", {}).items():
            self.document[key] = self.document.get(key, 0) + amount
        return SimpleNamespace(modified_count=1, matched_count=1)


class Database:
    def __init__(self):
        self.client = FakeClient()
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
            "nexus_repository_bindings": Collection(None),
            "execution_runs": Collection(None),
            "nexus_repository_merge_approvals": Collection(None),
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
    def __init__(self):
        self.document = None

    async def get_for_tenant(self, **_values):
        if self.document is not None:
            return self.document
        return {
            "artifact_id": "artifact-1", "run_id": "run-1",
            "exit_code": 0, "duration_ms": 12, "timed_out": False,
            "stdout_truncated": False, "stderr_truncated": False,
            "stdout_bytes": 2, "stderr_bytes": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "stdout": "ok", "stderr": "",
        }





class MergeApprovalStore:
    def __init__(self):
        self.document = None

    async def create(self, **values):
        self.document = {
            **values,
            "created_by_issuer": values["actor_issuer"],
            "created_by_subject": values["actor_subject"],
            "approval_id": "a" * 32, "status": "pending",
            "version": 1, "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        }
        return dict(self.document)

    async def get_for_run(self, **_values):
        return dict(self.document) if self.document is not None else None

    async def consume(self, **values):
        if (
            self.document is None or self.document["status"] != "pending"
            or self.document["approval_id"] != values["approval_id"]
            or self.document["created_by_issuer"] != values["actor_issuer"]
            or self.document["created_by_subject"] != values["actor_subject"]
        ):
            return None
        self.document["status"] = "consuming"
        self.document["version"] += 1
        return dict(self.document)

    async def finish(self, *, status, merge_commit_sha=None, **_values):
        assert self.document["status"] == "consuming"
        self.document["status"] = status
        self.document["merge_commit_sha"] = merge_commit_sha
        self.document["version"] += 1
        return dict(self.document)


class MergeGitHub:
    def __init__(self):
        self.verified = []
        self.merged = []

    async def verify_pull_request(self, *, binding, expected):
        self.verified.append((binding, expected))
        return {
            "repository_id": 123, "commit_sha": "c" * 40,
            "tree_sha": "d" * 40, "base_sha": "b" * 40,
            "pull_request_number": 12,
            "pull_request_url": "https://github.com/Acme/Service/pull/12",
        }

    async def merge_pull_request(self, *, binding, expected):
        self.merged.append((binding, expected))
        return {
            "repository_id": 123, "commit_sha": "c" * 40,
            "tree_sha": "d" * 40, "base_sha": "b" * 40,
            "pull_request_number": 12,
            "pull_request_url": "https://github.com/Acme/Service/pull/12",
            "merged": True, "merge_commit_sha": "e" * 40,
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


async def _verified_repository(**kwargs):
    assert kwargs == {"installation_id": 77, "owner": "acme", "name": "service"}
    return VerifiedGitHubRepository(
        installation_id=77, repository_id=123, repository_node_id="R_kgDOabc",
        owner="Acme", name="Service", full_name="Acme/Service",
        default_branch="main", contents_permission="write",
        pull_requests_permission="write", default_branch_sha="b" * 40, private=True,
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
        for key in ("mongo_database", "mongo_client", "audit_event_store", "task_store",
                    "execution_run_store", "workspace_snapshot_store",
                    "execution_profile_registry", "execution_artifact_store",
                    "github_app_client", "repository_merge_approval_store")
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
    app.state.mongo_client = database.client
    app.state.audit_event_store = audit
    app.state.task_store = tasks
    app.state.workspace_snapshot_store = snapshots
    app.state.execution_run_store = runs
    app.state.execution_artifact_store = Artifacts()
    app.state.github_app_client = type("GitHub", (), {
        "verify_repository": staticmethod(lambda **kwargs: _verified_repository(**kwargs)),
    })()
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
        "profile_id": "python-tests", "mode": "agent", "expected_task_version": 4,
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


@pytest.mark.parametrize("mode", ["ask", "plan", "debug", "unknown"])
def test_execution_requires_agent_mode_at_api_boundary(execution_state, mode):
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(mode=mode),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "NEXUS_MODE_CAPABILITY_DENIED"


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
    assert runs.created["audit_event"]["metadata"]["mode"] == "agent"
    assert runs.run.arguments == ()
    assert snapshots.documents
    assert audit.events == []


def test_execution_run_pins_verified_repository_identity_and_base(execution_state):
    database, _audit, _tasks, _snapshots, runs = execution_state
    database["projects"].document["owner_subject"] = "task-owner"
    database["nexus_repository_bindings"].document = {
        "_id": "org-1:project-1", "organization_id": "org-1", "project_id": "project-1",
        "state": "verified", "installation_id": 77, "repository_id": 123,
        "repository_node_id": "R_kgDOabc", "owner": "acme", "name": "service",
        "full_name": "Acme/Service", "default_branch": "main", "binding_version": 4,
    }
    body = payload()
    body["repository_publish_consent"] = True
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=body,
    )
    assert response.status_code == 200, response.text
    assert runs.run.repository_binding_version == 4
    assert runs.run.repository_id == 123
    assert runs.run.repository_node_id == "R_kgDOabc"
    assert runs.run.repository_base_sha == "b" * 40
    assert response.json()["repository_base_sha"] == "b" * 40



def test_bound_execution_without_publish_consent_does_not_create_repository_review(execution_state):
    database, _audit, _tasks, _snapshots, runs = execution_state
    database["nexus_repository_bindings"].document = {
        "_id": "org-1:project-1", "organization_id": "org-1", "project_id": "project-1",
        "state": "verified", "installation_id": 77, "repository_id": 123,
        "repository_node_id": "R_kgDOabc", "owner": "acme", "name": "service",
        "full_name": "Acme/Service", "default_branch": "main", "binding_version": 4,
    }
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(),
    )
    assert response.status_code == 200, response.text
    assert runs.run.repository_binding_version is None
    assert response.json()["repository_publish_consent"] is False


def test_bound_execution_publish_requires_project_owner(execution_state):
    database, _audit, _tasks, _snapshots, _runs = execution_state
    database["nexus_repository_bindings"].document = {
        "_id": "org-1:project-1", "organization_id": "org-1", "project_id": "project-1",
        "state": "verified", "installation_id": 77, "repository_id": 123,
        "repository_node_id": "R_kgDOabc", "owner": "acme", "name": "service",
        "full_name": "Acme/Service", "default_branch": "main", "binding_version": 4,
    }
    body = payload()
    body["repository_publish_consent"] = True
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=body,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "REPOSITORY_PUBLISH_OWNER_REQUIRED"




def test_owner_must_create_and_consume_single_use_merge_approval(execution_state):
    database, audit, tasks, _snapshots, runs = execution_state
    database["projects"].document["owner_subject"] = "task-owner"
    database["nexus_repository_bindings"].document = {
        "_id": "org-1:project-1", "organization_id": "org-1", "project_id": "project-1",
        "state": "verified", "installation_id": 77, "repository_id": 123,
        "repository_node_id": "R_kgDOabc", "owner": "Acme", "name": "Service",
        "default_branch": "main", "binding_version": 4,
    }
    created = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(),
    )
    assert created.status_code == 200, created.text
    tasks.task = replace(tasks.task, status=TaskStatus.EXECUTING)
    run = runs.run
    runs.run = replace(
        run, status=ExecutionRunStatus.COMPLETED,
        repository_binding_version=4, repository_id=123,
        repository_node_id="R_kgDOabc", repository_installation_id=77,
        repository_owner="Acme", repository_name="Service",
        repository_default_branch="main", repository_base_sha="b" * 40,
        worker_commit_sha="c" * 40, worker_tree_sha="d" * 40,
        worker_branch=f"odei/nexus/{run.id}", worker_pull_request_number=12,
        worker_pull_request_url="https://github.com/Acme/Service/pull/12",
        worker_provenance_at=datetime.now(timezone.utc),
    )
    store, github = MergeApprovalStore(), MergeGitHub()
    app.state.repository_merge_approval_store = store
    app.state.github_app_client = github
    path = f"/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions/{run.id}"
    confirmation = "I_REVIEWED_THE_PULL_REQUEST_AND_APPROVE_MERGE"
    approval_response = TestClient(app).post(
        path + "/merge-approvals", json={"confirmation": confirmation},
    )
    assert approval_response.status_code == 200, approval_response.text
    approval = approval_response.json()
    assert approval["status"] == "pending"
    assert approval["approval_id"] == "a" * 32
    assert github.verified[0][1]["commit_sha"] == "c" * 40
    approval_state = TestClient(app).get(path)
    assert approval_state.status_code == 200, approval_state.text
    assert approval_state.json()["repository_merge_approval"]["status"] == "pending"
    assert approval_state.json()["repository_merge_approval"]["approval_id"] == approval["approval_id"]

    merge_response = TestClient(app).post(
        path + "/merge",
        json={"approval_id": approval["approval_id"], "confirmation": confirmation},
    )
    assert merge_response.status_code == 200, merge_response.text
    assert merge_response.json()["merged"] is True
    assert merge_response.json()["merge_commit_sha"] == "e" * 40
    assert store.document["status"] == "consumed"
    assert "merge_lock" not in database["nexus_repository_bindings"].document
    assert len(github.merged) == 1
    merged_state = TestClient(app).get(path)
    assert merged_state.status_code == 200, merged_state.text
    assert merged_state.json()["repository_merge_approval"]["status"] == "consumed"
    assert merged_state.json()["repository_merge_approval"]["merge_commit_sha"] == "e" * 40

    replay = TestClient(app).post(
        path + "/merge",
        json={"approval_id": approval["approval_id"], "confirmation": confirmation},
    )
    assert replay.status_code == 409
    assert len(github.merged) == 1
    assert any(event["action"] == "nexus.repository_merge.execute" for event in audit.events)




def test_repairing_task_can_start_a_new_explicitly_consented_execution(execution_state):
    _database, _audit, tasks, _snapshots, runs = execution_state
    tasks.task = replace(tasks.task, status=TaskStatus.REPAIRING)
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(),
    )
    assert response.status_code == 200, response.text
    assert runs.created["expected_task_version"] == 4
    assert runs.run.task_id == "task-1"



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


def test_execution_diagnostics_are_structured_bounded_and_audited(execution_state):
    _database, audit, _tasks, _snapshots, _runs = execution_state
    client = TestClient(app)
    created = client.post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(),
    ).json()
    artifacts = app.state.execution_artifact_store
    artifacts.document = {
        "artifact_id": "artifact-1", "run_id": created["run_id"],
        "exit_code": 1, "duration_ms": 42, "timed_out": False,
        "stdout_truncated": False, "stderr_truncated": False,
        "stdout_bytes": 60, "stderr_bytes": 75,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stdout": "", "stderr": "Traceback (most recent call last):\nModuleNotFoundError: No module named 'missing_pkg'",
    }
    response = client.get(
        f"/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions/{created['run_id']}/diagnostics"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["category"] == "failed"
    assert "MODULE_NOT_FOUND" in body["signals"]
    assert len(body["evidence"]) == 2
    assert all(len(line) <= 240 for line in body["evidence"])
    assert "stderr" not in body
    assert audit.events[-1]["action"] == "nexus.execution.diagnostics.read"
    assert audit.events[-1]["metadata"]["evidence_count"] == 2


def test_execution_diagnostics_hide_cross_task_artifacts(execution_state):
    _database, _audit, _tasks, _snapshots, _runs = execution_state
    client = TestClient(app)
    created = client.post(
        "/api/v1/organizations/org-1/projects/project-1/tasks/task-1/executions",
        json=payload(),
    ).json()
    response = client.get(
        f"/api/v1/organizations/org-1/projects/project-1/tasks/other-task/executions/{created['run_id']}/diagnostics"
    )
    assert response.status_code == 404
