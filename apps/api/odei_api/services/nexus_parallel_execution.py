"""Bridge durable parallel jobs to the existing approved NEXUS execution queue."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from pymongo.errors import PyMongoError

from odei_api.services.execution_runs import (
    ExecutionRunConflict,
    ExecutionRunStatus,
    MongoExecutionRunStore,
)
from odei_api.services.parallel_job_worker import RetryableParallelJobError
from odei_api.services.parallel_jobs import ParallelJob


class NexusParallelExecutionHandler:
    """Wait for an already-authorized execution run and propagate job cancellation.

    Execution is performed by the existing isolated ExecutionWorker service.
    This handler never accepts shell commands, workspace paths, provider
    credentials or tool arguments from a parallel-job payload.
    """

    def __init__(
        self,
        *,
        runs: MongoExecutionRunStore,
        audit: Any,
        tasks: Any,
        task_events: Any,
        poll_seconds: float = 2.0,
    ) -> None:
        if not 0.25 <= poll_seconds <= 30:
            raise ValueError("poll_seconds must be between 0.25 and 30")
        self.runs = runs
        self.audit = audit
        self.tasks = tasks
        self.task_events = task_events
        self.poll_seconds = poll_seconds

    async def __call__(
        self,
        job: ParallelJob,
        payload: dict[str, Any],
        checkpoint: dict[str, Any] | None,
        save_checkpoint: Callable[[dict[str, Any]], Awaitable[None]],
        cancellation_requested: Callable[[], Awaitable[bool]],
    ) -> dict[str, Any]:
        if set(payload) != {
            "execution_run_id", "requested_by_issuer", "requested_by_subject",
        }:
            raise ValueError("parallel job is not a supported NEXUS execution reference")
        run_id = payload["execution_run_id"]
        issuer = payload["requested_by_issuer"]
        subject = payload["requested_by_subject"]
        if (
            not isinstance(run_id, str) or not run_id
            or not isinstance(issuer, str) or not issuer.startswith("https://")
            or not isinstance(subject, str) or not subject.strip()
        ):
            raise ValueError("parallel job execution reference is invalid")
        if checkpoint is not None and (
            not isinstance(checkpoint, dict)
            or checkpoint.get("execution_run_id") != run_id
        ):
            raise ValueError("checkpoint does not belong to the referenced execution run")

        previous = checkpoint or {}
        last_observed = (
            previous.get("execution_run_version"),
            previous.get("execution_run_status"),
        )
        while True:
            try:
                run = await self.runs.get(
                    organization_id=job.organization_id, run_id=run_id,
                )
            except PyMongoError as exc:
                raise RetryableParallelJobError("NEXUS execution state is temporarily unavailable") from exc
            if run is None:
                raise ValueError("referenced NEXUS execution run does not exist")
            if run.project_id != job.project_id or run.organization_id != job.organization_id:
                raise ValueError("referenced NEXUS execution run is outside this project")
            if run.requester_issuer != issuer or run.requester_subject != subject:
                raise ValueError("referenced NEXUS execution run belongs to another requester")

            cancelled = await cancellation_requested()
            if cancelled and run.status not in {
                ExecutionRunStatus.COMPLETED, ExecutionRunStatus.FAILED,
                ExecutionRunStatus.CANCELLED, ExecutionRunStatus.EXPIRED,
            } and not run.cancel_requested:
                try:
                    await self.runs.request_cancel(
                        organization_id=job.organization_id,
                        run_id=run_id,
                        actor_id="parallel-worker",
                        audit_event={
                            "organization_id": job.organization_id,
                            "actor_issuer": "https://odei-studio.internal",
                            "actor_subject": "parallel-worker",
                            "action": "nexus.execution.cancel",
                            "target_type": "nexus_execution_run",
                            "target_id": run_id,
                            "outcome": "success",
                            "request_id": uuid4().hex,
                            "metadata": {"source": "parallel_job_cancellation", "job_id": job.id},
                        },
                        tasks=self.tasks,
                        task_events=self.task_events,
                        task_audit_event={
                            "organization_id": job.organization_id,
                            "actor_issuer": "https://odei-studio.internal",
                            "actor_subject": "parallel-worker",
                            "action": "nexus.task.cancel",
                            "target_type": "nexus_task",
                            "target_id": run.task_id,
                            "outcome": "success",
                            "request_id": uuid4().hex,
                            "metadata": {"source": "parallel_job_cancellation", "job_id": job.id},
                        },
                    )
                except ExecutionRunConflict:
                    # A concurrent terminal transition wins; re-read authoritative state.
                    pass
                except PyMongoError as exc:
                    raise RetryableParallelJobError(
                        "NEXUS cancellation could not be persisted"
                    ) from exc
                continue

            observed = (run.version, run.status.value)
            if observed != last_observed:
                await save_checkpoint({
                    "execution_run_id": run_id,
                    "execution_run_version": run.version,
                    "execution_run_status": run.status.value,
                })
                last_observed = observed

            if cancelled and run.status in {
                ExecutionRunStatus.COMPLETED, ExecutionRunStatus.FAILED,
                ExecutionRunStatus.CANCELLED, ExecutionRunStatus.EXPIRED,
            }:
                return {"outcome": "cancelled", "execution_run_id": run_id}
            if run.status is ExecutionRunStatus.COMPLETED:
                return {"outcome": "completed", "execution_run_id": run_id}
            if run.status is ExecutionRunStatus.CANCELLED:
                return {"outcome": "cancelled", "execution_run_id": run_id}
            if run.status in {ExecutionRunStatus.FAILED, ExecutionRunStatus.EXPIRED}:
                raise ValueError("referenced NEXUS execution did not complete successfully")

            await asyncio.sleep(self.poll_seconds)
