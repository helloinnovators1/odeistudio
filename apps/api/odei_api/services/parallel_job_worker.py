"""Async lease-owning worker supervisor for durable NEXUS parallel jobs.

The supervisor is deliberately handler-injected: deployment code supplies an
isolated execution handler and worktree lifecycle. It never executes arbitrary
job payloads itself.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from odei_api.services.parallel_jobs import (
    MongoParallelJobStore,
    ParallelJob,
    ParallelJobConflict,
)

logger = logging.getLogger(__name__)

JobHandler = Callable[
    [ParallelJob, dict[str, Any], dict[str, Any] | None,
     Callable[[dict[str, Any]], Awaitable[None]], Callable[[], Awaitable[bool]]],
    Awaitable[dict[str, Any] | None],
]


class ParallelJobWorker:
    """Run one claimed job with heartbeat, verified checkpoint restore and cancellation."""

    def __init__(
        self,
        store: MongoParallelJobStore,
        *,
        worker_id: str,
        handler: JobHandler,
        lease_seconds: int = 60,
        heartbeat_seconds: int = 15,
    ) -> None:
        if not 5 <= lease_seconds <= 600:
            raise ValueError("lease_seconds must be between 5 and 600")
        if not 1 <= heartbeat_seconds < lease_seconds:
            raise ValueError("heartbeat_seconds must be positive and shorter than the lease")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self.store = store
        self.worker_id = worker_id
        self.handler = handler
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds

    async def run_once(self) -> str | None:
        job = await self.store.claim_next(
            worker_id=self.worker_id, lease_seconds=self.lease_seconds,
        )
        if job is None:
            return None

        # Read only the claimed row's payload. The lease token remains the
        # authority for every subsequent mutation.
        row = await self.store._jobs.find_one({
            "organization_id": job.organization_id,
            "project_id": job.project_id,
            "job_id": job.id,
            "worker_id": self.worker_id,
            "lease_token": job.lease_token,
            "status": "leased",
        })
        if row is None:
            raise ParallelJobConflict("claimed job disappeared before execution")
        payload = row.get("payload", {})
        if not isinstance(payload, dict):
            await self._finish(job, "failed")
            raise TypeError("persisted job payload is invalid")

        checkpoint = row.get("checkpoint")
        digest = row.get("checkpoint_sha256")
        if checkpoint is not None:
            if not isinstance(checkpoint, dict):
                await self._finish(job, "failed")
                raise ValueError("persisted checkpoint is invalid")
            canonical = json.dumps(
                checkpoint, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode()
            if len(canonical) > 256_000 or hashlib.sha256(canonical).hexdigest() != digest:
                await self._finish(job, "failed")
                raise ValueError("persisted checkpoint integrity verification failed")

        current_version = job.version
        stopped = asyncio.Event()
        heartbeat_task = asyncio.create_task(self._heartbeat(job, stopped))

        async def save_checkpoint(value: dict[str, Any]) -> None:
            nonlocal current_version
            if stopped.is_set():
                raise ParallelJobConflict("worker lost its lease")
            saved = await self.store.checkpoint(
                organization_id=job.organization_id, job_id=job.id,
                worker_id=self.worker_id, lease_token=job.lease_token,
                expected_version=current_version, checkpoint=value,
            )
            current_version = saved.version

        async def cancellation_requested() -> bool:
            if stopped.is_set():
                return True
            try:
                return await self.store.cancellation_requested(
                    organization_id=job.organization_id, job_id=job.id,
                    worker_id=self.worker_id, lease_token=job.lease_token,
                )
            except ParallelJobConflict:
                stopped.set()
                return True

        outcome = "failed"
        try:
            await self.handler(job, payload, checkpoint, save_checkpoint, cancellation_requested)
            outcome = "cancelled" if await cancellation_requested() else "completed"
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except Exception:
            logger.exception("NEXUS parallel job handler failed (job_id=%s)", job.id)
            outcome = "failed"
        finally:
            stopped.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            try:
                await self.store.finish(
                    organization_id=job.organization_id, job_id=job.id,
                    worker_id=self.worker_id, lease_token=job.lease_token,
                    expected_version=current_version, outcome=outcome,
                )
            except ParallelJobConflict:
                # The lease expired or was reclaimed. Never overwrite its new owner.
                logger.warning("NEXUS job completion lost lease ownership (job_id=%s)", job.id)
        return outcome

    async def _heartbeat(self, job: ParallelJob, stopped: asyncio.Event) -> None:
        while not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=self.heartbeat_seconds)
                return
            except TimeoutError:
                pass
            try:
                await self.store.heartbeat(
                    organization_id=job.organization_id, job_id=job.id,
                    worker_id=self.worker_id, lease_token=job.lease_token,
                    lease_seconds=self.lease_seconds,
                )
            except ParallelJobConflict:
                stopped.set()
                return

    async def _finish(self, job: ParallelJob, outcome: str) -> None:
        await self.store.finish(
            organization_id=job.organization_id, job_id=job.id,
            worker_id=self.worker_id, lease_token=job.lease_token,
            expected_version=job.version, outcome=outcome,
        )
