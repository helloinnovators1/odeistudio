"""Route-level tests for authenticated MAC environment governance."""
import json
from types import SimpleNamespace



ISSUER = "https://identity.example.test/"
OTHER_ISSUER = "https://other-identity.example.test/"


class AuditStore:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)


class EnvironmentStore:
    def __init__(self):
        self.calls = []

    async def get(self, environment):
        self.calls.append(("get", environment))
        return {"environment": environment, "latest_version": 1, "active_version": 0}

    async def create_draft(self, **kwargs):
        self.calls.append(("create_draft", kwargs))
        return {"version": 1, "status": "draft"}

    async def create_revision(self, **kwargs):
        self.calls.append(("create_revision", kwargs))
        return {"version": 2, "status": "draft"}

    async def update_draft(self, **kwargs):
        self.calls.append(("update_draft", kwargs))
        return {"latest_version": kwargs["expected_latest_version"]}

    async def submit_for_approval(self, **kwargs):
        self.calls.append(("submit", kwargs))
        return {"latest_version": kwargs["expected_latest_version"]}

    async def approve(self, **kwargs):
        self.calls.append(("approve", kwargs))
        return {"latest_version": kwargs["expected_latest_version"]}

    async def promote(self, **kwargs):
        self.calls.append(("promote", kwargs))
        return {"active_version": kwargs["version"]}

    async def create_rollback_draft(self, **kwargs):
        self.calls.append(("rollback", kwargs))
        return {"version": kwargs["expected_latest_version"] + 1, "rollback_of": kwargs["target_version"]}


def _client(monkeypatch, principal, roles=("infrastructure_admin",)):
    import importlib

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from odei_api.security.auth import get_current_principal
    from odei_api.services.mac_environment_api import router

    mac_environment_api = importlib.import_module("odei_api.services.mac_environment_api")
    registry = json.dumps([{
        "issuer": principal.issuer,
        "subject": principal.subject,
        "roles": list(roles),
    }])
    monkeypatch.setattr(
        mac_environment_api, "get_settings",
        lambda: SimpleNamespace(mac_platform_operators_json=registry),
    )
    app = FastAPI()
    app.include_router(router)
    store = EnvironmentStore()
    audit = AuditStore()
    app.state.mongo_database = object()
    app.state.mac_environment_store = store
    app.state.audit_event_store = audit
    app.dependency_overrides[get_current_principal] = lambda: principal
    return TestClient(app), store, audit


def test_actor_fingerprint_distinguishes_issuers_with_same_subject():
    from odei_api.security.auth import Principal
    from odei_api.services.mac_environment_api import _actor_id

    first = _actor_id(Principal(subject="same-subject", issuer=ISSUER))
    second = _actor_id(Principal(subject="same-subject", issuer=OTHER_ISSUER))
    assert first != second
    assert first.startswith("oidc-")
    assert len(first) == 69


def test_mac_environment_read_is_authenticated_and_audited(monkeypatch):
    from odei_api.security.auth import Principal

    principal = Principal(subject="operator-1", issuer=ISSUER)
    client, store, audit = _client(monkeypatch, principal, ("read_only_auditor",))
    response = client.get("/api/v1/mac/environments/staging")
    assert response.status_code == 200
    assert response.json()["environment"]["environment"] == "staging"
    assert store.calls == [("get", "staging")]
    assert audit.events[0]["action"] == "mac.environment.read"
    assert audit.events[0]["outcome"] == "success"


def test_mac_environment_draft_uses_issuer_scoped_actor_and_audits(monkeypatch):
    from odei_api.security.auth import Principal

    principal = Principal(subject="operator-1", issuer=ISSUER)
    client, store, audit = _client(monkeypatch, principal)
    response = client.post(
        "/api/v1/mac/environments/staging/drafts",
        json={"config": {"replicas": 2}, "change_summary": "Initial staging"},
    )
    assert response.status_code == 201
    name, arguments = store.calls[0]
    assert name == "create_draft"
    assert arguments["actor"] == _actor_id(principal)
    assert audit.events[0]["action"] == "mac.environment.draft.create"
    assert audit.events[0]["outcome"] == "success"


def test_mac_environment_permission_is_resolved_from_server_registry(monkeypatch):
    from odei_api.security.auth import Principal

    principal = Principal(subject="unassigned", issuer=ISSUER)
    client, _store, audit = _client(monkeypatch, principal, ("read_only_auditor",))
    response = client.post(
        "/api/v1/mac/environments/staging/drafts",
        json={"config": {"replicas": 2}, "change_summary": "Unauthorized"},
    )
    assert response.status_code == 403
    assert audit.events[0]["action"] == "mac.environment.authorization"
    assert audit.events[0]["outcome"] == "denied"


def test_mac_revision_api_rejects_boolean_version_values(monkeypatch):
    from odei_api.security.auth import Principal

    principal = Principal(subject="operator-1", issuer=ISSUER)
    client, store, _audit = _client(monkeypatch, principal)
    response = client.post(
        "/api/v1/mac/environments/staging/submit",
        json={"version": True, "expected_latest_version": 1},
    )
    assert response.status_code == 422
    assert store.calls == []
