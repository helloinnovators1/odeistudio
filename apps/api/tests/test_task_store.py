from copy import deepcopy

import pytest

from odei_api.services.audit_store import MongoAuditEventStore
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


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, field, direction):
        self.documents.sort(key=lambda row: row[field], reverse=direction < 0)
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    async def to_list(self, length):
        return deepcopy(self.documents[:length])


class FakeCollection:
    def __init__(self):
        self.documents = {}

    async def create_index(self, *args, **kwargs):
        return "index"

    async def insert_one(self, document, session=None):
        key = document["_id"] if "_id" in document else document["event_id"]
        self.documents[key] = deepcopy(document)

    def find(self, query):
        minimum = query["version"]["$gt"]
        rows = [
            deepcopy(row) for row in self.documents.values()
            if row.get("organization_id") == query["organization_id"]
            and row.get("task_id") == query["task_id"]
            and row.get("version", -1) > minimum
        ]
        return FakeCursor(rows)

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


def make_store(events_collection=None, audit_collection=None):
    tasks = FakeCollection()
    events = events_collection or FakeCollection()
    audit_events = audit_collection or FakeCollection()
    client = FakeClient([tasks, events, audit_events])
    audit_store = MongoAuditEventStore(audit_events)
    return MongoTaskStore(tasks, events, client, audit_store=audit_store), tasks, events


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



def audit_event():
    return {
        "organization_id": "org-1",
        "actor_issuer": "https://identity.example.test/",
        "actor_subject": "user-1",
        "action": "nexus.task.create",
        "target_type": "nexus_task",
        "target_id": "task-1",
        "outcome": "success",
        "request_id": "req-task-1",
        "metadata": {"project_id": "project-1"},
    }


@pytest.mark.asyncio
async def test_create_planned_atomically_persists_approval_ready_task_lifecycle_and_audit():
    store, tasks, events = make_store()
    await store.initialize()
    result = await store.create_planned(
        make_task(), plan="Inspect, implement, test", audit_event=audit_event()
    )
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
    audit_rows = list(store._audit_store._collection.documents.values())
    assert len(audit_rows) == 1
    assert audit_rows[0]["action"] == "nexus.task.create"
    assert audit_rows[0]["target_id"] == "task-1"


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



class FailingAuditCollection(FakeCollection):
    async def insert_one(self, document, session=None):
        raise RuntimeError("audit store unavailable")


@pytest.mark.asyncio
async def test_planned_task_and_lifecycle_roll_back_when_audit_insert_fails():
    store, tasks, events = make_store(audit_collection=FailingAuditCollection())
    with pytest.raises(RuntimeError, match="audit store unavailable"):
        await store.create_planned(
            make_task(), plan="Plan", audit_event=audit_event()
        )
    assert tasks.documents == {}
    assert events.documents == {}


@pytest.mark.asyncio
async def test_task_transition_and_event_roll_back_when_audit_insert_fails():
    store, tasks, events = make_store(audit_collection=FailingAuditCollection())
    await store.create(make_task())
    with pytest.raises(RuntimeError, match="audit store unavailable"):
        await store.transition(
            organization_id="org-1", task_id="task-1",
            next_status=TaskStatus.CONTEXT_GATHERING, expected_version=0,
            audit_event=audit_event(),
        )
    assert tasks.documents["task-1"]["status"] == "created"
    assert tasks.documents["task-1"]["version"] == 0
    assert len(events.documents) == 1


@pytest.mark.asyncio
async def test_task_transition_commits_audit_and_state_together():
    store, tasks, events = make_store()
    await store.create(make_task())
    updated = await store.transition(
        organization_id="org-1", task_id="task-1",
        next_status=TaskStatus.CONTEXT_GATHERING, expected_version=0,
        audit_event=audit_event(),
    )
    audit_rows = list(store._audit_store._collection.documents.values())
    assert updated.status is TaskStatus.CONTEXT_GATHERING
    assert tasks.documents["task-1"]["status"] == "context_gathering"
    assert len(events.documents) == 2
    assert len(audit_rows) == 1


@pytest.mark.asyncio
async def test_basic_task_create_commits_audit_with_task_and_event():
    store, tasks, events = make_store()
    await store.create(make_task(), audit_event=audit_event())
    assert tasks.documents["task-1"]["status"] == "created"
    assert len(events.documents) == 1
    audit_rows = list(store._audit_store._collection.documents.values())
    assert len(audit_rows) == 1
    assert audit_rows[0]["action"] == "nexus.task.create"


@pytest.mark.asyncio
async def test_basic_task_create_rolls_back_when_audit_insert_fails():
    store, tasks, events = make_store(audit_collection=FailingAuditCollection())
    with pytest.raises(RuntimeError, match="audit store unavailable"):
        await store.create(make_task(), audit_event=audit_event())
    assert tasks.documents == {}
    assert events.documents == {}


@pytest.mark.asyncio
async def test_task_events_use_ordered_reconnectable_version_cursor():
    store, _, _ = make_store()
    await store.create_planned(make_task(), plan="Plan")
    rows, has_more = await store.list_events(
        organization_id="org-1", task_id="task-1", after_version=-1, limit=2
    )
    assert [row["version"] for row in rows] == [0, 1]
    assert has_more is True
    next_rows, next_has_more = await store.list_events(
        organization_id="org-1", task_id="task-1", after_version=1, limit=2
    )
    assert [row["version"] for row in next_rows] == [2, 3]
    assert next_has_more is False


@pytest.mark.asyncio
async def test_task_events_reject_invalid_cursor_and_limit():
    store, _, _ = make_store()
    with pytest.raises(ValueError, match="cursor or page size"):
        await store.list_events(
            organization_id="org-1", task_id="task-1", after_version=-2
        )
    with pytest.raises(ValueError, match="cursor or page size"):
        await store.list_events(
            organization_id="org-1", task_id="task-1", limit=101
        )
