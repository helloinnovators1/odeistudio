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

    def find(self, query):
        return Cursor([
            row for row in self.rows
            if all(row.get(key, None) <= value["$lte"]
                   if isinstance(value, dict) and "$lte" in value
                   else row.get(key) == value
                   for key, value in query.items())
        ])

    async def find_one(self, query):
        for row in self.rows:
            if all(
                row.get(key) in value["$in"]
                if isinstance(value, dict) and "$in" in value
                else row.get(key) == value
                for key, value in query.items()
            ):
                return row
        return None

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
