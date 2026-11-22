"""Route-level tests for authenticated MAC environment governance."""

import pytest
from fastapi import HTTPException

from odei_api.security.auth import Principal
from odei_api.services.mac_environment_api import _mutate_with_audit

ISSUER = "https://identity.example.test/"
OTHER_ISSUER = "https://other-identity.example.test/"


class AuditStore:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)


class DeploymentStore:
    def __init__(self):
        self.attempts = {}

    async def create_attempt(self, **kwargs):
        self.attempts["attempt-12345678901234567890123456789012"] = {
            "environment": kwargs["environment"], "state": "queued",
            "revision": kwargs["version"], "provider": kwargs["provider"],
        }
        return {"_id": "attempt-12345678901234567890123456789012", **self.attempts["attempt-12345678901234567890123456789012"]}

    async def get(self, attempt_id):
        return {"_id": attempt_id, **self.attempts[attempt_id]}


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


def _client(monkeypatch, principal, roles=("platform_owner",)):
    import importlib
    import json

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
        lambda: type("Settings", (), {"mac_platform_operators_json": registry})(),
    )
    app = FastAPI()
    app.include_router(router)
    store = EnvironmentStore()
    audit = AuditStore()
    class TransactionSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def with_transaction(self, callback): return await callback(self)

    class TransactionClient:
        def start_session(self): return TransactionSession()

    app.state.mongo_database = type("Database", (), {"client": TransactionClient()})()
    app.state.mac_environment_store = store
    app.state.mac_deployment_store = DeploymentStore()
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
    from odei_api.services.mac_environment_api import _actor_id

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
    submit = client.post(
        "/api/v1/mac/environments/staging/submit",
        json={"version": True, "expected_latest_version": 1},
    )
    rollback = client.post(
        "/api/v1/mac/environments/staging/rollback-drafts",
        json={"target_version": 1, "expected_latest_version": True,
              "change_summary": "Reject boolean as a revision"},
    )
    assert submit.status_code == 422
    assert rollback.status_code == 422
    assert store.calls == []


def test_mac_lifecycle_routes_forward_verified_actor_and_compare_and_set_versions(monkeypatch):
    from odei_api.security.auth import Principal
    from odei_api.services.mac_environment_api import _actor_id

    principal = Principal(subject="operator-1", issuer=ISSUER)
    client, store, audit = _client(monkeypatch, principal)
    update = client.put(
        "/api/v1/mac/environments/staging/drafts/1",
        json={"config": {"replicas": 3}, "change_summary": "Update",
              "expected_latest_version": 1},
    )
    submit = client.post(
        "/api/v1/mac/environments/staging/submit",
        json={"version": 1, "expected_latest_version": 1},
    )
    approve = client.post(
        "/api/v1/mac/environments/staging/approve",
        json={"version": 1, "expected_latest_version": 1},
    )
    promote = client.post(
        "/api/v1/mac/environments/staging/promote",
        json={"version": 1, "expected_latest_version": 1,
              "expected_active_version": 0},
    )
    rollback = client.post(
        "/api/v1/mac/environments/staging/rollback-drafts",
        json={"target_version": 1, "expected_latest_version": 1,
              "change_summary": "Restore"},
    )
    assert [item.status_code for item in (update, submit, approve, promote, rollback)] == [200, 200, 200, 200, 201]
    assert all(call[1]["actor"] == _actor_id(principal) for call in store.calls)
    assert [event["outcome"] for event in audit.events] == ["success"] * 5


def test_mac_success_audit_uses_same_mongo_transaction_session():
    from types import SimpleNamespace

    from odei_api.security.auth import Principal
    from odei_api.services.mac_environment_api import _mutate_with_audit

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return False
        async def with_transaction(self, callback): return await callback(self)

    class Client:
        def start_session(self): return Session()

    class Store:
        def __init__(self): self.session = None
        async def create_draft(self, **kwargs):
            self.session = kwargs["session"]
            return {"version": 1}

    class Audit:
        def __init__(self): self.session = None
        async def append(self, **kwargs): self.session = kwargs["session"]

    session_client = Client()
    store, audit = Store(), Audit()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        mongo_database=SimpleNamespace(client=session_client)
    )))
    principal = Principal(subject="operator-1", issuer=ISSUER)
    result = await _mutate_with_audit(
        request, store, audit, principal, "mac.environment.draft.create",
        "staging", "create_draft", environment="staging", actor="oidc-actor",
        config={"replicas": 2}, change_summary="Initial",
    )
    assert result["version"] == 1
    assert store.session is audit.session
    assert store.session is not None



def test_mac_deployment_request_is_authenticated_idempotent_boundary_and_audited(monkeypatch):
    from odei_api.security.auth import Principal

    principal = Principal(subject="operator-1", issuer=ISSUER)
    client, _store, audit = _client(monkeypatch, principal, ("infrastructure_admin",))
    response = client.post(
        "/api/v1/mac/environments/staging/deployments",
        json={"version": 2, "provider": "aws", "idempotency_key": "request-12345678"},
    )
    assert response.status_code == 202
    assert response.json()["deployment"]["state"] == "queued"
    assert audit.events[0]["action"] == "mac.deployment.request"
    assert audit.events[0]["outcome"] == "success"


def test_mac_deployment_request_rejects_boolean_revision(monkeypatch):
    from odei_api.security.auth import Principal

    principal = Principal(subject="operator-1", issuer=ISSUER)
    client, _store, _audit = _client(monkeypatch, principal)
    response = client.post(
        "/api/v1/mac/environments/staging/deployments",
        json={"version": True, "provider": "aws", "idempotency_key": "request-12345678"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_mac_mutation_fails_closed_without_transaction_support():
    from types import SimpleNamespace

    class Store:
        called = False
        async def create_draft(self, **_kwargs):
            self.called = True
            return {"version": 1}

    class Audit:
        called = False
        async def append(self, **_kwargs):
            self.called = True

    store, audit = Store(), Audit()
    request = SimpleNamespace(app=SimpleNamespace(
        state=SimpleNamespace(mongo_database=object())
    ))
    with pytest.raises(HTTPException) as failure:
        await _mutate_with_audit(
            request, store, audit, Principal(subject="operator-1", issuer=ISSUER),
            "mac.environment.draft.create", "staging", "create_draft",
            environment="staging", actor="oidc-actor", config={"replicas": 2},
            change_summary="Must fail closed",
        )
    assert failure.value.status_code == 503
    assert failure.value.detail["code"] == "TRANSACTIONAL_AUDIT_UNAVAILABLE"
    assert store.called is False
    assert audit.called is False



def test_infrastructure_admin_cannot_approve_environment_revision(monkeypatch):
    from odei_api.security.auth import Principal

    principal = Principal(subject="requester-only", issuer=ISSUER)
    client, _store, audit = _client(monkeypatch, principal, ("infrastructure_admin",))
    response = client.post(
        "/api/v1/mac/environments/staging/approve",
        json={"version": 1, "expected_latest_version": 1},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "MAC_PERMISSION_DENIED"
    assert audit.events[0]["outcome"] == "denied"
