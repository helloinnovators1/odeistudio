from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from gridfs.errors import NoFile

from odei_api.services import execution_artifacts as artifact_module
from odei_api.services.execution_artifacts import MongoExecutionArtifactStore


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

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
        def matches(row):
            for key, value in query.items():
                if isinstance(value, dict) and "$in" in value:
                    if row.get(key) not in value["$in"]:
                        return False
                elif row.get(key) != value:
                    return False
            return True
        return next((row for row in self.rows if self.matches(row, query)), None)

    async def update_one(self, query, update, **_kwargs):
        row = await self.find_one({"_id": query["_id"]})
        if row is None or not self.matches(row, query):
            return SimpleNamespace(matched_count=0)
        row.update(update["$set"])
        return SimpleNamespace(matched_count=1)

    async def delete_one(self, query, **_kwargs):
        before = len(self.rows)
        self.rows = [row for row in self.rows if not all(row.get(k) == v for k, v in query.items())]
        return SimpleNamespace(deleted_count=before - len(self.rows))


class Bucket:
    def __init__(self):
        self.deleted = set()
        self.fail_blob = None

    async def delete(self, blob_id):
        if self.fail_blob == blob_id:
            self.fail_blob = None
            raise OSError("injected GridFS deletion failure")
        if blob_id in self.deleted:
            raise NoFile("already deleted")
        self.deleted.add(blob_id)


class Database:
    def __init__(self, artifact_rows):
        self.client = Client()
        self.collections = {
            "execution_artifacts": Collection(artifact_rows),
            "execution_runs": Collection(),
            "gridfs_upload_intents": Collection(),
            "projects": Collection(),
        }

    def __getitem__(self, name):
        return self.collections[name]


def artifact_row(*, state="available", run_id="run-1"):
    return {
        "_id": "artifact-1", "organization_id": "org-1",
        "project_id": "project-1", "task_id": "task-1", "run_id": run_id,
        "stdout_blob_id": "stdout-1", "stderr_blob_id": "stderr-1",
        "created_at": datetime.now(timezone.utc) - timedelta(days=60),
        "state": state,
    }


@pytest.mark.asyncio
async def test_artifact_retention_fences_project_and_skips_active_run(monkeypatch):
    database = Database([artifact_row()])
    buckets = {"execution_stdout": Bucket(), "execution_stderr": Bucket()}
    monkeypatch.setattr(
        artifact_module, "AsyncGridFSBucket",
        lambda _db, bucket_name: buckets[bucket_name],
    )
    fenced = []

    async def fence(_projects, **kwargs):
        fenced.append(kwargs)

    monkeypatch.setattr(artifact_module, "fence_project_write", fence)
    database["execution_runs"].rows.append({
        "organization_id": "org-1", "project_id": "project-1",
        "_id": "run-1", "status": "running",
    })
    store = MongoExecutionArtifactStore(database)

    assert await store.delete_expired() == 0
    assert fenced[0]["allow_deleting"] is True
    assert database["execution_artifacts"].rows[0]["state"] == "available"
    assert buckets["execution_stdout"].deleted == set()


@pytest.mark.asyncio
async def test_artifact_retention_resumes_after_partial_gridfs_failure(monkeypatch):
    database = Database([artifact_row()])
    buckets = {"execution_stdout": Bucket(), "execution_stderr": Bucket()}
    buckets["execution_stderr"].fail_blob = "stderr-1"
    monkeypatch.setattr(
        artifact_module, "AsyncGridFSBucket",
        lambda _db, bucket_name: buckets[bucket_name],
    )

    async def fence(_projects, **_kwargs):
        return None

    monkeypatch.setattr(artifact_module, "fence_project_write", fence)
    store = MongoExecutionArtifactStore(database)

    with pytest.raises(OSError, match="injected GridFS"):
        await store.delete_expired()
    assert database["execution_artifacts"].rows[0]["state"] == "deleting"
    assert buckets["execution_stdout"].deleted == {"stdout-1"}
    assert await store.delete_expired() == 1
    assert database["execution_artifacts"].rows == []
    assert buckets["execution_stderr"].deleted == {"stderr-1"}

@pytest.mark.asyncio
async def test_artifact_retention_resumes_nonexpired_deletion_tombstone(monkeypatch):
    row = artifact_row(state="deleting")
    row["created_at"] = datetime.now(timezone.utc)
    database = Database([row])
    buckets = {"execution_stdout": Bucket(), "execution_stderr": Bucket()}
    monkeypatch.setattr(
        artifact_module, "AsyncGridFSBucket",
        lambda _db, bucket_name: buckets[bucket_name],
    )

    async def fence(_projects, **_kwargs):
        return None

    monkeypatch.setattr(artifact_module, "fence_project_write", fence)
    store = MongoExecutionArtifactStore(database)

    assert await store.delete_expired() == 1
    assert database["execution_artifacts"].rows == []
    assert buckets["execution_stdout"].deleted == {"stdout-1"}
    assert buckets["execution_stderr"].deleted == {"stderr-1"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"organization_id": " org-1"}, "organization_id"),
        ({"project_id": ""}, "project_id"),
        ({"task_id": "task-1 "}, "task_id"),
        ({"run_id": "x" * 129}, "run_id"),
        ({"exit_code": True}, "exit code"),
        ({"exit_code": 2 ** 32}, "exit code"),
        ({"duration_ms": True}, "duration"),
        ({"duration_ms": -1}, "duration"),
        ({"timed_out": "false"}, "timed_out"),
        ({"stdout_truncated": 1}, "stdout_truncated"),
        ({"stderr_truncated": None}, "stderr_truncated"),
    ],
)
async def test_artifact_put_rejects_invalid_metadata_before_gridfs_upload(
    monkeypatch, overrides, message,
):
    database = Database([])
    class RejectingBucket:
        async def upload_from_stream(self, *_args, **_kwargs):
            raise AssertionError("invalid metadata must be rejected before GridFS upload")

    monkeypatch.setattr(
        artifact_module, "AsyncGridFSBucket",
        lambda _db, _bucket_name: RejectingBucket(),
    )
    store = MongoExecutionArtifactStore(database)
    arguments = {
        "organization_id": "org-1", "project_id": "project-1",
        "task_id": "task-1", "run_id": "run-1",
        "exit_code": 0, "duration_ms": 10, "timed_out": False,
        "stdout": "ok", "stderr": "", "stdout_truncated": False,
        "stderr_truncated": False,
    }
    arguments.update(overrides)

    with pytest.raises(ValueError, match=message):
        await store.put(**arguments)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("retention_days", "limit"),
    [(True, 100), (0, 100), (366, 100), (30, False), (30, 0), (30, 1001), (30, 1.5)],
)
async def test_artifact_retention_rejects_invalid_policy_bounds(retention_days, limit):
    database = Database([])
    store = MongoExecutionArtifactStore(database)

    with pytest.raises(ValueError, match="retention days and batch limit"):
        await store.delete_expired(retention_days=retention_days, limit=limit)


@pytest.mark.asyncio
async def test_artifact_read_hides_unknown_nonavailable_states():
    row = artifact_row(state="quarantined")
    database = Database([row])
    store = MongoExecutionArtifactStore(database)

    result = await store.get_for_tenant(
        organization_id="org-1", project_id="project-1",
        task_id="task-1", run_id="run-1",
    )

    assert result is None
