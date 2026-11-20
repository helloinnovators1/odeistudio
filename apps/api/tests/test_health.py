import pytest
from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal

client = TestClient(app)


class FakeAuditStore:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)
        return event


@pytest.fixture
def audit_store():
    previous = getattr(app.state, "audit_event_store", None)
    store = FakeAuditStore()
    app.state.audit_event_store = store
    try:
        yield store
    finally:
        app.state.audit_event_store = previous



def test_root_reports_service_identity() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"service": "odei-studio-api", "status": "running"}


def test_liveness_endpoint() -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_reports_missing_mongodb_as_not_ready() -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "status": "not_ready",
            "checks": {"mongodb": "not_configured"},
        }
    }


def test_current_identity_fails_closed_without_oidc_configuration() -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "AUTH_NOT_CONFIGURED"


def test_current_identity_returns_only_verified_identity() -> None:
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="user-123", issuer="https://identity.example.test/"
    )
    try:
        response = client.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
    assert response.status_code == 200
    assert response.json() == {
        "subject": "user-123",
        "issuer": "https://identity.example.test/",
    }


class FakeMembershipCollection:
    def __init__(self, membership):
        self.membership = membership
        self.query = None

    async def find_one(self, query):
        self.query = query
        return self.membership


class FakeDatabase:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "organization_memberships"
        return self.collection


def test_organization_membership_uses_verified_identity_and_returns_safe_fields(audit_store) -> None:
    collection = FakeMembershipCollection(
        {
            "organization_id": "org-1",
            "identity_issuer": "https://identity.example.test/",
            "identity_subject": "user-123",
            "status": "active",
            "role": "developer",
            "billing_customer_secret": "must-never-leak",
        }
    )
    previous_database = getattr(app.state, "mongo_database", None)
    app.state.mongo_database = FakeDatabase(collection)
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="user-123", issuer="https://identity.example.test/"
    )
    try:
        response = client.get("/api/v1/organizations/org-1/membership")
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.state.mongo_database = previous_database
    assert response.status_code == 200
    assert response.json() == {"organization_id": "org-1", "role": "developer"}
    assert collection.query == {
        "organization_id": "org-1",
        "identity_issuer": "https://identity.example.test/",
        "identity_subject": "user-123",
        "status": "active",
    }
    assert "must-never-leak" not in response.text
    assert len(audit_store.events) == 1
    assert audit_store.events[0]["action"] == "organization.membership.read"
    assert audit_store.events[0]["outcome"] == "success"
    assert audit_store.events[0]["organization_id"] == "org-1"


def test_organization_membership_fails_closed_when_store_is_missing() -> None:
    previous_database = getattr(app.state, "mongo_database", None)
    app.state.mongo_database = None
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="user-123", issuer="https://identity.example.test/"
    )
    try:
        response = client.get("/api/v1/organizations/org-1/membership")
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.state.mongo_database = previous_database
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MEMBERSHIP_STORE_UNAVAILABLE"


def test_organization_membership_denies_unknown_tenant(audit_store) -> None:
    previous_database = getattr(app.state, "mongo_database", None)
    app.state.mongo_database = FakeDatabase(FakeMembershipCollection(None))
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="user-123", issuer="https://identity.example.test/"
    )
    try:
        response = client.get("/api/v1/organizations/org-other/membership")
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.state.mongo_database = previous_database
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ORGANIZATION_ACCESS_DENIED"
    assert len(audit_store.events) == 1
    assert audit_store.events[0]["outcome"] == "denied"
    assert audit_store.events[0]["metadata"] == {"reason": "active_membership_required"}


def test_organization_membership_rejects_whitespace_padded_tenant_id() -> None:
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="user-123", issuer="https://identity.example.test/"
    )
    try:
        response = client.get("/api/v1/organizations/%20org-1/membership")
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_ORGANIZATION_ID"



def test_organization_membership_fails_closed_on_malformed_record() -> None:
    previous_database = getattr(app.state, "mongo_database", None)
    app.state.mongo_database = FakeDatabase(FakeMembershipCollection({"status": "active"}))
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="user-123", issuer="https://identity.example.test/"
    )
    try:
        response = client.get("/api/v1/organizations/org-1/membership")
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.state.mongo_database = previous_database
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MEMBERSHIP_RECORD_INVALID"


def test_organization_membership_fails_closed_on_database_error() -> None:
    from pymongo.errors import ServerSelectionTimeoutError

    class UnavailableCollection:
        async def find_one(self, query):
            raise ServerSelectionTimeoutError("database unavailable")

    previous_database = getattr(app.state, "mongo_database", None)
    app.state.mongo_database = FakeDatabase(UnavailableCollection())
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="user-123", issuer="https://identity.example.test/"
    )
    try:
        response = client.get("/api/v1/organizations/org-1/membership")
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.state.mongo_database = previous_database
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MEMBERSHIP_STORE_UNAVAILABLE"
