"""Standalone trusted NEXUS worker supervisor.

Run with: python -m odei_api.execution_worker
The worker must run on a dedicated host with a pinned OCI runtime and no browser-facing port.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from pymongo.errors import PyMongoError

from odei_api.config import get_settings
from odei_api.mongo_client import create_mongo_client
from odei_api.services.audit_store import MongoAuditEventStore
from odei_api.services.execution_artifacts import MongoExecutionArtifactStore
from odei_api.services.execution_profiles import load_execution_profiles
from odei_api.services.execution_runs import (
    ExecutionRun,
    ExecutionRunStatus,
    MongoExecutionRunStore,
)
from odei_api.services.execution_sandbox import ContainerSandbox
from odei_api.services.mad_telemetry import MongoWorkerHeartbeatStore
from odei_api.services.workspace_snapshot_store import MongoWorkspaceSnapshotStore
from odei_api.services.workspace_snapshots import WorkspaceSnapshotIngestor

logger = logging.getLogger("odei.execution.worker")


class ExecutionWorker:
    """Lease-supervised worker that verifies immutable snapshots before sandbox execution."""

    def __init__(self, *, worker_id, runs, snapshots, artifacts, registry, sandbox, workspace_root, tasks, task_events, heartbeats=None):
        self.worker_id = worker_id
        self.runs = runs
        self.snapshots = snapshots
        self.artifacts = artifacts
        self.registry = registry
        self.sandbox = sandbox
        self.workspace_root = Path(workspace_root).resolve(strict=True)
        self.tasks = tasks
        self.task_events = task_events
        self.heartbeats = heartbeats

    async def _publish_heartbeat(self, *, status: str, active_run_id: str | None = None) -> None:
        if self.heartbeats is None:
            return
        try:
            await self.heartbeats.heartbeat(
                worker_id=self.worker_id, status=status, active_run_id=active_run_id,
            )
        except (PyMongoError, OSError, RuntimeError, ValueError, TypeError) as exc:
            logger.warning("Worker heartbeat write failed (%s)", type(exc).__name__)

    def _audit(self, run: ExecutionRun, *, action: str, outcome: str, metadata=None):
        from uuid import uuid4
        return {
            "organization_id": run.organization_id,
            "actor_issuer": "https://odei-studio.internal",
            "actor_subject": self.worker_id,
            "action": action,
            "target_type": "nexus_execution_run",
            "target_id": run.id,
            "outcome": outcome,
            "request_id": uuid4().hex,
            "metadata": metadata or {},
        }

    async def run_once(self) -> bool:
        run = await self.runs.claim_next(worker_id=self.worker_id, lease_seconds=45)
        if run is None:
            return False
        lease_token = run.lease_token
        if not lease_token:
            logger.error("Claimed execution run has no lease token")
            return True
        workspace = None
        sandbox_task: asyncio.Task | None = None
        await self._publish_heartbeat(status="busy", active_run_id=run.id)
        try:
            profile = self.registry.get(run.profile_id)
            if not run.snapshot_id:
                raise RuntimeError("Execution run has no immutable snapshot reference")
            stored = await self.snapshots.get_archive_for_worker(snapshot_id=run.snapshot_id)
            if stored is None:
                raise RuntimeError("Workspace snapshot is missing or expired")
            metadata, archive = stored
            if (
                metadata.get("organization_id") != run.organization_id
                or metadata.get("project_id") != run.project_id
                or metadata.get("task_id") != run.task_id
                or metadata.get("sha256") != run.snapshot_sha256
            ):
                raise RuntimeError("Workspace snapshot tenant binding or digest metadata mismatch")
            record = WorkspaceSnapshotIngestor(self.workspace_root).ingest(archive)
            workspace = record.path
            if record.sha256 != run.snapshot_sha256:
                raise RuntimeError("Workspace snapshot content digest verification failed")
            await self.runs.mark_running(
                organization_id=run.organization_id, run_id=run.id,
                worker_id=self.worker_id, lease_token=lease_token,
            )
            sandbox_task = asyncio.create_task(self.sandbox.run(profile, workspace, arguments=()))
            while not sandbox_task.done():
                done, _ = await asyncio.wait({sandbox_task}, timeout=5)
                if done:
                    break
                await self.runs.heartbeat(
                    organization_id=run.organization_id, run_id=run.id,
                    worker_id=self.worker_id, lease_token=lease_token, lease_seconds=45,
                )
                await self._publish_heartbeat(status="busy", active_run_id=run.id)
                current = await self.runs.get(organization_id=run.organization_id, run_id=run.id)
                if current is None:
                    raise RuntimeError("Execution run disappeared while worker held its lease")
                if current.cancel_requested:
                    sandbox_task.cancel()
                    try:
                        await sandbox_task
                    except asyncio.CancelledError:
                        pass
                    await self.runs.finish(
                        organization_id=run.organization_id, run_id=run.id,
                        worker_id=self.worker_id, lease_token=lease_token,
                        outcome=ExecutionRunStatus.CANCELLED,
                        audit_event=self._audit(run, action="nexus.execution.cancelled",
                                                outcome="success", metadata={"phase": "sandbox"}),
                        tasks=self.tasks, task_events=self.task_events,
                    )
                    return True
            result = await sandbox_task
            await self.runs.mark_collecting(
                organization_id=run.organization_id, run_id=run.id,
                worker_id=self.worker_id, lease_token=lease_token,
            )
            await self.artifacts.put(
                organization_id=run.organization_id, project_id=run.project_id,
                task_id=run.task_id, run_id=run.id, exit_code=result.exit_code,
                duration_ms=result.duration_ms, timed_out=result.timed_out,
                stdout=result.stdout, stderr=result.stderr,
                stdout_truncated=result.stdout_truncated,
                stderr_truncated=result.stderr_truncated,
            )
            current = await self.runs.get(organization_id=run.organization_id, run_id=run.id)
            outcome = (
                ExecutionRunStatus.CANCELLED if current and current.cancel_requested
                else ExecutionRunStatus.COMPLETED
                if result.exit_code == 0 and not result.timed_out
                else ExecutionRunStatus.FAILED
            )
            await self.runs.finish(
                organization_id=run.organization_id, run_id=run.id,
                worker_id=self.worker_id, lease_token=lease_token, outcome=outcome,
                audit_event=self._audit(
                    run,
                    action="nexus.execution.complete" if outcome is ExecutionRunStatus.COMPLETED
                    else "nexus.execution.cancelled" if outcome is ExecutionRunStatus.CANCELLED
                    else "nexus.execution.failed",
                    outcome="success" if outcome is ExecutionRunStatus.COMPLETED else "failure",
                    metadata={"exit_code": result.exit_code, "timed_out": result.timed_out,
                              "duration_ms": result.duration_ms},
                ),
                tasks=self.tasks, task_events=self.task_events,
            )
            return True
        except asyncio.CancelledError:
            if sandbox_task is not None and not sandbox_task.done():
                sandbox_task.cancel()
                try:
                    await sandbox_task
                except asyncio.CancelledError:
                    pass
            raise
        except (PyMongoError, OSError, RuntimeError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
            logger.warning("Execution run %s failed (%s)", run.id, type(exc).__name__)
            try:
                current = await self.runs.get(organization_id=run.organization_id, run_id=run.id)
                if current is not None and current.worker_id == self.worker_id:
                    outcome = ExecutionRunStatus.CANCELLED if current.cancel_requested else ExecutionRunStatus.FAILED
                    await self.runs.finish(
                        organization_id=run.organization_id, run_id=run.id,
                        worker_id=self.worker_id, lease_token=lease_token, outcome=outcome,
                        audit_event=self._audit(run, action="nexus.execution.failed",
                                                outcome="failure", metadata={"error_type": type(exc).__name__}),
                        tasks=self.tasks, task_events=self.task_events,
                    )
            except (PyMongoError, OSError, RuntimeError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as finish_error:
                logger.warning("Could not finalize execution run %s (%s)", run.id, type(finish_error).__name__)
            return True
        finally:
            if workspace is not None:
                shutil.rmtree(workspace, ignore_errors=True)
            await self._publish_heartbeat(status="idle")

    async def serve(self, *, idle_seconds: float = 1.0) -> None:
        last_cleanup = 0.0
        last_heartbeat = 0.0
        try:
            await self._publish_heartbeat(status="idle")
            while True:
                now = time.monotonic()
                if now - last_heartbeat >= 15:
                    await self._publish_heartbeat(status="idle")
                    last_heartbeat = now
                await self.runs.expire_exhausted(actor_id=self.worker_id, limit=50,
                                                 tasks=self.tasks, task_events=self.task_events)
                if now - last_cleanup >= 60:
                    await self.snapshots.delete_expired(limit=50)
                    await self.artifacts.delete_expired(limit=50)
                    last_cleanup = now
                worked = await self.run_once()
                if not worked:
                    await asyncio.sleep(idle_seconds)
        finally:
            if self.heartbeats is not None:
                try:
                    await self.heartbeats.mark_stopped(worker_id=self.worker_id)
                except (PyMongoError, OSError, RuntimeError, ValueError, TypeError) as exc:
                    logger.warning("Worker shutdown heartbeat failed (%s)", type(exc).__name__)


async def _main() -> None:
    settings = get_settings()
    if not settings.execution_runtime_path or not settings.execution_workspace_root:
        raise RuntimeError("EXECUTION_RUNTIME_PATH and EXECUTION_WORKSPACE_ROOT are required")
    registry = load_execution_profiles(settings)
    if registry is None:
        raise RuntimeError("EXECUTION_PROFILES_JSON must configure at least one approved profile")
    workspace_root = Path(settings.execution_workspace_root)
    if workspace_root.is_symlink():
        raise RuntimeError("Execution workspace root must not be a symlink")
    workspace_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(workspace_root, 0o700)
    client, database_name = create_mongo_client(settings)
    database = client[database_name]
    audit = MongoAuditEventStore(database["audit_events"])
    await audit.initialize()
    runs = MongoExecutionRunStore(
        database["execution_runs"], database["execution_run_events"], client,
        audit_store=audit,
    )
    await runs.initialize()
    snapshots = MongoWorkspaceSnapshotStore(database)
    await snapshots.initialize()
    artifacts = MongoExecutionArtifactStore(database)
    await artifacts.initialize()
    heartbeats = MongoWorkerHeartbeatStore(database["execution_worker_heartbeats"])
    await heartbeats.initialize()
    sandbox = ContainerSandbox(
        runtime_path=settings.execution_runtime_path,
        workspace_root=workspace_root,
    )
    worker_id = settings.execution_worker_id or ("worker-" + uuid.uuid4().hex)
    worker = ExecutionWorker(
        worker_id=worker_id, runs=runs, snapshots=snapshots, artifacts=artifacts,
        registry=registry, sandbox=sandbox, workspace_root=workspace_root,
        tasks=database["tasks"], task_events=database["task_events"],
        heartbeats=heartbeats,
    )
    try:
        await worker.serve()
    finally:
        await client.close()


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(_main())


if __name__ == "__main__":
    main()
