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

    async def delete_one(self, query):
        def matches(row):
            for key, value in query.items():
                if isinstance(value, dict) and "$lte" in value:
                    if row.get(key) is None or row[key] > value["$lte"]:
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

    async def delete(self, blob_id):
        if blob_id in self.deleted:
            raise NoFile("already deleted")
        self.deleted.append(blob_id)


class Database:
    def __init__(self):
        self.collections = {
            "workspace_snapshots": Collection(),
            "execution_runs": Collection(),
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
         "expires_at": now - timedelta(seconds=1)},
        {"_id": "expired-snapshot", "blob_id": "blob-expired",
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
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    database["workspace_snapshots"].rows.append(expired)
    bucket.deleted.append("blob-retry")

    store = MongoWorkspaceSnapshotStore(database)
    deleted = await store.delete_expired(limit=10)

    assert deleted == 1
    assert database["workspace_snapshots"].rows == []
