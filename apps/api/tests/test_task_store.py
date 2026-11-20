from copy import deepcopy

import pytest

from odei_api.services.task_store import MongoTaskStore
from odei_api.services.tasks import InvalidTaskTransition, TaskRecord, TaskStatus


class FakeCollection:
    def __init__(self):
        self.documents = {}

    async def create_index(self, *args, **kwargs):
        return "index"

    async def insert_one(self, document):
        self.documents[document["_id"]] = deepcopy(document)

    async def find_one(self, query):
        document = self.documents.get(query["_id"])
        if document and document["organization_id"] == query["organization_id"]:
            return deepcopy(document)
        return None

    async def find_one_and_update(self, query, update, return_document=None):
        document = self.documents.get(query["_id"])
        if not document:
            return None
        if document["organization_id"] != query["organization_id"]:
            return None
        if document["version"] != query["version"] or document["status"] != query["status"]:
            return None
        document.update(deepcopy(update["$set"]))
        document["version"] += update["$inc"]["version"]
        document["events"].append(deepcopy(update["$push"]["events"]))
        return deepcopy(document)


def make_task():
    return TaskRecord(
        id="task-1", organization_id="org-1", project_id="project-1",
        owner_id="user-1", goal="Implement project indexing",
    )


@pytest.mark.asyncio
async def test_task_store_scopes_reads_to_organization():
    store = MongoTaskStore(FakeCollection())
    await store.initialize()
    await store.create(make_task())
    assert await store.get(organization_id="org-1", task_id="task-1") is not None
    assert await store.get(organization_id="org-other", task_id="task-1") is None


@pytest.mark.asyncio
async def test_task_transition_persists_status_version_and_event():
    store = MongoTaskStore(FakeCollection())
    await store.create(make_task())
    task = await store.transition(
        organization_id="org-1", task_id="task-1",
        next_status=TaskStatus.CONTEXT_GATHERING, expected_version=0,
    )
    assert task.status is TaskStatus.CONTEXT_GATHERING
    assert task.version == 1
    raw = await store._collection.find_one({"_id": "task-1", "organization_id": "org-1"})
    assert len(raw["events"]) == 2
    assert raw["events"][-1]["to_status"] == "context_gathering"


@pytest.mark.asyncio
async def test_task_transition_rejects_wrong_organization():
    store = MongoTaskStore(FakeCollection())
    await store.create(make_task())
    with pytest.raises(KeyError, match="not found"):
        await store.transition(
            organization_id="wrong-org", task_id="task-1",
            next_status=TaskStatus.CONTEXT_GATHERING, expected_version=0,
        )


@pytest.mark.asyncio
async def test_task_transition_rejects_stale_version():
    store = MongoTaskStore(FakeCollection())
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
