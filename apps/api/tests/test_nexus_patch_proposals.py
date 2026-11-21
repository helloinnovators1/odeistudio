from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal
from odei_api.services.patch_proposals import sha256_text


class FakeCollection:
    def __init__(self, document):
        self.document = document

    async def find_one(self, query):
        if self.document is None:
            return None
        return self.document


class FakeDatabase:
    def __init__(self):
        self.collections = {
            "organization_memberships": FakeCollection({"status": "active"}),
            "projects": FakeCollection({
                "organization_id": "org-1", "project_id": "project-1",
                "status": "active", "owner_issuer": "https://identity.example/",
                "owner_subject": "owner-1",
            }),
            "project_memberships": FakeCollection(None),
        }

    def __getitem__(self, name):
        return self.collections[name]


class FakeAudit:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)


class FakePatchStore:
    def __init__(self):
        self.documents = {}

    async def create(self, **values):
        item = {
            "proposal_id": values["proposal_id"],
            "organization_id": values["organization_id"],
            "project_id": values["project_id"],
            "owner_issuer": values["owner_issuer"],
            "owner_subject": values["owner_subject"],
            "title": values["title"],
            "files": values["files"],
            "status": "pending",
            "version": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "decided_by_issuer": None,
            "decided_by_subject": None,
            "decided_at": None,
        }
        self.documents[item["proposal_id"]] = item
        return item

    async def list_for_project(self, *, organization_id, project_id, owner_issuer=None, owner_subject=None, limit=30):
        items = [
            item for item in self.documents.values()
            if item["organization_id"] == organization_id and item["project_id"] == project_id
            and (owner_issuer is None or item["owner_issuer"] == owner_issuer)
            and (owner_subject is None or item["owner_subject"] == owner_subject)
        ]
        return sorted(items, key=lambda item: item["updated_at"], reverse=True)[:limit]

    async def get(self, *, organization_id, project_id, proposal_id):
        item = self.documents.get(proposal_id)
        if item and item["organization_id"] == organization_id and item["project_id"] == project_id:
            return item
        return None

    async def decide(self, *, organization_id, project_id, proposal_id, expected_version, decision, actor_issuer, actor_subject):
        item = await self.get(organization_id=organization_id, project_id=project_id, proposal_id=proposal_id)
        if item is None or item["status"] != "pending" or item["version"] != expected_version:
            return None
        item["status"] = decision
        item["version"] += 1
        item["decided_by_issuer"] = actor_issuer
        item["decided_by_subject"] = actor_subject
        item["decided_at"] = datetime.now(timezone.utc)
        item["updated_at"] = item["decided_at"]
        return item


@pytest.fixture
def patch_state():
    previous = {
        key: getattr(app.state, key, None)
        for key in ("mongo_database", "audit_event_store", "patch_proposal_store")
    }
    database, audit, store = FakeDatabase(), FakeAudit(), FakePatchStore()
    app.state.mongo_database = database
    app.state.audit_event_store = audit
    app.state.patch_proposal_store = store
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="owner-1", issuer="https://identity.example/",
    )
    try:
        yield database, audit, store
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        for key, value in previous.items():
            setattr(app.state, key, value)


def _payload():
    base = "print('old')\n"
    return {
        "title": "Update greeting",
        "base_files": {"src/main.py": base},
        "changes": {"src/main.py": "print('new')\n"},
        "expected_base_hashes": {"src/main.py": sha256_text(base)},
        "cloud_model_consent": True,
    }


def test_patch_proposal_is_persisted_redacted_and_owner_approved(patch_state):
    _, audit, _ = patch_state
    client = TestClient(app)
    response = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals",
        json=_payload(),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["application_enabled"] is False
    assert body["files"][0]["operation"] == "update"
    assert "print('new')" in body["files"][0]["content"]

    listed = client.get(
        "/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals"
    )
    assert listed.status_code == 200
    assert listed.json()["can_decide"] is True
    assert listed.json()["proposals"][0]["proposal_id"] == body["proposal_id"]

    detail = client.get(
        f"/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals/{body['proposal_id']}"
    )
    assert detail.status_code == 200
    assert detail.json()["files"][0]["base_sha256"] == sha256_text("print('old')\n")
    assert detail.json()["can_decide"] is True

    approved = client.post(
        f"/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals/{body['proposal_id']}/approve",
        json={"expected_version": 0},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["version"] == 1
    assert approved.json()["application_enabled"] is False
    assert store.documents[body["proposal_id"]]["decided_by_subject"] == "owner-1"
    assert audit.events[-1]["action"] == "nexus.patch_proposal.decision"
    assert audit.events[-1]["outcome"] == "success"


def test_patch_proposal_rejects_stale_base_hash_and_missing_consent(patch_state):
    client = TestClient(app)
    payload = _payload()
    payload["expected_base_hashes"]["src/main.py"] = "0" * 64
    response = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals",
        json=payload,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_PATCH_PROPOSAL"

    payload = _payload()
    payload["cloud_model_consent"] = False
    response = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals",
        json=payload,
    )
    assert response.status_code == 422


def test_patch_proposal_secret_is_redacted_before_persistence(patch_state):
    _, _, store = patch_state
    client = TestClient(app)
    payload = _payload()
    secret = "sk-proj-" + "A" * 28
    payload["changes"]["src/main.py"] = "api_key = '" + secret + "'\n"
    response = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals",
        json=payload,
    )
    assert response.status_code == 201, response.text
    saved = next(iter(store.documents.values()))
    assert secret not in saved["files"][0]["content"]
    assert "[REDACTED]" in saved["files"][0]["content"]
    assert secret not in saved["files"][0]["unified_diff"]


def test_patch_proposal_decision_requires_project_owner(patch_state, monkeypatch):
    database, _, _ = patch_state
    client = TestClient(app)
    created = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals",
        json=_payload(),
    ).json()
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="member-2", issuer="https://identity.example/",
    )
    database.collections["project_memberships"].document = {
        "status": "active", "role": "developer",
    }
    response = client.post(
        f"/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals/{created['proposal_id']}/approve",
        json={"expected_version": 0},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PROJECT_OWNER_REQUIRED"


def test_apply_capability_requires_approved_owner_decision_and_binds_workspace(patch_state, monkeypatch):
    _, audit, _ = patch_state
    client = TestClient(app)
    created = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals",
        json=_payload(),
    ).json()
    path = f"/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals/{created['proposal_id']}/apply-capability"
    request = {
        "expected_version": 0,
        "workspace_id": "workspace_1234567890123456",
        "confirm_apply": True,
    }
    pending = client.post(path, json=request)
    assert pending.status_code == 409
    assert pending.json()["detail"]["code"] == "PATCH_PROPOSAL_NOT_APPROVED"

    client.post(
        f"/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals/{created['proposal_id']}/approve",
        json={"expected_version": 0},
    )
    monkeypatch.setattr(
        "odei_api.services.nexus_patch_proposals.issue_patch_apply_capability",
        lambda **kwargs: ("signed-capability", 1_900_000_000, "f" * 64),
    )
    request["expected_version"] = 1
    response = client.post(path, json=request)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["capability"] == "signed-capability"
    assert body["workspace_id"] == request["workspace_id"]
    assert body["proposal_version"] == 1
    assert body["application_enabled"] is False
    assert "signed-capability" not in str(audit.events)
    assert audit.events[-1]["action"] == "nexus.patch_proposal.apply_capability"


def test_apply_capability_requires_project_owner_and_explicit_confirmation(patch_state, monkeypatch):
    database, _, _ = patch_state
    client = TestClient(app)
    created = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals",
        json=_payload(),
    ).json()
    client.post(
        f"/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals/{created['proposal_id']}/approve",
        json={"expected_version": 0},
    )
    path = f"/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals/{created['proposal_id']}/apply-capability"
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="member-2", issuer="https://identity.example/",
    )
    database.collections["project_memberships"].document = {
        "status": "active", "role": "developer",
    }
    response = client.post(path, json={
        "expected_version": 1,
        "workspace_id": "workspace_1234567890123456",
        "confirm_apply": True,
    })
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PROJECT_OWNER_REQUIRED"



def test_apply_capability_fails_closed_without_signing_configuration(patch_state):
    client = TestClient(app)
    created = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals",
        json=_payload(),
    ).json()
    path = f"/api/v1/organizations/org-1/projects/project-1/nexus/patch-proposals/{created['proposal_id']}"
    client.post(path + "/approve", json={"expected_version": 0})
    response = client.post(path + "/apply-capability", json={
        "expected_version": 1,
        "workspace_id": "workspace_1234567890123456",
        "confirm_apply": True,
    })
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PATCH_APPROVAL_SIGNING_UNAVAILABLE"

    unconfirmed = client.post(path + "/apply-capability", json={
        "expected_version": 1,
        "workspace_id": "workspace_1234567890123456",
        "confirm_apply": False,
    })
    assert unconfirmed.status_code == 422
