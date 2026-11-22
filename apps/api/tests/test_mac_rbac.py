import json

import pytest
from fastapi import HTTPException

from odei_api.config import Settings
from odei_api.security.auth import Principal
from odei_api.security.mac_rbac import (
    parse_mac_operator_registry,
    require_mac_permission,
    resolve_mac_access,
)


ISSUER = "https://identity.example.test/"
SUBJECT = "operator-123"


def test_mac_registry_resolves_only_exact_verified_issuer_and_subject():
    raw = json.dumps([{
        "issuer": ISSUER,
        "subject": SUBJECT,
        "roles": ["security_admin", "read_only_auditor"],
    }])
    access = resolve_mac_access(raw, issuer=ISSUER, subject=SUBJECT)
    assert access["roles"] == ["read_only_auditor", "security_admin"]
    assert "mac:secrets:manage" in access["permissions"]
    assert "mac:audit:read" in access["permissions"]
    assert resolve_mac_access(raw, issuer=ISSUER, subject="other") == {
        "roles": [], "permissions": [],
    }
    assert resolve_mac_access(raw, issuer="https://other.example/", subject=SUBJECT) == {
        "roles": [], "permissions": [],
    }


@pytest.mark.parametrize("raw", [
    "{",
    "[]",
    '[{"issuer":"http://identity.example.test","subject":"x","roles":["platform_owner"]}]',
    '[{"issuer":"https://identity.example.test/","subject":"x","roles":["unknown"]}]',
    '[{"issuer":"https://identity.example.test/","subject":"x","roles":["platform_owner"],"extra":true}]',
    '[{"issuer":"https://identity.example.test/","subject":"x","roles":["platform_owner"]},'
    '{"issuer":"https://identity.example.test/","subject":"x","roles":["security_admin"]}]',
])
def test_mac_registry_rejects_malformed_or_ambiguous_assignments(raw):
    with pytest.raises(ValueError):
        parse_mac_operator_registry(raw)


def test_settings_validate_mac_operator_registry():
    valid = json.dumps([{
        "issuer": ISSUER, "subject": SUBJECT, "roles": ["platform_owner"],
    }])
    assert Settings(mac_platform_operators_json=valid).mac_platform_operators_json == valid
    with pytest.raises(ValueError):
        Settings(mac_platform_operators_json='[{"issuer":"https://id.test","subject":"x","roles":["root"]}]')


def test_mac_permission_helper_fails_closed_for_missing_permission():
    access = resolve_mac_access(json.dumps([{
        "issuer": ISSUER, "subject": SUBJECT, "roles": ["read_only_auditor"],
    }]), issuer=ISSUER, subject=SUBJECT)
    require_mac_permission(access, "mac:audit:read")
    with pytest.raises(HTTPException) as error:
        require_mac_permission(access, "mac:secrets:manage")
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "MAC_PERMISSION_DENIED"


class AuditEventStore:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)


def _call_mac_access(monkeypatch, *, principal, registry):
    from fastapi.testclient import TestClient

    from odei_api.main import app, settings
    from odei_api.security.auth import get_current_principal

    previous_audit = getattr(app.state, "audit_event_store", None)
    previous_registry = settings.mac_platform_operators_json
    audit = AuditEventStore()
    app.state.audit_event_store = audit
    monkeypatch.setattr(settings, "mac_platform_operators_json", registry)
    app.dependency_overrides[get_current_principal] = lambda: principal
    try:
        response = TestClient(app).get("/api/v1/mac/access")
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.state.audit_event_store = previous_audit
        monkeypatch.setattr(settings, "mac_platform_operators_json", previous_registry)
    return response, audit


def test_mac_access_endpoint_returns_roles_and_audits_success(monkeypatch):
    raw = json.dumps([{
        "issuer": ISSUER, "subject": SUBJECT, "roles": ["platform_owner"],
    }])
    response, audit = _call_mac_access(
        monkeypatch,
        principal=Principal(subject=SUBJECT, issuer=ISSUER),
        registry=raw,
    )
    assert response.status_code == 200
    assert response.json()["roles"] == ["platform_owner"]
    assert "mac:secrets:manage" in response.json()["permissions"]
    assert len(audit.events) == 1
    assert audit.events[0]["action"] == "mac.access.read"
    assert audit.events[0]["outcome"] == "success"
    assert audit.events[0]["organization_id"] == "platform"


def test_mac_access_endpoint_denies_unassigned_identity_and_audits_denial(monkeypatch):
    raw = json.dumps([{
        "issuer": ISSUER, "subject": SUBJECT, "roles": ["platform_owner"],
    }])
    response, audit = _call_mac_access(
        monkeypatch,
        principal=Principal(subject="unassigned", issuer=ISSUER),
        registry=raw,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "MAC_OPERATOR_REQUIRED"
    assert audit.events[0]["outcome"] == "denied"
