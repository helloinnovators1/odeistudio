from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError

from odei_api.services.repository_merge_approvals import (
    MongoRepositoryMergeApprovalStore,
    RepositoryMergeApprovalConflict,
)


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


class FakeProjects:
    async def update_one(self, *_args, **_kwargs):
        return SimpleNamespace(matched_count=1)


class Collection:
    def __init__(self):
        self.documents = {}
        self.indexes = []

    async def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    async def insert_one(self, document, **_kwargs):
        key = (document["organization_id"], document["project_id"], document["run_id"])
        if any(
            (row["organization_id"], row["project_id"], row["run_id"]) == key
            for row in self.documents.values()
        ):
            raise DuplicateKeyError("one approval per run")
        self.documents[document["_id"]] = dict(document)

    async def find_one_and_update(self, query, update, **_kwargs):
        row = self.documents.get(query["_id"])
        if row is None:
            return None
        for key, value in query.items():
            if key == "_id":
                continue
            if isinstance(value, dict) and "$gt" in value:
                if row.get(key) is None or row[key] <= value["$gt"]:
                    return None
            elif row.get(key) != value:
                return None
        row.update(update.get("$set", {}))
        for key, value in update.get("$inc", {}).items():
            row[key] = row.get(key, 0) + value
        return dict(row)


def approval_values():
    return {
        "organization_id": "org-1", "project_id": "project-1",
        "task_id": "task-1", "run_id": "run-1",
        "actor_issuer": "https://identity.example/",
        "actor_subject": "project-owner",
        "repository_id": 123, "repository_node_id": "R_kgDOabc",
        "installation_id": 77, "binding_version": 4,
        "owner": "Acme", "name": "Service", "default_branch": "main",
        "base_sha": "b" * 40, "commit_sha": "c" * 40, "tree_sha": "d" * 40,
        "branch": "odei/nexus/run-1", "pull_request_number": 12,
        "pull_request_url": "https://github.com/Acme/Service/pull/12",
    }


@pytest.mark.asyncio
async def test_merge_approval_is_durable_single_use_and_bound_to_same_owner():
    collection = Collection()
    store = MongoRepositoryMergeApprovalStore(collection, FakeClient(), FakeProjects())
    await store.initialize()
    approval = await store.create(**approval_values())
    assert approval["status"] == "pending"
    assert approval["expires_at"] > datetime.now(timezone.utc)
    assert len(collection.indexes) == 2

    wrong_actor = await store.consume(
        approval_id=approval["approval_id"], organization_id="org-1",
        project_id="project-1", task_id="task-1", run_id="run-1",
        actor_issuer="https://identity.example/", actor_subject="another-owner",
    )
    assert wrong_actor is None

    consumed = await store.consume(
        approval_id=approval["approval_id"], organization_id="org-1",
        project_id="project-1", task_id="task-1", run_id="run-1",
        actor_issuer="https://identity.example/", actor_subject="project-owner",
    )
    assert consumed["status"] == "consuming"
    assert consumed["version"] == 2
    assert await store.consume(
        approval_id=approval["approval_id"], organization_id="org-1",
        project_id="project-1", task_id="task-1", run_id="run-1",
        actor_issuer="https://identity.example/", actor_subject="project-owner",
    ) is None

    finished = await store.finish(
        approval_id=approval["approval_id"], organization_id="org-1",
        project_id="project-1", status="consumed", merge_commit_sha="e" * 40,
    )
    assert finished["status"] == "consumed"
    assert finished["merge_commit_sha"] == "e" * 40
    with pytest.raises(RepositoryMergeApprovalConflict):
        await store.create(**approval_values())


@pytest.mark.asyncio
async def test_expired_approval_cannot_be_consumed():
    collection = Collection()
    store = MongoRepositoryMergeApprovalStore(collection, FakeClient(), FakeProjects())
    approval = await store.create(**approval_values())
    collection.documents[approval["_id"]]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    assert await store.consume(
        approval_id=approval["approval_id"], organization_id="org-1",
        project_id="project-1", task_id="task-1", run_id="run-1",
        actor_issuer="https://identity.example/", actor_subject="project-owner",
    ) is None


@pytest.mark.asyncio
async def test_failed_approval_is_terminal_and_not_reusable():
    collection = Collection()
    store = MongoRepositoryMergeApprovalStore(collection, FakeClient(), FakeProjects())
    approval = await store.create(**approval_values())
    await store.consume(
        approval_id=approval["approval_id"], organization_id="org-1",
        project_id="project-1", task_id="task-1", run_id="run-1",
        actor_issuer="https://identity.example/", actor_subject="project-owner",
    )
    failed = await store.finish(
        approval_id=approval["approval_id"], organization_id="org-1",
        project_id="project-1", status="failed",
        failure_code="GITHUB_PROVENANCE_OR_MERGE_FAILED",
    )
    assert failed["status"] == "failed"
    assert failed["merge_commit_sha"] is None

def test_merge_approval_store_rejects_missing_lifecycle_dependencies():
    with pytest.raises(ValueError, match="transactional project lifecycle fencing"):
        MongoRepositoryMergeApprovalStore(Collection(), None, None)

