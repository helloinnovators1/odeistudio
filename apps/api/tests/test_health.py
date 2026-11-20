from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal

client = TestClient(app)


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
