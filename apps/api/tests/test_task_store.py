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



@pytest.mark.asyncio
async def test_create_planned_atomically_persists_approval_ready_task_and_lifecycle():
    store, tasks, events = make_store()
    await store.initialize()
    result = await store.create_planned(make_task(), plan="Inspect, implement, test")
    assert result.status is TaskStatus.AWAITING_APPROVAL
    assert result.version == 3
    assert result.plan == "Inspect, implement, test"
    rows = sorted(events.documents.values(), key=lambda row: row["version"])
    assert [row["version"] for row in rows] == [0, 1, 2, 3]
    assert [row.get("to_status", row.get("status")) for row in rows] == [
        "created", "context_gathering", "planning", "awaiting_approval",
    ]
    assert rows[-1]["type"] == "task.approval.requested"
    assert tasks.documents["task-1"]["status"] == "awaiting_approval"


@pytest.mark.asyncio
async def test_create_planned_rolls_back_task_and_all_events_on_event_failure():
    store, tasks, events = make_store(FailingEventCollection())
    with pytest.raises(RuntimeError, match="event store unavailable"):
        await store.create_planned(make_task(), plan="Plan")
    assert tasks.documents == {}
    assert events.documents == {}


@pytest.mark.asyncio
async def test_create_planned_rejects_empty_plan():
    store, _, _ = make_store()
    with pytest.raises(ValueError, match="non-empty plan"):
        await store.create_planned(make_task(), plan="  ")
