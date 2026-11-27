from copy import deepcopy

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
        return type("Result", (), {"matched_count": 1})()


def make_store(collection):
    return MongoConversationStore(collection, FakeClient(), FakeProjects())


class Collection:
    def __init__(self):
        self.documents = {}

    async def create_index(self, *_args, **_kwargs):
        return "index"

    async def insert_one(self, document, **_kwargs):
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

    async def delete_one(self, query, **_kwargs):
        key = query["conversation_id"]
        row = self.documents.get(key)
        if row is None or any(row.get(field) != query[field] for field in ("organization_id", "project_id", "owner_issuer", "owner_subject")):
            return type("DeleteResult", (), {"deleted_count": 0})()
        del self.documents[key]
        return type("DeleteResult", (), {"deleted_count": 1})()
    async def find_one_and_update(self, query, update, return_document=None, **_kwargs):
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
    store = make_store(collection)
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
    store = make_store(collection)
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
async def test_conversation_turn_persists_validated_mode_metadata():
    collection = Collection()
    store = make_store(collection)
    created = await store.create(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="alice", title="Mode history",
    )
    common = {
        "organization_id": "org-a", "project_id": "project-a",
        "owner_issuer": "https://id.example/", "owner_subject": "alice",
        "conversation_id": created["conversation_id"],
    }
    saved = await store.append(**common, role="user", content="Debug this", mode="debug", expected_version=0)
    assert saved["messages"][0]["mode"] == "debug"
    with pytest.raises(ValueError, match="mode"):
        await store.append(**common, role="assistant", content="Bad mode", mode="root", expected_version=1)


@pytest.mark.asyncio
async def test_conversation_list_is_owner_scoped_and_bounded():
    collection = Collection()
    store = make_store(collection)
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
    store = make_store(collection)
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


@pytest.mark.asyncio
async def test_conversation_delete_is_owner_scoped():
    collection = Collection()
    store = make_store(collection)
    created = await store.create(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="alice", title="Delete me",
    )
    common = {
        "organization_id": "org-a", "project_id": "project-a",
        "owner_issuer": "https://id.example/",
        "conversation_id": created["conversation_id"],
    }
    assert await store.delete_for_owner(**common, owner_subject="mallory") is False
    assert await store.delete_for_owner(**common, owner_subject="alice") is True


@pytest.mark.asyncio
async def test_conversation_store_redacts_secret_like_titles_and_messages():
    collection = Collection()
    store = make_store(collection)
    created = await store.create(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="alice",
        title="api_key=super_secret_token_12345",
    )
    saved = await store.append(
        organization_id="org-a", project_id="project-a",
        owner_issuer="https://id.example/", owner_subject="alice",
        conversation_id=created["conversation_id"], role="user",
        content="Please inspect api_key=super_secret_token_12345",
        expected_version=0,
    )
    assert "super_secret_token_12345" not in saved["title"]
    assert "super_secret_token_12345" not in saved["messages"][0]["content"]
