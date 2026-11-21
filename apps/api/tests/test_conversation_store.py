from copy import deepcopy
from datetime import datetime, timezone

import pytest

from odei_api.services.conversation_store import (
    MAX_CONVERSATION_MESSAGES,
    MongoConversationStore,
)


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, field, direction):
        self.rows.sort(key=lambda row: row[field], reverse=direction < 0)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, length):
        return deepcopy(self.rows[:length])


class Collection:
    def __init__(self):
        self.documents = {}

    async def create_index(self, *_args, **_kwargs):
        return "index"

    async def insert_one(self, document):
        self.documents[document["conversation_id"]] = deepcopy(document)

    def find(self, query, _projection=None):
        rows = [
            deepcopy(row) for row in self.documents.values()
            if all(row.get(key) == value for key, value in query.items())
        ]
        return Cursor(rows)

    async def find_one(self, query, _projection=None):
        for row in self.documents.values():
            if all(row.get(key) == value for key, value in query.items()):
                return deepcopy(row)
        return None

    async def find_one_and_update(self, query, update, return_document=None):
        row = self.documents.get(query["conversation_id"])
        if row is None:
            return None
        for key in ("organization_id", "project_id", "owner_issuer", "owner_subject"):
            if row.get(key) != query[key]:
                return None
        if "version" in query and row["version"] != query["version"]:
            return None
        if len(row["messages"]) >= MAX_CONVERSATION_MESSAGES:
            return None
        if sum(len(item["content"]) for item in row["messages"]) + len(update["$push"]["messages"]["content"]) > 1_000_000:
            return None
        row["messages"].append(deepcopy(update["$push"]["messages"]))
        row["version"] += update["$inc"]["version"]
        row["updated_at"] = update["$set"]["updated_at"]
        return deepcopy(row)


@pytest.mark.asyncio
async def test_conversation_store_scopes_reads_to_owner_project_and_organization():
    collection = Collection()
    store = MongoConversationStore(collection)
    await store.initialize()
    created = await store.create(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="alice", title="Chat",
    )
    assert await store.get_for_owner(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="alice",
        conversation_id=created["conversation_id"],
    ) is not None
    assert await store.get_for_owner(
        organization_id="org-b", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="alice",
        conversation_id=created["conversation_id"],
    ) is None
    assert await store.get_for_owner(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="mallory",
        conversation_id=created["conversation_id"],
    ) is None


@pytest.mark.asyncio
async def test_conversation_append_uses_optimistic_version_and_persists_messages():
    collection = Collection()
    store = MongoConversationStore(collection)
    created = await store.create(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="alice", title="Chat",
    )
    common = {
        "organization_id": "org-a", "project_id": "project-a",
        "owner_issuer": "https://id.example/", "owner_subject": "alice",
        "conversation_id": created["conversation_id"],
    }
    updated = await store.append(**common, role="user", content="Hello", expected_version=0)
    assert updated["version"] == 1
    assert updated["messages"][0]["content"] == "Hello"
    assert await store.append(**common, role="assistant", content="Hi", expected_version=0) is None
    final = await store.append(**common, role="assistant", content="Hi", expected_version=1)
    assert final["version"] == 2
    assert [item["role"] for item in final["messages"]] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_conversation_list_is_owner_scoped_and_bounded():
    collection = Collection()
    store = MongoConversationStore(collection)
    await store.create(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="alice", title="A",
    )
    await store.create(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="bob", title="B",
    )
    rows = await store.list_for_owner(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="alice", limit=10,
    )
    assert len(rows) == 1
    assert rows[0]["title"] == "A"


@pytest.mark.asyncio
async def test_conversation_store_rejects_invalid_title_and_message():
    collection = Collection()
    store = MongoConversationStore(collection)
    with pytest.raises(ValueError):
        await store.create(
            organization_id="org-a", project_id="project-a",
            owner_issuer="https://id.example/", owner_subject="alice", title=" ",
        )
    created = await store.create(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="alice", title="Chat",
    )
    with pytest.raises(ValueError):
        await store.append(
            organization_id="org-a", project_id="project-a",
            owner_issuer="https://id.example/", owner_subject="alice",
            conversation_id=created["conversation_id"], role="system", content="bad",
        )
