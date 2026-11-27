from __future__ import annotations

from types import SimpleNamespace

import pytest

from odei_api.services.repository_index_store import MongoRepositoryIndexStore


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
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.queries = []

    async def delete_one(self, query, **_kwargs):
        self.queries.append(query)
        before = len(self.rows)
        self.rows = [row for row in self.rows if not all(row.get(k) == v for k, v in query.items())]
        return SimpleNamespace(deleted_count=before-len(self.rows))

    async def delete_many(self, query, **_kwargs):
        self.queries.append(query)
        before = len(self.rows)
        self.rows = [row for row in self.rows if not all(row.get(k) == v for k, v in query.items())]
        return SimpleNamespace(deleted_count=before-len(self.rows))


class Database:
    def __init__(self):
        self.client = FakeClient()
        self.collections = {}
        for name in (
            "repository_index_state", "repository_index_files",
            "repository_index_symbols", "repository_index_references",
            "repository_index_imports", "repository_index_chunks",
        ):
            self.collections[name] = Collection([
                {"organization_id": "org-a", "project_id": "project-a", "revision_id": "old"},
                {"organization_id": "org-a", "project_id": "project-a", "revision_id": "active"},
                {"organization_id": "org-b", "project_id": "project-a", "revision_id": "other-tenant"},
                {"organization_id": "org-a", "project_id": "project-b", "revision_id": "other-project"},
            ])
        self.collections["projects"] = Collection([
            {"organization_id": "org-a", "project_id": "project-a", "status": "active"},
        ])
        async def update_one(query, update, **_kwargs):
            return SimpleNamespace(matched_count=1)
        self.collections["projects"].update_one = update_one

    def __getitem__(self, name):
        return self.collections[name]


@pytest.mark.asyncio
async def test_delete_project_index_removes_all_revisions_without_cross_tenant_deletion():
    database = Database()
    store = MongoRepositoryIndexStore(database)

    deleted = await store.delete_project_index(organization_id="org-a", project_id="project-a")

    assert deleted == {
        "state": 2, "files": 2, "symbols": 2, "references": 2,
        "imports": 2, "chunks": 2,
    }
    for name, collection in database.collections.items():
        if name == "projects":
            continue
        assert collection.rows == [
            {"organization_id": "org-b", "project_id": "project-a", "revision_id": "other-tenant"},
            {"organization_id": "org-a", "project_id": "project-b", "revision_id": "other-project"},
        ]
        assert collection.queries == [{
            "organization_id": "org-a", "project_id": "project-a",
        }]


@pytest.mark.asyncio
async def test_delete_project_index_is_idempotent():
    database = Database()
    store = MongoRepositoryIndexStore(database)
    first = await store.delete_project_index(organization_id="org-a", project_id="project-a")
    second = await store.delete_project_index(organization_id="org-a", project_id="project-a")
    assert sum(first.values()) == 12
    assert sum(second.values()) == 0


@pytest.mark.asyncio
async def test_delete_project_index_rejects_empty_scope():
    store = MongoRepositoryIndexStore(Database())
    with pytest.raises(ValueError):
        await store.delete_project_index(organization_id="", project_id="project-a")
