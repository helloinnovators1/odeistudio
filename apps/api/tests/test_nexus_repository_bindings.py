from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal
from odei_api.services.github_app import VerifiedGitHubRepository


class Collection:
    def __init__(self, rows=()):
        self.rows = [dict(row) for row in rows]
    async def find_one(self, query):
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                return dict(row)
        return None
    async def insert_one(self, document):
        self.rows.append(dict(document))
    async def replace_one(self, query, document, upsert=False):
        for index, row in enumerate(self.rows):
            if all(row.get(key) == value for key, value in query.items()):
                self.rows[index] = dict(document)
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)
    async def delete_one(self, query):
        for index, row in enumerate(self.rows):
            if all(row.get(key) == value for key, value in query.items()):
                self.rows.pop(index)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class Database:
    def __init__(self):
        self.collections = {
            "organization_memberships": Collection([{
                "organization_id": "org", "identity_issuer": "https://id.example/",
                "identity_subject": "owner", "status": "active",
            }, {
                "organization_id": "org", "identity_issuer": "https://id.example/",
                "identity_subject": "intruder", "status": "active",
            }]),
            "projects": Collection([{
                "organization_id": "org", "project_id": "project", "status": "active",
                "owner_issuer": "https://id.example/", "owner_subject": "owner",
            }]),
            "project_memberships": Collection(),
            "nexus_repository_bindings": Collection(),
        }
    def __getitem__(self, name):
        return self.collections[name]


class Audit:
    def __init__(self):
        self.events = []
    async def append(self, **event):
        self.events.append(event)


class GitHub:
    async def verify_repository(self, *, installation_id, owner, name):
        assert (installation_id, owner, name) == (77, "acme", "service")
        return VerifiedGitHubRepository(
            installation_id=77, repository_id=123, repository_node_id="R_kgDOabc",
            owner="Acme", name="Service", full_name="Acme/Service",
            default_branch="main", contents_permission="write",
            pull_requests_permission="write", default_branch_sha="a" * 40, private=True,
        )


def install(principal):
    keys = ("mongo_database", "audit_event_store", "github_app_client")
    previous = {key: getattr(app.state, key, None) for key in keys}
    database, audit = Database(), Audit()
    app.state.mongo_database = database
    app.state.audit_event_store = audit
    app.state.github_app_client = GitHub()
    app.dependency_overrides[get_current_principal] = lambda: principal
    return previous, database, audit


def restore(previous):
    app.dependency_overrides.pop(get_current_principal, None)
    for key, value in previous.items():
        setattr(app.state, key, value)


def test_project_owner_binds_verified_repository_and_versioned_replacement():
    previous, database, audit = install(Principal(
        subject="owner", issuer="https://id.example/",
    ))
    try:
        client = TestClient(app)
        url = "/api/v1/organizations/org/projects/project/repository-binding"
        first = client.put(url, json={
            "installation_id": 77, "owner": "acme", "repository": "service",
        })
        assert first.status_code == 200, first.text
        binding = first.json()["binding"]
        assert binding["repository"]["id"] == 123
        assert binding["repository"]["node_id"] == "R_kgDOabc"
        assert binding["repository"]["default_branch"] == "main"
        assert binding["binding_version"] == 1
        assert "token" not in first.text.lower()
        second = client.put(url, json={
            "installation_id": 77, "owner": "acme", "repository": "service",
            "expected_version": 1,
        })
        assert second.status_code == 200, second.text
        assert second.json()["binding"]["binding_version"] == 2
        assert audit.events[0]["action"] == "nexus.repository_binding.bind"
        assert any(event["outcome"] == "success" for event in audit.events)
        assert len(database["nexus_repository_bindings"].rows) == 1
    finally:
        restore(previous)


def test_repository_binding_rejects_non_owner_and_stale_version():
    previous, database, _audit = install(Principal(
        subject="intruder", issuer="https://id.example/",
    ))
    database["project_memberships"].rows.append({
        "organization_id": "org", "project_id": "project",
        "identity_issuer": "https://id.example/", "identity_subject": "intruder",
        "status": "active",
    })
    try:
        response = TestClient(app).put(
            "/api/v1/organizations/org/projects/project/repository-binding",
            json={"installation_id": 77, "owner": "acme", "repository": "service"},
        )
        assert response.status_code == 403
    finally:
        restore(previous)

    previous, _database, _audit = install(Principal(
        subject="owner", issuer="https://id.example/",
    ))
    try:
        response = TestClient(app).put(
            "/api/v1/organizations/org/projects/project/repository-binding",
            json={"installation_id": 77, "owner": "acme", "repository": "service",
                  "expected_version": 9},
        )
        assert response.status_code == 409
    finally:
        restore(previous)


def test_repository_binding_remove_requires_exact_version():
    previous, database, _audit = install(Principal(
        subject="owner", issuer="https://id.example/",
    ))
    try:
        now = datetime.now(timezone.utc)
        database["nexus_repository_bindings"].rows.append({
            "_id": "org:project", "organization_id": "org", "project_id": "project",
            "binding_version": 3, "created_at": now,
        })
        url = "/api/v1/organizations/org/projects/project/repository-binding"
        stale = TestClient(app).request("DELETE", url, json={"expected_version": 2})
        assert stale.status_code == 409
        removed = TestClient(app).request("DELETE", url, json={"expected_version": 3})
        assert removed.status_code == 200
        assert removed.json() == {"removed": True, "binding_version": 3}
    finally:
        restore(previous)
