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

    def create(self, **_kwargs):
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
