from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, length):
        return self.rows[:length]


class Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    async def find_one(self, query, **_kwargs):
        return next((row for row in self.rows if all(row.get(k) == v for k, v in query.items())), None)

    async def insert_one(self, document, **_kwargs):
        self.rows.append(dict(document))
        return SimpleNamespace(inserted_id=len(self.rows))

    def find(self, query, *_args, **_kwargs):
        def matches(row):
            for key, value in query.items():
                if key == "$or":
                    if not any(all(row.get(k) == v for k, v in option.items()) for option in value):
                        return False
                elif isinstance(value, dict) and "$in" in value:
                    if row.get(key) not in value["$in"]:
                        return False
                elif row.get(key) != value:
                    return False
            return True
        return Cursor([row for row in self.rows if matches(row)])

    async def update_one(self, query, update, **_kwargs):
        row = await self.find_one(query)
        if row is None:
            return SimpleNamespace(matched_count=0)
        row.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1)


class Session:
    @asynccontextmanager
    async def _transaction(self):
        yield

    async def start_transaction(self):
        return self._transaction()


class MongoClient:
    @asynccontextmanager
    async def start_session(self):
        yield Session()


class Audit:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)


class Database:
    def __init__(self):
        self.collections = {
            "organization_memberships": Collection([{
                "organization_id": "org-1", "identity_issuer": "https://identity.example/",
                "identity_subject": "owner", "status": "active", "role": "owner",
            }, {
                "organization_id": "org-1", "identity_issuer": "https://identity.example/",
                "identity_subject": "member", "status": "active", "role": "member",
            }]),
            "projects": Collection(),
            "project_memberships": Collection(),
        }

    def __getitem__(self, key):
        return self.collections[key]


def test_authenticated_identity_can_discover_only_active_organizations():
    previous = {
        key: getattr(app.state, key, None)
        for key in ("mongo_database", "mongo_client", "audit_event_store")
    }
    database, audit = Database(), Audit()
    database["organization_memberships"].rows.extend([
        {
            "organization_id": "org-2",
            "identity_issuer": "https://identity.example/",
            "identity_subject": "owner",
            "status": "active",
            "role": "member",
        },
        {
            "organization_id": "org-secret",
            "identity_issuer": "https://identity.example/",
            "identity_subject": "someone-else",
            "status": "active",
            "role": "owner",
        },
        {
            "organization_id": "org-disabled",
            "identity_issuer": "https://identity.example/",
            "identity_subject": "owner",
            "status": "inactive",
            "role": "owner",
        },
    ])
    app.state.mongo_database = database
    app.state.audit_event_store = audit
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="owner", issuer="https://identity.example/",
    )
    try:
        response = TestClient(app).get("/api/v1/organizations")
        assert response.status_code == 200, response.text
        assert response.json()["organizations"] == [
            {"organization_id": "org-1", "role": "owner"},
            {"organization_id": "org-2", "role": "member"},
        ]
        assert response.json()["limit"] == 100
        assert [event["action"] for event in audit.events] == ["organization.list", "organization.list"]
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        for key, value in previous.items():
            setattr(app.state, key, value)


def test_project_create_list_and_membership_lifecycle():
    previous = {
        key: getattr(app.state, key, None)
        for key in ("mongo_database", "mongo_client", "audit_event_store")
    }
    database, audit = Database(), Audit()
    app.state.mongo_database = database
    app.state.mongo_client = MongoClient()
    app.state.audit_event_store = audit
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="owner", issuer="https://identity.example/",
    )
    client = TestClient(app)
    try:
        created = client.post(
            "/api/v1/organizations/org-1/projects",
            json={"name": "ODEI Workspace", "description": "Primary project"},
        )
        assert created.status_code == 201, created.text
        project = created.json()
        assert project["name"] == "ODEI Workspace"
        assert project["owner"]["subject"] == "owner"
        assert audit.events[-1]["action"] == "project.create"
        assert audit.events[-1]["session"] is not None

        listed = client.get("/api/v1/organizations/org-1/projects")
        assert listed.status_code == 200, listed.text
        assert [item["project_id"] for item in listed.json()["projects"]] == [project["project_id"]]

        member = client.put(
            f"/api/v1/organizations/org-1/projects/{project['project_id']}/members",
            json={"identity_issuer": "https://identity.example/", "identity_subject": "member"},
        )
        assert member.status_code == 200, member.text
        assert member.json()["status"] == "active"
        assert audit.events[-1]["action"] == "project.member.add"
        assert audit.events[-1]["session"] is not None

        members = client.get(
            f"/api/v1/organizations/org-1/projects/{project['project_id']}/members"
        )
        assert members.status_code == 200, members.text
        assert members.json()["members"][0]["identity_subject"] == "member"
        assert audit.events[-1]["action"] == "project.member.list"

        removed = client.request(
            "DELETE",
            f"/api/v1/organizations/org-1/projects/{project['project_id']}/members",
            json={"identity_issuer": "https://identity.example/", "identity_subject": "member"},
        )
        assert removed.status_code == 200, removed.text
        assert removed.json()["status"] == "inactive"
        assert audit.events[-1]["action"] == "project.member.remove"
        assert audit.events[-1]["session"] is not None
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        for key, value in previous.items():
            setattr(app.state, key, value)


def test_project_membership_target_must_be_active_org_member():
    previous = {
        key: getattr(app.state, key, None)
        for key in ("mongo_database", "mongo_client", "audit_event_store")
    }
    database, audit = Database(), Audit()
    app.state.mongo_database = database
    app.state.mongo_client = MongoClient()
    app.state.audit_event_store = audit
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="owner", issuer="https://identity.example/",
    )
    try:
        project_id = "project-test"
        database["projects"].rows.append({
            "organization_id": "org-1", "project_id": project_id,
            "name": "Project", "description": "", "status": "active",
            "owner_issuer": "https://identity.example/", "owner_subject": "owner",
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        })
        response = TestClient(app).put(
            f"/api/v1/organizations/org-1/projects/{project_id}/members",
            json={"identity_issuer": "https://identity.example/", "identity_subject": "unknown"},
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "ORGANIZATION_MEMBER_NOT_FOUND"
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        for key, value in previous.items():
            setattr(app.state, key, value)
