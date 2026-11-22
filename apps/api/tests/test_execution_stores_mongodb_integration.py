"""Real MongoDB replica-set tests for execution runs and GridFS snapshots."""
from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient
from pymongo.errors import DuplicateKeyError

from odei_api.services.audit_store import MongoAuditEventStore
from odei_api.services.execution_artifacts import MongoExecutionArtifactStore
from odei_api.services.execution_runs import (
    ExecutionRun,
    ExecutionRunStatus,
    MongoExecutionRunStore,
)
from odei_api.services.workspace_snapshot_store import MongoWorkspaceSnapshotStore


def zip_bytes() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("README.md", b"approved workspace")
    return stream.getvalue()


@pytest.mark.asyncio
async def test_snapshot_gridfs_and_approved_task_run_are_tenant_scoped_and_durable():
    uri = os.getenv("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI is not configured")
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000)
    database_name = f"odei_execution_integration_{uuid4().hex}"
    database = client[database_name]
    audit = MongoAuditEventStore(database["audit_events"])
    snapshots = MongoWorkspaceSnapshotStore(database)
    artifacts = MongoExecutionArtifactStore(database)
    runs = MongoExecutionRunStore(
        database["execution_runs"], database["execution_run_events"], client,
        audit_store=audit,
    )
    task_id, run_id = uuid4().hex, uuid4().hex
    now = datetime.now(timezone.utc)
    archive = zip_bytes()
    digest = "a" * 64
    task = {
        "_id": task_id, "organization_id": "org-integration",
        "project_id": "project-integration", "owner_id": "owner",
        "goal": "execute approved code", "status": "approved",
        "plan": "run the approved test profile", "version": 4,
        "created_at": now, "updated_at": now,
    }
    try:
        topology = await client.admin.command("hello")
        assert topology.get("setName") or topology.get("msg") == "isdbgrid"
        await audit.initialize()
        await snapshots.initialize()
        await artifacts.initialize()
        await runs.initialize()
        await database["tasks"].insert_one(task)
        await database["task_events"].create_index(
            [("organization_id", 1), ("task_id", 1), ("version", 1)], unique=True
        )
        snapshot = await snapshots.put(
            organization_id="org-integration", project_id="project-integration",
            task_id=task_id, owner_issuer="https://identity.example.test/",
            owner_subject="owner", archive=archive, sha256=digest,
            file_count=1, total_bytes=len(b"approved workspace"),
        )
        assert snapshot["snapshot_id"]
        stored = await snapshots.get_archive_for_worker(snapshot_id=snapshot["snapshot_id"])
        assert stored is not None
        assert stored[1] == archive

        run = ExecutionRun(
            id=run_id, organization_id="org-integration",
            project_id="project-integration", task_id=task_id,
            requester_issuer="https://identity.example.test/",
            requester_subject="owner", profile_id="python-tests",
            snapshot_sha256=digest, snapshot_id=snapshot["snapshot_id"],
            arguments=(),
        )
        audit_event = {
            "organization_id": "org-integration",
            "actor_issuer": "https://identity.example.test/",
            "actor_subject": "owner", "action": "nexus.execution.create",
            "target_type": "nexus_execution_run", "target_id": run_id,
            "outcome": "success", "request_id": f"req-{uuid4().hex}",
            "metadata": {"task_id": task_id, "profile_id": "python-tests"},
        }
        created = await runs.create_approved_task_run(
            run, tasks=database["tasks"], task_events=database["task_events"],
            expected_task_version=4, audit_event=audit_event,
        )
        assert created.status is ExecutionRunStatus.QUEUED
        assert created.snapshot_id == snapshot["snapshot_id"]
        changed_task = await database["tasks"].find_one({"_id": task_id})
        assert changed_task["status"] == "executing"
        assert changed_task["version"] == 5
        assert await database["execution_runs"].count_documents({"task_id": task_id}) == 1
        assert await database["audit_events"].count_documents({"target_id": run_id}) == 1

        with pytest.raises(DuplicateKeyError):
            duplicate = ExecutionRun(
                id=uuid4().hex, organization_id="org-integration",
                project_id="project-integration", task_id=task_id,
                requester_issuer="https://identity.example.test/",
                requester_subject="owner", profile_id="python-tests",
                snapshot_sha256=digest, snapshot_id=snapshot["snapshot_id"],
                arguments=(),
            )
            await runs.create(duplicate)

        claimed = await runs.claim_next(worker_id="worker-integration", lease_seconds=30)
        assert claimed is not None and claimed.lease_token
        running = await runs.mark_running(
            organization_id=run.organization_id, run_id=run_id,
            worker_id="worker-integration", lease_token=claimed.lease_token,
        )
        collecting = await runs.mark_collecting(
            organization_id=run.organization_id, run_id=run_id,
            worker_id="worker-integration", lease_token=claimed.lease_token,
        )
        artifact = await artifacts.put(
            organization_id=run.organization_id, project_id=run.project_id,
            task_id=run.task_id, run_id=run.id, exit_code=0, duration_ms=123,
            timed_out=False, stdout="api_key=super_secret_value_123456", stderr="",
            stdout_truncated=False, stderr_truncated=False,
        )
        loaded_artifact = await artifacts.get_for_tenant(
            organization_id=run.organization_id, project_id=run.project_id,
            task_id=run.task_id, run_id=run.id,
        )
        assert artifact["run_id"] == run.id
        assert loaded_artifact is not None
        assert "super_secret_value_123456" not in loaded_artifact["stdout"]
        assert "[REDACTED]" in loaded_artifact["stdout"]
        completed = await runs.finish(
            organization_id=run.organization_id, run_id=run_id,
            worker_id="worker-integration", lease_token=claimed.lease_token,
            outcome=ExecutionRunStatus.COMPLETED,
            tasks=database["tasks"], task_events=database["task_events"],
        )
        assert running.status is ExecutionRunStatus.RUNNING
        assert collecting.status is ExecutionRunStatus.COLLECTING
        assert completed.status is ExecutionRunStatus.COMPLETED
        assert completed.lease_token is None
        finalized_task = await database["tasks"].find_one({"_id": task_id})
        assert finalized_task["status"] == "validating"
        assert finalized_task["version"] == 6

        task2_id, run2_id = uuid4().hex, uuid4().hex
        await database["tasks"].insert_one({
            "_id": task2_id, "organization_id": "org-integration",
            "project_id": "project-integration", "owner_id": "owner",
            "goal": "cancel queued run", "status": "executing",
            "plan": "already approved", "version": 5,
            "created_at": now, "updated_at": now,
        })
        snapshot2 = await snapshots.put(
            organization_id="org-integration", project_id="project-integration",
            task_id=task2_id, owner_issuer="https://identity.example.test/",
            owner_subject="owner", archive=archive, sha256=digest,
            file_count=1, total_bytes=len(b"approved workspace"),
        )
        run2 = ExecutionRun(
            id=run2_id, organization_id="org-integration",
            project_id="project-integration", task_id=task2_id,
            requester_issuer="https://identity.example.test/",
            requester_subject="owner", profile_id="python-tests",
            snapshot_sha256=digest, snapshot_id=snapshot2["snapshot_id"],
            arguments=(),
        )
        await runs.create(run2)
        cancelled = await runs.request_cancel(
            organization_id="org-integration", run_id=run2_id,
            actor_id="authenticated-user",
            audit_event=audit_event | {
                "action": "nexus.execution.cancel", "target_id": run2_id,
                "request_id": f"req-{uuid4().hex}",
            },
            tasks=database["tasks"], task_events=database["task_events"],
            task_audit_event=audit_event | {
                "action": "nexus.task.cancel", "target_type": "nexus_task",
                "target_id": task2_id, "request_id": f"req-{uuid4().hex}",
            },
        )
        assert cancelled.status is ExecutionRunStatus.CANCELLED
        cancelled_task = await database["tasks"].find_one({"_id": task2_id})
        assert cancelled_task["status"] == "cancelled"
        assert cancelled_task["version"] == 6

        task3_id, run3_id = uuid4().hex, uuid4().hex
        await database["tasks"].insert_one({
            "_id": task3_id, "organization_id": "org-integration",
            "project_id": "project-integration", "owner_id": "owner",
            "goal": "exhausted run", "status": "executing",
            "plan": "already approved", "version": 8,
            "created_at": now, "updated_at": now,
        })
        await database["execution_runs"].insert_one({
            "_id": run3_id, "organization_id": "org-integration",
            "project_id": "project-integration", "task_id": task3_id,
            "requester_issuer": "https://identity.example.test/",
            "requester_subject": "owner", "profile_id": "python-tests",
            "snapshot_sha256": digest, "snapshot_id": snapshot2["snapshot_id"],
            "arguments": [], "status": "queued", "version": 0,
            "attempts": 3, "max_attempts": 3, "worker_id": None,
            "lease_token": None, "lease_expires_at": None,
            "cancel_requested": False, "active_task_id": task3_id,
            "available_at": now, "created_at": now, "updated_at": now,
        })
        assert await runs.expire_exhausted(
            actor_id="worker-integration", tasks=database["tasks"],
            task_events=database["task_events"],
        ) == 1
        exhausted_run = await runs.get(organization_id="org-integration", run_id=run3_id)
        exhausted_task = await database["tasks"].find_one({"_id": task3_id})
        assert exhausted_run.status is ExecutionRunStatus.FAILED
        assert exhausted_task["status"] == "failed"
        assert exhausted_task["version"] == 9

        await database["workspace_snapshots"].update_one(
            {"_id": snapshot["snapshot_id"]},
            {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
        )
        assert await snapshots.delete_expired(limit=10) == 1
        assert await database["workspace_snapshots"].count_documents(
            {"_id": snapshot["snapshot_id"]}
        ) == 0
    finally:
        await client.drop_database(database_name)
        await client.close()
