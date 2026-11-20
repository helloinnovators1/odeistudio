from copy import deepcopy

import pytest

from odei_api.services.task_store import MongoTaskStore
from odei_api.services.tasks import InvalidTaskTransition, TaskRecord, TaskStatus


class FakeTransaction:
    def __init__(self, collections):
        self.collections = collections
        self.snapshots = None

    async def __aenter__(self):
        self.snapshots = [deepcopy(collection.documents) for collection in self.collections]
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        if exc_type is not None and self.snapshots is not None:
            for collection, snapshot in zip(self.collections, self.snapshots):
                collection.documents = snapshot
        return False


class FakeSession:
    def __init__(self, collections):
        self.collections = collections

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def start_transaction(self):
        return FakeTransaction(self.collections)


class FakeClient:
    def __init__(self, collections):
        self.collections = collections

    def start_session(self):
        return FakeSession(self.collections)


class FakeCollection:
    def __init__(self):
        self.documents = {}

    async def create_index(self, *args, **kwargs):
        return "index"

    async def insert_one(self, document, session=None):
        key = document["_id"] if "_id" in document else document["event_id"]
        self.documents[key] = deepcopy(document)

    async def find_one(self, query):
        document = self.documents.get(query["_id"])
        if document and document["organization_id"] == query["organization_id"]:
            return deepcopy(document)
        return None

    async def find_one_and_update(self, query, update, return_document=None, session=None):
        document = self.documents.get(query["_id"])
        if not document:
            return None
        if document["organization_id"] != query["organization_id"]:
            return None
        if document["version"] != query["version"] or document["status"] != query["status"]:
            return None
        document.update(deepcopy(update["$set"]))
        document["version"] += update["$inc"]["version"]
        return deepcopy(document)


class FailingEventCollection(FakeCollection):
    async def insert_one(self, document, session=None):
        raise RuntimeError("event store unavailable")


def make_task():
    return TaskRecord(
        id="task-1", organization_id="org-1", project_id="project-1",
        owner_id="user-1", goal="Implement project indexing",
    )


def make_store(events_collection=None):
    tasks = FakeCollection()
    events = events_collection or FakeCollection()
    client = FakeClient([tasks, events])
    return MongoTaskStore(tasks, events, client), tasks, events


@pytest.mark.asyncio
async def test_task_store_scopes_reads_to_organization():
    store, _, _ = make_store()
    await store.initialize()
    await store.create(make_task())
    assert await store.get(organization_id="org-1", task_id="task-1") is not None
    assert await store.get(organization_id="org-other", task_id="task-1") is None


@pytest.mark.asyncio
async def test_task_transition_persists_state_and_separate_event():
    store, tasks, events = make_store()
    await store.initialize()
    await store.create(make_task())
    task = await store.transition(
        organization_id="org-1", task_id="task-1",
        next_status=TaskStatus.CONTEXT_GATHERING, expected_version=0,
    )
    assert task.status is TaskStatus.CONTEXT_GATHERING
    assert task.version == 1
    raw_task = await tasks.find_one({"_id": "task-1", "organization_id": "org-1"})
    assert "events" not in raw_task
    event_rows = list(events.documents.values())
    assert len(event_rows) == 2
    assert event_rows[-1]["to_status"] == "context_gathering"


@pytest.mark.asyncio
async def test_task_create_rolls_back_when_event_insert_fails():
    store, tasks, _ = make_store(FailingEventCollection())
    with pytest.raises(RuntimeError, match="event store unavailable"):
        await store.create(make_task())
    assert tasks.documents == {}


@pytest.mark.asyncio
async def test_task_transition_rejects_wrong_organization():
    store, _, _ = make_store()
    await store.create(make_task())
    with pytest.raises(KeyError, match="not found"):
        await store.transition(
            organization_id="wrong-org", task_id="task-1",
            next_status=TaskStatus.CONTEXT_GATHERING, expected_version=0,
        )


@pytest.mark.asyncio
async def test_task_transition_rejects_stale_version():
    store, _, _ = make_store()
    await store.create(make_task())
    await store.transition(
        organization_id="org-1", task_id="task-1",
        next_status=TaskStatus.CONTEXT_GATHERING, expected_version=0,
    )
    with pytest.raises(InvalidTaskTransition):
        await store.transition(
            organization_id="org-1", task_id="task-1",
            next_status=TaskStatus.PLANNING, expected_version=0,
        )
