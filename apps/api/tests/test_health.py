from fastapi.testclient import TestClient

from odei_api.main import app

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
