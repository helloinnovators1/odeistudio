from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from gridfs.errors import NoFile

from odei_api.services import gridfs_upload_intents as intents_module
from odei_api.services.gridfs_upload_intents import (
    MongoGridFSUploadIntentStore,
    UploadIntentLeaseLost,
)


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, key, direction=1):
        self.rows.sort(
            key=lambda row: (
                row.get(key) is not None,
                row.get(key) or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=direction < 0,
        )
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, length):
        return self.rows[:length]


class Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def start_transaction(self):
        return self


class Client:
    def start_session(self):
        return Session()


def _value(row, dotted):
    value = row
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _matches(row, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(row, clause) for clause in expected):
                return False
            continue
        actual = _value(row, key)
        if isinstance(expected, dict):
            if "$lte" in expected and (actual is None or actual > expected["$lte"]):
                return False
            if "$gt" in expected and (actual is None or actual <= expected["$gt"]):
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
        elif actual != expected:
            return False
    return True


class Collection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def find(self, query, projection=None):
        return Cursor([row for row in self.rows if _matches(row, query)])

    async def find_one(self, query, **_kwargs):
        return next((row for row in self.rows if _matches(row, query)), None)

    async def insert_one(self, document, **_kwargs):
        self.rows.append(dict(document))
        return SimpleNamespace(inserted_id=document["_id"])

    async def update_one(self, query, update, **_kwargs):
        row = await self.find_one(query)
        if row is None:
            return SimpleNamespace(matched_count=0, modified_count=0)
        row.update(update.get("$set", {}))
        for key, amount in update.get("$inc", {}).items():
            row[key] = row.get(key, 0) + amount
        for key in update.get("$unset", {}):
            row.pop(key, None)
        return SimpleNamespace(matched_count=1, modified_count=1)

    async def delete_one(self, query, **_kwargs):
        before = len(self.rows)
        self.rows = [row for row in self.rows if not _matches(row, query)]
        return SimpleNamespace(deleted_count=before - len(self.rows))

    async def delete_many(self, query, **_kwargs):
        before = len(self.rows)
        self.rows = [row for row in self.rows if not _matches(row, query)]
        return SimpleNamespace(deleted_count=before - len(self.rows))


class Bucket:
    def __init__(self):
        self.deleted = set()
        self.fail_once = False

    async def delete(self, file_id):
        if self.fail_once:
            self.fail_once = False
            raise OSError("injected blob deletion failure")
        if file_id in self.deleted:
            raise NoFile("already deleted")
        self.deleted.add(file_id)


class Database:
    def __init__(self):
        self.client = Client()
        self.collections = {
            "gridfs_upload_intents": Collection(),
            "projects": Collection([{
                "_id": "project", "organization_id": "org",
                "project_id": "project", "status": "active",
            }]),
            "workspace_snapshot_blobs.files": Collection(),
            "workspace_snapshot_blobs.chunks": Collection(),
            "execution_stdout.files": Collection(),
            "execution_stdout.chunks": Collection(),
            "execution_stderr.files": Collection(),
            "execution_stderr.chunks": Collection(),
        }

    def __getitem__(self, name):
        return self.collections[name]


@pytest.mark.asyncio
async def test_create_upload_intent_is_project_fenced_and_leased():
    database = Database()
    store = MongoGridFSUploadIntentStore(database)

    intent_id = await store.create(
        organization_id="org", project_id="project",
        resource_type="workspace_snapshot", bucket_names=("workspace_snapshot_blobs",),
    )

    intent = await database["gridfs_upload_intents"].find_one({"_id": intent_id})
    assert intent["state"] == "uploading"
    assert intent["lease_expires_at"] > intent["created_at"]
    assert database["projects"].rows[0]["lifecycle_write_seq"] == 1


@pytest.mark.asyncio
async def test_blob_id_rejects_expired_upload_lease():
    database = Database()
    store = MongoGridFSUploadIntentStore(database)
    intent_id = await store.create(
        organization_id="org", project_id="project",
        resource_type="workspace_snapshot", bucket_names=("workspace_snapshot_blobs",),
    )
    await database["gridfs_upload_intents"].update_one(
        {"_id": intent_id},
        {"$set": {"lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )

    with pytest.raises(UploadIntentLeaseLost):
        await store.blob_id(intent_id, "workspace_snapshot_blobs")


@pytest.mark.asyncio
async def test_upload_rejects_expired_lease_before_starting_stream():
    database = Database()
    store = MongoGridFSUploadIntentStore(database)
    intent_id = await store.create(
        organization_id="org", project_id="project",
        resource_type="workspace_snapshot", bucket_names=("workspace_snapshot_blobs",),
    )
    await database["gridfs_upload_intents"].update_one(
        {"_id": intent_id},
        {"$set": {"lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )
    upload_started = False

    async def upload():
        nonlocal upload_started
        upload_started = True

    with pytest.raises(UploadIntentLeaseLost):
        await store.upload_with_heartbeat(intent_id, upload)
    assert upload_started is False


@pytest.mark.asyncio
async def test_reconcile_expired_upload_deletes_only_its_gridfs_files():
    database = Database()
    store = MongoGridFSUploadIntentStore(database)
    stale = datetime.now(timezone.utc) - timedelta(hours=1)
    intent = {
        "_id": "stale-intent", "organization_id": "org", "project_id": "project",
        "bucket_names": ["workspace_snapshot_blobs"], "state": "uploading",
        "lease_expires_at": stale,
    }
    database["gridfs_upload_intents"].rows.append(intent)
    database["workspace_snapshot_blobs.files"].rows.extend([
        {"_id": "orphan", "metadata": {"upload_intent_id": "stale-intent"}},
        {"_id": "unrelated", "metadata": {"upload_intent_id": "other-intent"}},
    ])
    bucket = Bucket()

    assert await store.reconcile({"workspace_snapshot_blobs": bucket}) == 1
    assert bucket.deleted == {"orphan"}
    assert [row["_id"] for row in database["workspace_snapshot_blobs.files"].rows] == [
        "orphan", "unrelated",
    ]
    tombstone = await database["gridfs_upload_intents"].find_one({"_id": "stale-intent"})
    assert tombstone["state"] == "deleting"
    assert tombstone["cleanup_passes"] == 1
    # Re-sweeping is intentional: a paused uploader may resume after the first
    # pass and write new chunks under its preallocated file ID.
    assert await store.reconcile({"workspace_snapshot_blobs": bucket}) == 1
    assert tombstone["cleanup_passes"] == 2


@pytest.mark.asyncio
async def test_reconcile_committed_intent_never_deletes_committed_blob():
    database = Database()
    store = MongoGridFSUploadIntentStore(database)
    database["gridfs_upload_intents"].rows.append({
        "_id": "committed-intent", "state": "committed",
        "committed_at": datetime.now(timezone.utc) - timedelta(days=2),
        "bucket_names": ["execution_stdout"],
    })
    database["execution_stdout.files"].rows.append({
        "_id": "valid-output", "metadata": {"upload_intent_id": "committed-intent"},
    })
    bucket = Bucket()

    assert await store.reconcile({"execution_stdout": bucket}) == 1
    assert bucket.deleted == set()
    assert database["execution_stdout.files"].rows[0]["_id"] == "valid-output"
    assert await database["gridfs_upload_intents"].find_one({"_id": "committed-intent"}) is None


@pytest.mark.asyncio
async def test_reconcile_resumes_after_partial_bucket_cleanup_failure():
    database = Database()
    store = MongoGridFSUploadIntentStore(database)
    database["gridfs_upload_intents"].rows.append({
        "_id": "deleting-intent", "state": "deleting",
        "bucket_names": ["execution_stdout", "execution_stderr"],
    })
    database["execution_stdout.files"].rows.append({
        "_id": "stdout", "metadata": {"upload_intent_id": "deleting-intent"},
    })
    database["execution_stderr.files"].rows.append({
        "_id": "stderr", "metadata": {"upload_intent_id": "deleting-intent"},
    })
    stdout, stderr = Bucket(), Bucket()
    stderr.fail_once = True

    with pytest.raises(OSError, match="injected"):
        await store.reconcile({
            "execution_stdout": stdout, "execution_stderr": stderr,
        })
    assert (await database["gridfs_upload_intents"].find_one({
        "_id": "deleting-intent",
    }))["state"] == "deleting"
    assert await store.reconcile({
        "execution_stdout": stdout, "execution_stderr": stderr,
    }) == 1
    assert stdout.deleted == {"stdout"}
    assert stderr.deleted == {"stderr"}
    tombstone = await database["gridfs_upload_intents"].find_one({
        "_id": "deleting-intent",
    })
    assert tombstone["state"] == "deleting"
    assert tombstone["cleanup_passes"] == 1


@pytest.mark.asyncio
async def test_upload_heartbeat_renews_lease_while_upload_is_running(monkeypatch):
    database = Database()
    store = MongoGridFSUploadIntentStore(database)
    intent_id = await store.create(
        organization_id="org", project_id="project",
        resource_type="workspace_snapshot", bucket_names=("workspace_snapshot_blobs",),
    )
    monkeypatch.setattr(intents_module, "HEARTBEAT_SECONDS", 0.001)
    finished = asyncio.Event()

    async def upload():
        await asyncio.sleep(0.01)
        finished.set()
        return "blob-id"

    assert await store.upload_with_heartbeat(intent_id, upload) == "blob-id"
    assert finished.is_set()
    intent = await database["gridfs_upload_intents"].find_one({"_id": intent_id})
    assert intent["heartbeat_at"] >= intent["created_at"]


@pytest.mark.asyncio
async def test_upload_is_cancelled_when_lease_is_lost(monkeypatch):
    database = Database()
    store = MongoGridFSUploadIntentStore(database)
    intent_id = await store.create(
        organization_id="org", project_id="project",
        resource_type="workspace_snapshot", bucket_names=("workspace_snapshot_blobs",),
    )
    monkeypatch.setattr(intents_module, "HEARTBEAT_SECONDS", 0.001)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def upload():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = asyncio.create_task(store.upload_with_heartbeat(intent_id, upload))
    await started.wait()
    await database["gridfs_upload_intents"].update_one(
        {"_id": intent_id}, {"$set": {"state": "deleting"}},
    )
    with pytest.raises(UploadIntentLeaseLost):
        await task
    assert cancelled.is_set()

@pytest.mark.asyncio
async def test_reconcile_removes_incomplete_gridfs_chunks_without_files_document():
    database = Database()
    store = MongoGridFSUploadIntentStore(database)
    database["gridfs_upload_intents"].rows.append({
        "_id": "partial-intent", "state": "deleting",
        "bucket_names": ["workspace_snapshot_blobs"],
        "blob_ids": {"workspace_snapshot_blobs": "reserved-file-id"},
    })
    database["workspace_snapshot_blobs.chunks"].rows.extend([
        {"_id": "chunk-0", "files_id": "reserved-file-id", "n": 0},
        {"_id": "chunk-1", "files_id": "reserved-file-id", "n": 1},
        {"_id": "other-chunk", "files_id": "another-file", "n": 0},
    ])
    bucket = Bucket()

    assert await store.reconcile({"workspace_snapshot_blobs": bucket}) == 1
    assert database["workspace_snapshot_blobs.chunks"].rows == [
        {"_id": "other-chunk", "files_id": "another-file", "n": 0},
    ]
    assert database["workspace_snapshot_blobs.files"].rows == []
    tombstone = await database["gridfs_upload_intents"].find_one({
        "_id": "partial-intent",
    })
    assert tombstone["state"] == "deleting"
    assert tombstone["cleanup_passes"] == 1


@pytest.mark.asyncio
async def test_reconciliation_is_scoped_to_one_resource_worker():
    database = Database()
    store = MongoGridFSUploadIntentStore(database)
    stale = datetime.now(timezone.utc) - timedelta(hours=1)
    database["gridfs_upload_intents"].rows.extend([
        {
            "_id": "snapshot-intent", "resource_type": "workspace_snapshot",
            "state": "uploading", "lease_expires_at": stale,
            "bucket_names": ["workspace_snapshot_blobs"],
        },
        {
            "_id": "artifact-intent", "resource_type": "execution_artifact",
            "state": "uploading", "lease_expires_at": stale,
            "bucket_names": ["execution_stdout", "execution_stderr"],
        },
    ])
    database["workspace_snapshot_blobs.files"].rows.append({
        "_id": "snapshot-blob",
        "metadata": {"upload_intent_id": "snapshot-intent"},
    })
    database["execution_stdout.files"].rows.append({
        "_id": "stdout-blob",
        "metadata": {"upload_intent_id": "artifact-intent"},
    })
    snapshot_bucket = Bucket()

    assert await store.reconcile(
        {"workspace_snapshot_blobs": snapshot_bucket},
        resource_type="workspace_snapshot",
    ) == 1
    assert snapshot_bucket.deleted == {"snapshot-blob"}
    assert await database["gridfs_upload_intents"].find_one({
        "_id": "artifact-intent",
    }) is not None

@pytest.mark.asyncio
async def test_create_rejects_resource_type_bucket_mismatch_before_database_write():
    database = Database()
    store = MongoGridFSUploadIntentStore(database)

    with pytest.raises(ValueError, match="resource type and GridFS buckets"):
        await store.create(
            organization_id="org", project_id="project",
            resource_type="workspace_snapshot",
            bucket_names=("execution_stdout", "execution_stderr"),
        )
    assert database["gridfs_upload_intents"].rows == []

