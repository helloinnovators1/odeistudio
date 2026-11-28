from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal
from odei_api.services.github_app import VerifiedGitHubRepository


class FakeSession:
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_):
        return False
    async def start_transaction(self):
        return self


class FakeClient:
    def start_session(self):
        return FakeSession()


class Collection:
    def __init__(self, rows=()):
        self.rows = [dict(row) for row in rows]

    @staticmethod
    def _value(row, key):
        value = row
        for part in key.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    @classmethod
    def _matches(cls, row, query):
        for key, expected in query.items():
            actual = cls._value(row, key)
            if isinstance(expected, dict) and "$exists" in expected:
                if (actual is not None) != expected["$exists"]:
                    return False
            elif isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif isinstance(expected, dict) and "$lte" in expected:
                if actual is None or actual > expected["$lte"]:
                    return False
            elif actual != expected:
                return False
        return True

    async def find_one(self, query, **_kwargs):
        for row in self.rows:
            if self._matches(row, query):
                return dict(row)
        return None

    async def insert_one(self, document, **_kwargs):
        self.rows.append(dict(document))

    async def update_one(self, query, update, **_kwargs):
        for row in self.rows:
            if self._matches(row, query):
                for key in update.get("$unset", {}):
                    row.pop(key, None)
                for key, value in update.get("$set", {}).items():
                    row[key] = value
                for key, amount in update.get("$inc", {}).items():
                    row[key] = row.get(key, 0) + amount
                return SimpleNamespace(modified_count=1, matched_count=1)
        return SimpleNamespace(modified_count=0, matched_count=0)

    async def replace_one(self, query, document, upsert=False, **_kwargs):
        for index, row in enumerate(self.rows):
            if self._matches(row, query):
                self.rows[index] = dict(document)
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def delete_one(self, query, **_kwargs):
        for index, row in enumerate(self.rows):
            if self._matches(row, query):
                self.rows.pop(index)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class Database:
    def __init__(self):
        self.client = FakeClient()
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
            "execution_runs": Collection(),
            "nexus_repository_merge_approvals": Collection(),
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
    keys = ("mongo_database", "mongo_client", "audit_event_store", "github_app_client")
    previous = {key: getattr(app.state, key, None) for key in keys}
    database, audit = Database(), Audit()
    app.state.mongo_database = database
    app.state.mongo_client = database.client
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





def test_expired_repository_merge_lock_is_recovered_before_rebinding():
    previous, database, _audit = install(Principal(
        subject="owner", issuer="https://id.example/",
    ))
    database["nexus_repository_bindings"].rows.append({
        "_id": "org:project", "organization_id": "org", "project_id": "project",
        "state": "verified", "installation_id": 77, "repository_id": 123,
        "repository_node_id": "R_kgDOabc", "owner": "Acme", "name": "Service",
        "full_name": "Acme/Service", "default_branch": "main",
        "binding_version": 3,
        "merge_lock": {
            "approval_id": "a" * 32, "run_id": "run-1",
            "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        },
    })
    try:
        response = TestClient(app).put(
            "/api/v1/organizations/org/projects/project/repository-binding",
            json={
                "installation_id": 77, "owner": "acme", "repository": "service",
                "expected_version": 3,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["binding"]["binding_version"] == 4
        assert "merge_lock" not in database["nexus_repository_bindings"].rows[0]
    finally:
        restore(previous)


def test_repository_binding_cannot_change_while_human_merge_is_locked():
    previous, database, _audit = install(Principal(
        subject="owner", issuer="https://id.example/",
    ))
    database["nexus_repository_bindings"].rows.append({
        "_id": "org:project", "organization_id": "org", "project_id": "project",
        "state": "verified", "installation_id": 77, "repository_id": 123,
        "repository_node_id": "R_kgDOabc", "owner": "Acme", "name": "Service",
        "full_name": "Acme/Service", "default_branch": "main",
        "binding_version": 3,
        "merge_lock": {
            "approval_id": "a" * 32, "run_id": "run-1",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=2),
        },
    })
    try:
        url = "/api/v1/organizations/org/projects/project/repository-binding"
        bind = TestClient(app).put(url, json={
            "installation_id": 77, "owner": "acme", "repository": "service",
            "expected_version": 3,
        })
        assert bind.status_code == 409
        remove = TestClient(app).request("DELETE", url, json={"expected_version": 3})
        assert remove.status_code == 409
        assert len(database["nexus_repository_bindings"].rows) == 1
    finally:
        restore(previous)


def test_repository_binding_cannot_change_while_execution_is_active():
    previous, database, _audit = install(Principal(
        subject="owner", issuer="https://id.example/",
    ))
    database["execution_runs"].rows.append({
        "organization_id": "org", "project_id": "project", "status": "running",
    })
    try:
        url = "/api/v1/organizations/org/projects/project/repository-binding"
        bind = TestClient(app).put(url, json={
            "installation_id": 77, "owner": "acme", "repository": "service",
        })
        assert bind.status_code == 409
        assert bind.json()["detail"]["code"] == "REPOSITORY_BINDING_LOCKED"
        remove = TestClient(app).request("DELETE", url, json={"expected_version": 1})
        assert remove.status_code == 409
        assert remove.json()["detail"]["code"] == "REPOSITORY_BINDING_LOCKED"
    finally:
        restore(previous)



def test_repository_binding_mutations_reject_active_runs_inside_transaction():
    principal = Principal(subject="owner", issuer="https://id.example/")
    previous, database, _audit = install(principal)
    database["execution_runs"].rows.append({
        "organization_id": "org", "project_id": "project",
        "_id": "run-active", "status": "running",
    })
    try:
        client = TestClient(app)
        url = "/api/v1/organizations/org/projects/project/repository-binding"
        bind = client.put(url, json={
            "installation_id": 77, "owner": "acme", "repository": "service",
        })
        assert bind.status_code == 409
        assert bind.json()["detail"]["code"] == "REPOSITORY_BINDING_LOCKED"
        assert database["nexus_repository_bindings"].rows == []

        database["nexus_repository_bindings"].rows.append({
            "_id": "org:project", "organization_id": "org",
            "project_id": "project", "binding_version": 1,
        })
        remove = client.request("DELETE", url, json={"expected_version": 1})
        assert remove.status_code == 409
        assert remove.json()["detail"]["code"] == "REPOSITORY_BINDING_LOCKED"
        assert len(database["nexus_repository_bindings"].rows) == 1
    finally:
        restore(previous)
