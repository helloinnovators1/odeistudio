from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal


client = TestClient(app)


class FakeMembershipCollection:
    def __init__(self, membership):
        self.membership = membership
        self.query = None

    async def find_one(self, query):
        self.query = query
        return self.membership


class FakeDatabase:
    def __init__(self, memberships):
        self.memberships = memberships

    def __getitem__(self, name):
        assert name == "organization_memberships"
        return self.memberships


class FakeAuditStore:
    def __init__(self, fail=False):
        self.events = []
        self.fail = fail

    async def append(self, **event):
        if self.fail:
            raise RuntimeError("audit storage unavailable")
        self.events.append(event)
        return event


@pytest.fixture
def route_state():
    previous_database = getattr(app.state, "mongo_database", None)
    previous_audit = getattr(app.state, "audit_event_store", None)
    memberships = FakeMembershipCollection({
        "organization_id": "org-1",
        "identity_issuer": "https://identity.example.test/",
        "identity_subject": "user-1",
        "status": "active",
        "role": "developer",
    })
    audit = FakeAuditStore()
    app.state.mongo_database = FakeDatabase(memberships)
    app.state.audit_event_store = audit
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="user-1",
        issuer="https://identity.example.test/",
    )
    try:
        yield memberships, audit
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.state.mongo_database = previous_database
        app.state.audit_event_store = previous_audit


def test_nexus_plan_requires_explicit_cloud_consent(route_state):
    _, audit = route_state
    response = client.post(
        "/api/v1/organizations/org-1/nexus/plan",
        json={"task": "Add tests", "cloud_model_consent": False},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "CLOUD_MODEL_CONSENT_REQUIRED"
    assert audit.events == []


def test_nexus_plan_requires_active_membership(route_state):
    memberships, audit = route_state
    memberships.membership = None
    response = client.post(
        "/api/v1/organizations/org-1/nexus/plan",
        json={"task": "Add tests", "cloud_model_consent": True},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ORGANIZATION_ACCESS_DENIED"
    assert len(audit.events) == 1
    assert audit.events[0]["action"] == "organization.membership.read"
    assert audit.events[0]["outcome"] == "denied"


def test_nexus_plan_returns_plan_and_audits_without_task_content(route_state, monkeypatch):
    _, audit = route_state
    monkeypatch.setattr(
        "odei_api.main.get_openai_client",
        lambda: (object(), "test-model"),
    )

    def fake_create_task_plan(client_arg, **kwargs):
        assert kwargs["cloud_model_consent"] is True
        assert kwargs["task"] == "Add safe tests"
        return SimpleNamespace(text="1. Inspect\\n2. Test", model="test-model")

    monkeypatch.setattr("odei_api.main.create_task_plan", fake_create_task_plan)
    response = client.post(
        "/api/v1/organizations/org-1/nexus/plan",
        json={
            "task": "Add safe tests",
            "project_context": "FastAPI project",
            "cloud_model_consent": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["organization_id"] == "org-1"
    assert body["model"] == "test-model"
    assert body["plan"] == "1. Inspect\\n2. Test"
    assert body["plan_id"]
    assert len(audit.events) == 1
    event = audit.events[0]
    assert event["action"] == "nexus.plan.create"
    assert event["outcome"] == "success"
    assert event["metadata"] == {"model": "test-model"}
    assert "Add safe tests" not in str(event)
    assert "FastAPI project" not in str(event)
    assert body["plan"] not in str(event)


def test_nexus_plan_fails_closed_when_audit_append_fails(route_state, monkeypatch):
    _, audit = route_state
    audit.fail = True
    monkeypatch.setattr(
        "odei_api.main.get_openai_client",
        lambda: (object(), "test-model"),
    )
    monkeypatch.setattr(
        "odei_api.main.create_task_plan",
        lambda *_args, **_kwargs: SimpleNamespace(text="Plan", model="test-model"),
    )
    response = client.post(
        "/api/v1/organizations/org-1/nexus/plan",
        json={"task": "Add tests", "cloud_model_consent": True},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "AUDIT_STORE_UNAVAILABLE"


def test_nexus_plan_rejects_oversized_or_extra_input(route_state):
    oversized = client.post(
        "/api/v1/organizations/org-1/nexus/plan",
        json={"task": "x" * 8_001, "cloud_model_consent": True},
    )
    extra = client.post(
        "/api/v1/organizations/org-1/nexus/plan",
        json={"task": "Add tests", "cloud_model_consent": True, "admin": True},
    )
    assert oversized.status_code == 422
    assert extra.status_code == 422
