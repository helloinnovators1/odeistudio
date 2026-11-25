from __future__ import annotations

from fastapi.testclient import TestClient

from odei_api.main import app
from odei_api.security.auth import Principal, get_current_principal


class Collection:
    def __init__(self, rows):
        self.rows = list(rows)

    async def find_one(self, query):
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                return row
        return None


class Database:
    def __init__(self):
        self.collections = {
            "organization_memberships": Collection([
                {
                    "organization_id": "org-1",
                    "identity_issuer": "https://identity.example/",
                    "identity_subject": "owner",
                    "status": "active",
                },
                {
                    "organization_id": "org-1",
                    "identity_issuer": "https://identity.example/",
                    "identity_subject": "intruder",
                    "status": "active",
                },
            ]),
            "projects": Collection([{
                "organization_id": "org-1", "project_id": "project-1",
                "status": "active", "owner_issuer": "https://identity.example/",
                "owner_subject": "owner",
            }]),
            "project_memberships": Collection([]),
        }

    def __getitem__(self, key):
        return self.collections[key]


class Audit:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)


class SnapshotStore:
    async def get_latest_for_tenant(self, *, organization_id, project_id):
        assert (organization_id, project_id) == ("org-1", "project-1")
        return {"_id": "snapshot-1", "sha256": "f" * 64}


class RepositoryStore:
    async def get_state(self, *, organization_id, project_id):
        assert (organization_id, project_id) == ("org-1", "project-1")
        return {
            "organization_id": organization_id, "project_id": project_id,
            "revision": 7, "revision_id": "private-revision",
            "snapshot_id": "snapshot-1", "snapshot_sha256": "f" * 64,
            "indexed_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "expires_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "file_count": 1, "total_bytes": 22, "symbol_count": 1,
            "reference_count": 0, "import_count": 0, "chunk_count": 1,
            "embedding_model": "text-embedding-3-small", "chunk_limit_reached": False,
        }

    async def get_active_files(self, *, organization_id, project_id):
        return [{
            "path": "src/main.py", "content": "alpha\nneedle found here\nomega",
            "sha256": "a" * 64,
        }]


def _install_state(principal):
    previous = {
        key: getattr(app.state, key, None)
        for key in ("mongo_database", "repository_index_store", "audit_event_store", "workspace_snapshot_store")
    }
    database, audit = Database(), Audit()
    app.state.mongo_database = database
    app.state.repository_index_store = RepositoryStore()
    app.state.workspace_snapshot_store = SnapshotStore()
    app.state.audit_event_store = audit
    app.dependency_overrides[get_current_principal] = lambda: principal
    return previous, audit


def _restore_state(previous):
    app.dependency_overrides.pop(get_current_principal, None)
    for key, value in previous.items():
        setattr(app.state, key, value)


def test_authenticated_project_search_returns_hash_and_snapshot_provenance():
    previous, audit = _install_state(Principal(
        subject="owner", issuer="https://identity.example/",
    ))
    try:
        response = TestClient(app).get(
            "/api/v1/organizations/org-1/projects/project-1/repository-index/search",
            params={"q": "needle"},
        )
        assert response.status_code == 200, response.text
        result, = response.json()["results"]
        assert result == {
            "path": "src/main.py", "line": 2, "snippet": "needle found here",
            "sha256": "a" * 64, "revision": 7, "snapshot_id": "snapshot-1",
        }
        assert audit.events[-1]["action"] == "repository.search.exact"
        assert audit.events[-1]["metadata"]["query_length"] == 6
    finally:
        _restore_state(previous)


def test_project_search_hides_another_users_project():
    previous, _audit_store = _install_state(Principal(
        subject="intruder", issuer="https://identity.example/",
    ))
    try:
        response = TestClient(app).get(
            "/api/v1/organizations/org-1/projects/project-1/repository-index/search",
            params={"q": "needle"},
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    finally:
        _restore_state(previous)


def test_semantic_search_requires_explicit_cloud_consent():
    previous, _audit_store = _install_state(Principal(
        subject="owner", issuer="https://identity.example/",
    ))
    try:
        response = TestClient(app).post(
            "/api/v1/organizations/org-1/projects/project-1/repository-index/semantic-search",
            json={"query": "where is the worker started?", "cloud_model_consent": False},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "CLOUD_MODEL_CONSENT_REQUIRED"
    finally:
        _restore_state(previous)

def test_project_regex_search_is_bounded_and_returns_provenance():
    previous, audit = _install_state(Principal(
        subject="owner", issuer="https://identity.example/",
    ))
    try:
        response = TestClient(app).get(
            "/api/v1/organizations/org-1/projects/project-1/repository-index/search",
            params={"q": r"needle\s+found", "regex": "true"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["mode"] == "regex"
        result, = response.json()["results"]
        assert result["path"] == "src/main.py"
        assert result["sha256"] == "a" * 64
        assert audit.events[-1]["action"] == "repository.search.regex"
    finally:
        _restore_state(previous)


def test_project_regex_search_rejects_invalid_expression():
    previous, _audit_store = _install_state(Principal(
        subject="owner", issuer="https://identity.example/",
    ))
    try:
        response = TestClient(app).get(
            "/api/v1/organizations/org-1/projects/project-1/repository-index/search",
            params={"q": "(", "regex": "true"},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "REGEX_INVALID"
    finally:
        _restore_state(previous)


def test_project_regex_search_times_out_pathological_expression():
    previous, _audit_store = _install_state(Principal(
        subject="owner", issuer="https://identity.example/",
    ))
    class PathologicalStore(RepositoryStore):
        async def get_active_files(self, *, organization_id, project_id):
            return [{
                "path": "src/large.txt", "content": "a" * 100_000 + "!",
                "sha256": "b" * 64,
            }]
    app.state.repository_index_store = PathologicalStore()
    try:
        response = TestClient(app).get(
            "/api/v1/organizations/org-1/projects/project-1/repository-index/search",
            params={"q": r"^(a+)+$", "regex": "true"},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "REGEX_SEARCH_BUDGET_EXCEEDED"
    finally:
        _restore_state(previous)

def test_project_search_fails_closed_when_index_snapshot_is_stale():
    previous, _audit_store = _install_state(Principal(
        subject="owner", issuer="https://identity.example/",
    ))
    class NewerSnapshotStore:
        async def get_latest_for_tenant(self, *, organization_id, project_id):
            return {"_id": "snapshot-2", "sha256": "e" * 64}
    app.state.workspace_snapshot_store = NewerSnapshotStore()
    try:
        response = TestClient(app).get(
            "/api/v1/organizations/org-1/projects/project-1/repository-index/search",
            params={"q": "needle"},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "REPOSITORY_INDEX_STALE"
    finally:
        _restore_state(previous)
