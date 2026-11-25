"""Authenticated NEXUS inspection uses the governed registry and durable audit sink."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal


class FakeAuditStore:
    def __init__(self, fail_action=None):
        self.events = []
        self.fail_action = fail_action

    async def append(self, **event):
        if event["action"] == self.fail_action:
            raise RuntimeError("audit unavailable")
        self.events.append(event)
        return event


class FakeConversationStore:
    def __init__(self):
        self.version = 0

    async def get_for_owner(self, **_kwargs):
        return {"messages": [], "version": self.version}

    async def append(self, **_kwargs):
        self.version += 1
        return {"version": self.version}


class FakeResponses:
    def __init__(self):
        self.calls = 0
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                output=[SimpleNamespace(
                    type="function_call",
                    name="read_attached_excerpt",
                    arguments='{"path":"src/main.py"}',
                    call_id="read_call_1",
                )],
                output_text="",
            )
        return SimpleNamespace(output=[SimpleNamespace(type="message")],
                               output_text="The file prints ODEI.")


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


@pytest.fixture
def inspection_state(monkeypatch):
    previous = {
        "audit_event_store": getattr(app.state, "audit_event_store", None),
        "conversation_store": getattr(app.state, "conversation_store", None),
        "patch_proposal_store": getattr(app.state, "patch_proposal_store", None),
        "execution_run_store": getattr(app.state, "execution_run_store", None),
        "execution_artifact_store": getattr(app.state, "execution_artifact_store", None),
        "task_store": getattr(app.state, "task_store", None),
    }
    audit = FakeAuditStore()
    app.state.audit_event_store = audit
    app.state.conversation_store = FakeConversationStore()
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="user-1", issuer="https://identity.example.test/",
    )

    async def authorize_project(*_args, **_kwargs):
        return {
            "owner_issuer": "https://identity.example.test/",
            "owner_subject": "user-1",
        }

    monkeypatch.setattr(
        "odei_api.services.nexus_inspection._authorize_project",
        authorize_project,
    )
    try:
        yield audit
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        for key, value in previous.items():
            setattr(app.state, key, value)


def _payload():
    return {
        "messages": [{"role": "user", "content": "Explain the attached source"}],
        "workspace_files": [{"path": "src/main.py", "content": "print('ODEI')"}],
        "cloud_model_consent": True,
        "conversation_id": "conversation-1",
        "mode": "agent",
    }


def test_inspection_dispatches_tools_through_registry_and_persists_scoped_audit(
    inspection_state, monkeypatch,
):
    audit = inspection_state
    fake_client = FakeClient()
    monkeypatch.setattr(
        "odei_api.services.nexus_inspection.get_openai_client",
        lambda: (fake_client, "test-model"),
    )
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat/inspect",
        json=_payload(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["tool_names"] == ["read_attached_excerpt"]
    actions = [event["action"] for event in audit.events]
    assert "nexus.tool.started" in actions
    assert "nexus.tool.completed" in actions
    assert "agent.run.started" in actions
    assert "agent.run.completed" in actions
    tool_event = next(event for event in audit.events if event["action"] == "nexus.tool.started")
    assert tool_event["organization_id"] == "org-1"
    assert tool_event["actor_subject"] == "user-1"
    assert tool_event["target_type"] == "nexus_tool"
    assert tool_event["target_id"] == "read_attached_excerpt"
    assert "Explain the attached source" not in str(tool_event)
    assert "print('ODEI')" not in str(tool_event)


def test_inspection_fails_closed_before_tool_dispatch_when_audit_is_unavailable(
    inspection_state, monkeypatch,
):
    audit = inspection_state
    audit.fail_action = "nexus.tool.started"
    fake_client = FakeClient()
    monkeypatch.setattr(
        "odei_api.services.nexus_inspection.get_openai_client",
        lambda: (fake_client, "test-model"),
    )
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat/inspect",
        json=_payload(),
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "AUDIT_STORE_UNAVAILABLE"
    # The provider requested a tool, but the governed dispatcher stopped before
    # invoking it when the required durable "started" audit event could not commit.
    assert fake_client.responses.calls == 1
    assert "nexus.tool.completed" not in [event["action"] for event in audit.events]


class FakeExecutionRunStore:
    def __init__(self, run):
        self.run = run

    async def get(self, **_kwargs):
        return self.run




class FakeRepairBudgetStore:
    def __init__(self, audit):
        self.audit = audit
        self.iterations = 0

    async def consume_repair_iteration(
        self, *, organization_id, project_id, task_id, max_iterations, audit_event,
    ):
        if self.iterations >= max_iterations:
            return None
        self.iterations += 1
        event = dict(audit_event)
        event["metadata"] = {**event.get("metadata", {}), "repair_iteration": self.iterations}
        await self.audit.append(**event)
        return self.iterations


class FakeExecutionArtifactStore:
    async def get_for_tenant(self, **_kwargs):
        return {
            "exit_code": 1, "duration_ms": 1200, "timed_out": False,
            "stdout": "", "stderr": "ModuleNotFoundError: No module named 'missing_pkg'",
        }


def test_failed_execution_context_is_authorized_audited_and_proposal_only(
    inspection_state, monkeypatch,
):
    from types import SimpleNamespace

    audit = inspection_state
    previous_run_store = getattr(app.state, "execution_run_store", None)
    previous_artifact_store = getattr(app.state, "execution_artifact_store", None)
    previous_task_store = getattr(app.state, "task_store", None)
    app.state.execution_run_store = FakeExecutionRunStore(SimpleNamespace(
        project_id="project-1", task_id="task-1", status="failed",
    ))
    app.state.execution_artifact_store = FakeExecutionArtifactStore()
    app.state.task_store = FakeRepairBudgetStore(audit)

    async def authorize_execution(*_args, **_kwargs):
        return (None, {"owner_issuer": "https://identity.example.test/"}, SimpleNamespace(id="task-1"))

    monkeypatch.setattr(
        "odei_api.services.nexus_inspection._authorize_execution_resource",
        authorize_execution,
    )
    fake_client = FakeClient()
    monkeypatch.setattr(
        "odei_api.services.nexus_inspection.get_openai_client",
        lambda: (fake_client, "test-model"),
    )
    payload = _payload()
    payload.update({
        "execution_repair_task_id": "task-1",
        "execution_repair_run_id": "run-1",
        "execution_repair_consent": True,
    })
    try:
        response = TestClient(app).post(
            "/api/v1/organizations/org-1/projects/project-1/nexus/chat/inspect",
            json=payload,
        )
        assert response.status_code == 200, response.text
        first_input = fake_client.responses.requests[0]["input"][-1]["content"]
        assert "UNTRUSTED EXECUTION DIAGNOSTICS" in first_input
        assert "ModuleNotFoundError" in first_input
        assert response.json()["read_only"] is True
        assert response.json()["repair_iteration"] == 1
        assert response.json()["max_repair_iterations"] == 3
        repair_audit = next(event for event in audit.events if event["action"] == "nexus.execution.repair_context.read")
        assert repair_audit["target_id"] == "run-1"
        assert repair_audit["metadata"]["category"] == "failed"
        assert repair_audit["metadata"]["repair_iteration"] == 1
        assert "ModuleNotFoundError" not in str(repair_audit)
    finally:
        app.state.execution_run_store = previous_run_store
        app.state.execution_artifact_store = previous_artifact_store
        app.state.task_store = previous_task_store


def test_execution_repair_context_requires_explicit_consent(inspection_state):
    payload = _payload()
    payload.update({
        "execution_repair_task_id": "task-1",
        "execution_repair_run_id": "run-1",
    })
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat/inspect",
        json=payload,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EXECUTION_REPAIR_CONSENT_REQUIRED"



def test_execution_repair_context_stops_after_three_audited_iterations(
    inspection_state, monkeypatch,
):
    audit = inspection_state
    previous_run_store = getattr(app.state, "execution_run_store", None)
    previous_artifact_store = getattr(app.state, "execution_artifact_store", None)
    previous_task_store = getattr(app.state, "task_store", None)
    app.state.execution_run_store = FakeExecutionRunStore(SimpleNamespace(
        project_id="project-1", task_id="task-1", status="failed",
    ))
    app.state.execution_artifact_store = FakeExecutionArtifactStore()
    app.state.task_store = FakeRepairBudgetStore(audit)

    async def authorize_execution(*_args, **_kwargs):
        return (None, {"owner_issuer": "https://identity.example.test/"}, SimpleNamespace(id="task-1"))

    monkeypatch.setattr(
        "odei_api.services.nexus_inspection._authorize_execution_resource",
        authorize_execution,
    )
    fake_client = FakeClient()
    monkeypatch.setattr(
        "odei_api.services.nexus_inspection.get_openai_client",
        lambda: (fake_client, "test-model"),
    )
    payload = _payload()
    payload.update({
        "execution_repair_task_id": "task-1",
        "execution_repair_run_id": "run-1",
        "execution_repair_consent": True,
    })
    try:
        client = TestClient(app)
        for expected in (1, 2, 3):
            response = client.post(
                "/api/v1/organizations/org-1/projects/project-1/nexus/chat/inspect",
                json=payload,
            )
            assert response.status_code == 200, response.text
            assert response.json()["repair_iteration"] == expected
        provider_calls = fake_client.responses.calls
        blocked = client.post(
            "/api/v1/organizations/org-1/projects/project-1/nexus/chat/inspect",
            json=payload,
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "EXECUTION_REPAIR_LIMIT_REACHED"
        assert fake_client.responses.calls == provider_calls
        repair_events = [event for event in audit.events if event["action"] == "nexus.execution.repair_context.read"]
        assert [event["metadata"]["repair_iteration"] for event in repair_events] == [1, 2, 3]
    finally:
        app.state.execution_run_store = previous_run_store
        app.state.execution_artifact_store = previous_artifact_store
        app.state.task_store = previous_task_store


