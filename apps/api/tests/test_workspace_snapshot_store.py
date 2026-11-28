from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from gridfs.errors import NoFile

from odei_api.services import workspace_snapshot_store as snapshot_module
from odei_api.services.workspace_snapshot_store import MongoWorkspaceSnapshotStore


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, length):
        return self.rows[:length]


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

    @staticmethod
    def matches(row, query):
        for key, value in query.items():
            if key == "$or":
                if not any(Collection.matches(row, clause) for clause in value):
                    return False
            elif isinstance(value, dict) and "$lte" in value:
                if row.get(key) is None or row[key] > value["$lte"]:
                    return False
            elif isinstance(value, dict) and "$in" in value:
                if row.get(key) not in value["$in"]:
                    return False
            elif row.get(key) != value:
                return False
        return True

    def find(self, query):
        return Cursor([row for row in self.rows if self.matches(row, query)])

    async def find_one(self, query, **_kwargs):
        return next((row for row in self.rows if self.matches(row, query)), None)

    async def update_one(self, query, update, **_kwargs):
        row = await self.find_one(query)
        if row is None:
            return SimpleNamespace(matched_count=0, modified_count=0)
        row.update(update.get("$set", {}))
        for key, amount in update.get("$inc", {}).items():
            row[key] = row.get(key, 0) + amount
        return SimpleNamespace(matched_count=1, modified_count=1)

    async def delete_one(self, query, **_kwargs):
        def matches(row):
            for key, value in query.items():
                if isinstance(value, dict) and "$lte" in value:
                    if row.get(key) is None or row[key] > value["$lte"]:
                        return False
                elif isinstance(value, dict) and "$in" in value:
                    if row.get(key) not in value["$in"]:
                        return False
                elif row.get(key) != value:
                    return False
            return True

        before = len(self.rows)
        self.rows = [row for row in self.rows if not matches(row)]
        return SimpleNamespace(deleted_count=before - len(self.rows))


class Bucket:
    def __init__(self):
        self.deleted = []
        self.fail_next = False

    async def delete(self, blob_id):
        if self.fail_next:
            self.fail_next = False
            raise OSError("injected GridFS delete failure")
        if blob_id in self.deleted:
            raise NoFile("already deleted")
        self.deleted.append(blob_id)


class Database:
    def __init__(self):
        self.client = FakeClient()
        self.collections = {
            "workspace_snapshots": Collection(),
            "execution_runs": Collection(),
            "gridfs_upload_intents": Collection(),
            "projects": Collection([
                {"organization_id": "org", "project_id": "project", "status": "active"},
            ]),
        }

    def __getitem__(self, name):
        return self.collections[name]


@pytest.mark.asyncio
async def test_expired_snapshot_cleanup_skips_active_runs_and_deletes_inactive_blobs(monkeypatch):
    database = Database()
    bucket = Bucket()
    monkeypatch.setattr(
        snapshot_module, "AsyncGridFSBucket",
        lambda _database, bucket_name: bucket,
    )
    now = datetime.now(timezone.utc)
    database["workspace_snapshots"].rows.extend([
        {"_id": "active-snapshot", "blob_id": "blob-active",
         "organization_id": "org", "project_id": "project", "state": "available",
         "expires_at": now - timedelta(seconds=1)},
        {"_id": "expired-snapshot", "blob_id": "blob-expired",
         "organization_id": "org", "project_id": "project", "state": "available",
         "expires_at": now - timedelta(seconds=1)},
    ])
    database["execution_runs"].rows.append({
        "organization_id": "org", "project_id": "project",
        "snapshot_id": "active-snapshot", "status": "running",
    })

    store = MongoWorkspaceSnapshotStore(database)
    deleted = await store.delete_expired(limit=10)

    assert deleted == 1
    assert bucket.deleted == ["blob-expired"]
    assert [row["_id"] for row in database["workspace_snapshots"].rows] == [
        "active-snapshot",
    ]


@pytest.mark.asyncio
async def test_expired_snapshot_cleanup_is_retry_safe_after_blob_was_removed(monkeypatch):
    database = Database()
    bucket = Bucket()
    monkeypatch.setattr(
        snapshot_module, "AsyncGridFSBucket",
        lambda _database, bucket_name: bucket,
    )
    expired = {
        "_id": "snapshot-retry", "blob_id": "blob-retry",
        "organization_id": "org", "project_id": "project", "state": "available",
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    database["workspace_snapshots"].rows.append(expired)
    bucket.deleted.append("blob-retry")

    store = MongoWorkspaceSnapshotStore(database)
    deleted = await store.delete_expired(limit=10)

    assert deleted == 1
    assert database["workspace_snapshots"].rows == []


@pytest.mark.asyncio
async def test_expired_snapshot_cleanup_resumes_after_gridfs_delete_failure(monkeypatch):
    database = Database()
    bucket = Bucket()
    bucket.fail_next = True
    monkeypatch.setattr(
        snapshot_module, "AsyncGridFSBucket",
        lambda _database, bucket_name: bucket,
    )
    row = {
        "_id": "snapshot-fault", "blob_id": "blob-fault",
        "organization_id": "org", "project_id": "project", "state": "available",
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    database["workspace_snapshots"].rows.append(row)
    store = MongoWorkspaceSnapshotStore(database)

    with pytest.raises(OSError, match="injected GridFS"):
        await store.delete_expired(limit=10)
    assert database["workspace_snapshots"].rows[0]["state"] == "deleting"
    assert await store.delete_expired(limit=10) == 1
    assert database["workspace_snapshots"].rows == []
    assert bucket.deleted == ["blob-fault"]



@pytest.mark.asyncio
async def test_snapshot_retention_resumes_nonexpired_deletion_tombstone_after_restart(monkeypatch):
    database = Database()
    bucket = Bucket()
    monkeypatch.setattr(
        snapshot_module, "AsyncGridFSBucket",
        lambda _database, bucket_name: bucket,
    )
    database["workspace_snapshots"].rows.append({
        "_id": "manual-delete-retry", "blob_id": "blob-manual",
        "organization_id": "org", "project_id": "project", "state": "deleting",
        "expires_at": datetime.now(timezone.utc) + timedelta(days=3),
    })

    store = MongoWorkspaceSnapshotStore(database)
    assert await store.delete_expired(limit=10) == 1
    assert bucket.deleted == ["blob-manual"]
    assert database["workspace_snapshots"].rows == []



@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("archive", "message"),
    [
        (b"", "non-empty bytes"),
        ("not-bytes", "non-empty bytes"),
        (b"x" * (50 * 1024 * 1024 + 1), "50 MiB"),
    ],
)
async def test_snapshot_put_rejects_invalid_or_oversized_archive_before_gridfs_upload(
    monkeypatch, archive, message,
):
    database = Database()

    class RejectingBucket:
        async def upload_from_stream(self, *_args, **_kwargs):
            raise AssertionError("invalid archive must be rejected before GridFS upload")

    monkeypatch.setattr(
        snapshot_module, "AsyncGridFSBucket",
        lambda _database, bucket_name: RejectingBucket(),
    )
    store = MongoWorkspaceSnapshotStore(database)

    with pytest.raises(ValueError, match=message):
        await store.put(
            organization_id="org",
            project_id="project",
            task_id="task",
            owner_issuer="issuer",
            owner_subject="subject",
            archive=archive,
            sha256="0" * 64,
            file_count=0,
            total_bytes=0,
        )



@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"sha256": "not-a-digest"}, "SHA-256"),
        ({"sha256": "A" * 64}, "SHA-256"),
        ({"file_count": -1}, "file count"),
        ({"file_count": 10_001}, "file count"),
        ({"file_count": True}, "file count"),
        ({"total_bytes": -1}, "expanded byte"),
        ({"total_bytes": 512 * 1024 * 1024 + 1}, "expanded byte"),
        ({"total_bytes": True}, "expanded byte"),
        ({"owner_subject": " "}, "identifiers"),
    ],
)
async def test_snapshot_put_rejects_invalid_metadata_before_gridfs_upload(
    monkeypatch, overrides, message,
):
    database = Database()

    class RejectingBucket:
        async def upload_from_stream(self, *_args, **_kwargs):
            raise AssertionError("invalid metadata must be rejected before GridFS upload")

    monkeypatch.setattr(
        snapshot_module, "AsyncGridFSBucket",
        lambda _database, bucket_name: RejectingBucket(),
    )
    store = MongoWorkspaceSnapshotStore(database)
    arguments = {
        "organization_id": "org",
        "project_id": "project",
        "task_id": "task",
        "owner_issuer": "issuer",
        "owner_subject": "subject",
        "archive": b"zip-data",
        "sha256": "0" * 64,
        "file_count": 1,
        "total_bytes": 10,
    }
    arguments.update(overrides)

    with pytest.raises(ValueError, match=message):
        await store.put(**arguments)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"retention_days": True}, "retention"),
        ({"retention_days": 0}, "retention"),
        ({"retention_days": 31}, "retention"),
        ({"organization_id": " org"}, "organization_id"),
        ({"project_id": "project "}, "project_id"),
        ({"task_id": ""}, "task_id"),
        ({"owner_issuer": "issuer\\n"}, "owner_issuer"),
        ({"owner_subject": "x" * 129}, "owner_subject"),
    ],
)
async def test_snapshot_put_rejects_malformed_retention_and_identifiers_before_upload(
    monkeypatch, overrides, message,
):
    database = Database()

    class RejectingBucket:
        async def upload_from_stream(self, *_args, **_kwargs):
            raise AssertionError("invalid metadata must be rejected before GridFS upload")

    monkeypatch.setattr(
        snapshot_module, "AsyncGridFSBucket",
        lambda _database, bucket_name: RejectingBucket(),
    )
    store = MongoWorkspaceSnapshotStore(database)
    arguments = {
        "organization_id": "org",
        "project_id": "project",
        "task_id": "task",
        "owner_issuer": "issuer",
        "owner_subject": "subject",
        "archive": b"zip-data",
        "sha256": "0" * 64,
        "file_count": 1,
        "total_bytes": 10,
        "retention_days": 7,
    }
    arguments.update(overrides)

    with pytest.raises(ValueError, match=message):
        await store.put(**arguments)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [True, False, 0, 1001, 1.5, "10"])
async def test_snapshot_retention_rejects_invalid_batch_limits(limit):
    database = Database()
    store = MongoWorkspaceSnapshotStore(database)

    with pytest.raises(ValueError, match="batch limit"):
        await store.delete_expired(limit=limit)
