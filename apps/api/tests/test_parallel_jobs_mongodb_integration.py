"""Replica-set integration tests for NEXUS parallel job orchestration."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from odei_api.services.audit_store import MongoAuditEventStore
from odei_api.services.execution_runs import (
    ExecutionRun,
    ExecutionRunStatus,
    MongoExecutionRunStore,
)
from odei_api.services.nexus_parallel_execution import NexusParallelExecutionHandler
from odei_api.services.parallel_job_worker import ParallelJobWorker
from odei_api.services.parallel_jobs import MongoParallelJobStore


def _audit_event(organization_id: str, target_id: str, action: str) -> dict:
    return {
        "organization_id": organization_id,
        "actor_issuer": "https://identity.example.test/",
        "actor_subject": "owner",
        "action": action,
        "target_type": "nexus_execution_run",
        "target_id": target_id,
        "outcome": "success",
        "request_id": uuid4().hex,
        "metadata": {"source": "parallel-worker-integration"},
    }


@pytest.mark.asyncio
async def test_parallel_worker_orchestrates_real_execution_run_and_cancellation():
    uri = os.getenv("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI is not configured")
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000)
    database_name = f"odei_parallel_integration_{uuid4().hex}"
    database = client[database_name]
    audit = MongoAuditEventStore(database["audit_events"])
    runs = MongoExecutionRunStore(
        database["execution_runs"], database["execution_run_events"], client,
        audit_store=audit,
    )
    jobs = MongoParallelJobStore(
        database["nexus_parallel_jobs"], database["nexus_parallel_job_groups"],
        database["nexus_parallel_job_events"],
    )
    tasks, task_events = database["tasks"], database["task_events"]
    try:
        topology = await client.admin.command("hello")
        assert topology.get("setName") or topology.get("msg") == "isdbgrid"
        await audit.initialize()
        await runs.initialize()
        await jobs.initialize()
        await tasks.create_index([("_id", 1), ("organization_id", 1)], unique=True)
        await task_events.create_index(
            [("organization_id", 1), ("task_id", 1), ("version", 1)], unique=True,
        )

        organization_id = "org-integration"
        project_id = "project-integration"
        completed_run_id = uuid4().hex
        completed_task_id = uuid4().hex
        await tasks.insert_one({
            "_id": completed_task_id, "organization_id": organization_id,
            "project_id": project_id, "status": "executing", "version": 1,
        })
        completed_run = ExecutionRun(
            id=completed_run_id, organization_id=organization_id,
            project_id=project_id, task_id=completed_task_id,
            requester_issuer="https://identity.example.test/",
            requester_subject="owner", profile_id="python-tests",
            snapshot_sha256="a" * 64, arguments=(),
        )
        await runs.create(
            completed_run,
            audit_event=_audit_event(organization_id, completed_run_id, "nexus.execution.create"),
        )
        claim = await runs.claim_next(worker_id="execution-worker")
        assert claim is not None
        await runs.mark_running(
            organization_id=organization_id, run_id=completed_run_id,
            worker_id="execution-worker", lease_token=claim.lease_token,
        )
        await runs.mark_collecting(
            organization_id=organization_id, run_id=completed_run_id,
            worker_id="execution-worker", lease_token=claim.lease_token,
        )
        await runs.finish(
            organization_id=organization_id, run_id=completed_run_id,
            worker_id="execution-worker", lease_token=claim.lease_token,
            outcome=ExecutionRunStatus.COMPLETED,
            audit_event=_audit_event(organization_id, completed_run_id, "nexus.execution.complete"),
        )

        await jobs.create_group(
            organization_id=organization_id, project_id=project_id,
            group_id="completed-group",
            jobs=[{
                "job_id": "completed-job",
                "payload": {
                    "execution_run_id": completed_run_id,
                    "requested_by_issuer": "https://identity.example.test/",
                    "requested_by_subject": "owner",
                },
            }],
        )
        handler = NexusParallelExecutionHandler(
            runs=runs, audit=audit, tasks=tasks, task_events=task_events,
            poll_seconds=0.25,
        )
        worker = ParallelJobWorker(
            jobs, worker_id="parallel-worker", handler=handler,
            lease_seconds=30, heartbeat_seconds=5,
        )
        assert await worker.run_once() == "completed"
        completed_job = await jobs.get(
            organization_id=organization_id, project_id=project_id,
            job_id="completed-job",
        )
        assert completed_job is not None and completed_job.status == "completed"
        assert completed_job.checkpoint is not None
        assert completed_job.checkpoint["execution_run_status"] == "completed"

        cancelled_run_id = uuid4().hex
        cancelled_task_id = uuid4().hex
        await tasks.insert_one({
            "_id": cancelled_task_id, "organization_id": organization_id,
            "project_id": project_id, "status": "executing", "version": 1,
        })
        cancelled_run = ExecutionRun(
            id=cancelled_run_id, organization_id=organization_id,
            project_id=project_id, task_id=cancelled_task_id,
            requester_issuer="https://identity.example.test/",
            requester_subject="owner", profile_id="python-tests",
            snapshot_sha256="b" * 64, arguments=(),
        )
        await runs.create(
            cancelled_run,
            audit_event=_audit_event(organization_id, cancelled_run_id, "nexus.execution.create"),
        )
        await jobs.create_group(
            organization_id=organization_id, project_id=project_id,
            group_id="cancelled-group",
            jobs=[{
                "job_id": "cancelled-job",
                "payload": {
                    "execution_run_id": cancelled_run_id,
                    "requested_by_issuer": "https://identity.example.test/",
                    "requested_by_subject": "owner",
                },
            }],
        )
        await jobs.cancel_group(
            organization_id=organization_id, project_id=project_id,
            group_id="cancelled-group",
        )
        assert await worker.run_once() == "cancelled"
        cancelled_job = await jobs.get(
            organization_id=organization_id, project_id=project_id,
            job_id="cancelled-job",
        )
        cancelled_state = await runs.get(
            organization_id=organization_id, run_id=cancelled_run_id,
        )
        assert cancelled_job is not None and cancelled_job.status == "cancelled"
        assert cancelled_state is not None
        assert cancelled_state.status is ExecutionRunStatus.CANCELLED
    finally:
        await client.drop_database(database_name)
        await client.close()
