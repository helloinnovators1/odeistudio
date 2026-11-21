import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal
from odei_api.services.patch_proposals import sha256_text


class Collection:
    def __init__(self, document):
        self.document = document

    async def find_one(self, query):
        return self.document


class Database:
    def __init__(self):
        self.collections = {
            "organization_memberships": Collection({"status": "active"}),
            "projects": Collection({
                "organization_id": "org-1", "project_id": "project-1",
                "status": "active", "owner_issuer": "https://identity.example/",
                "owner_subject": "owner-1",
            }),
            "project_memberships": Collection(None),
        }

    def __getitem__(self, name):
        return self.collections[name]


class Audit:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)


class ConversationStore:
    def __init__(self):
        self.item = {
            "conversation_id": "conversation-1",
            "organization_id": "org-1",
            "project_id": "project-1",
            "owner_issuer": "https://identity.example/",
            "owner_subject": "owner-1",
            "messages": [],
            "version": 0,
        }

    async def get_for_owner(self, **scope):
        item = self.item
        if any(item.get(key) != value for key, value in scope.items()):
            return None
        return item

    async def append(self, *, organization_id, project_id, owner_issuer, owner_subject,
                     conversation_id, role, content, expected_version=None):
        item = await self.get_for_owner(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=owner_issuer, owner_subject=owner_subject,
            conversation_id=conversation_id,
        )
        if item is None or item["version"] != expected_version:
            return None
        item["messages"].append({"role": role, "content": content})
        item["version"] += 1
        return item


class PatchStore:
    def __init__(self):
        self.items = {}

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
        self.items[item["proposal_id"]] = item
        return item


@pytest.fixture
def patch_generation_state():
    keys = ("mongo_database", "audit_event_store", "conversation_store", "patch_proposal_store")
    previous = {key: getattr(app.state, key, None) for key in keys}
    database, audit, conversations, patches = Database(), Audit(), ConversationStore(), PatchStore()
    app.state.mongo_database = database
    app.state.audit_event_store = audit
    app.state.conversation_store = conversations
    app.state.patch_proposal_store = patches
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="owner-1", issuer="https://identity.example/",
    )
    try:
        yield audit, conversations, patches
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        for key, value in previous.items():
            setattr(app.state, key, value)


def test_chat_generates_and_persists_review_only_single_file_patch(patch_generation_state, monkeypatch):
    audit, conversations, patches = patch_generation_state

    class FakeResponses:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(output_text=json.dumps({"content": "print('new')\\n"}))

    fake_client = SimpleNamespace(responses=FakeResponses())
    monkeypatch.setattr(
        "odei_api.services.nexus_patch_proposals.get_openai_client",
        lambda: (fake_client, "patch-test-model"),
    )
    response = TestClient(app).post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat/propose-patch",
        json={
            "title": "Update greeting",
            "prompt": "Change the greeting from old to new",
            "path": "src/main.py",
            "base_content": "print('old')\\n",
            "conversation_id": "conversation-1",
            "cloud_model_consent": True,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["can_approve"] is True
    assert body["application_enabled"] is False
    assert body["model"] == "patch-test-model"
    assert body["files"][0]["content"] == "print('new')\\n"
    assert body["files"][0]["base_sha256"] == sha256_text("print('old')\\n")
    assert fake_client.responses.calls[0]["store"] is False
    assert conversations.item["messages"][-1]["role"] == "assistant"
    assert audit.events[-1]["action"] == "nexus.patch_proposal.generate"
    assert audit.events[-1]["outcome"] == "success"
    assert next(iter(patches.items.values()))["status"] == "pending"


def test_chat_patch_generation_requires_cloud_consent_and_owned_conversation(patch_generation_state):
    payload = {
        "prompt": "Update the greeting",
        "path": "src/main.py",
        "base_content": "print('old')\\n",
        "conversation_id": "missing-conversation",
        "cloud_model_consent": False,
    }
    client = TestClient(app)
    response = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat/propose-patch",
        json=payload,
    )
    assert response.status_code == 400
    payload["cloud_model_consent"] = True
    response = client.post(
        "/api/v1/organizations/org-1/projects/project-1/nexus/chat/propose-patch",
        json=payload,
    )
    assert response.status_code == 404
