"""Lease-owning worker supervisor for durable NEXUS parallel jobs."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pymongo.errors import PyMongoError

from odei_api.services.parallel_jobs import (
    MongoParallelJobStore,
    ParallelJob,
    ParallelJobConflict,
)

logger = logging.getLogger(__name__)


class RetryableParallelJobError(RuntimeError):
    """A transient dependency failure that may be retried within the job budget."""


JobHandler = Callable[
    [
        ParallelJob,
        dict[str, Any],
        dict[str, Any] | None,
        Callable[[dict[str, Any]], Awaitable[None]],
        Callable[[], Awaitable[bool]],
    ],
    Awaitable[dict[str, Any] | None],
]


class ParallelJobWorker:
    """Run one job with heartbeat, checkpoint restore, cancellation and bounded retries."""

    def __init__(
        self,
        store: MongoParallelJobStore,
        *,
        worker_id: str,
        handler: JobHandler,
        lease_seconds: int = 60,
        heartbeat_seconds: int = 15,
        retry_base_seconds: int = 5,
        heartbeats: Any | None = None,
    ) -> None:
        if not 5 <= lease_seconds <= 600:
            raise ValueError("lease_seconds must be between 5 and 600")
        if not 1 <= heartbeat_seconds < lease_seconds:
            raise ValueError("heartbeat_seconds must be positive and shorter than the lease")
        if not 0 <= retry_base_seconds <= 300:
            raise ValueError("retry_base_seconds must be between 0 and 300")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self.store = store
        self.worker_id = worker_id
        self.handler = handler
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.retry_base_seconds = retry_base_seconds
        self.heartbeats = heartbeats

    async def run_once(self) -> str | None:
        job = await self.store.claim_next(
            worker_id=self.worker_id, lease_seconds=self.lease_seconds,
        )
        if job is None:
            return None
        lease_token = job.lease_token
        if not lease_token:
            logger.error("Claimed parallel job has no lease token (job_id=%s)", job.id)
            return "lease_invalid"

        claimed = await self.store.get_claimed(
            organization_id=job.organization_id, project_id=job.project_id,
            job_id=job.id, worker_id=self.worker_id, lease_token=lease_token,
        )
        if claimed is None:
            return "lease_lost"
        payload = claimed.get("payload", {})
        checkpoint = claimed.get("checkpoint")
        if not isinstance(payload, dict):
            await self._finish(job, lease_token, job.version, "failed")
            return "failed"

        current_version = int(claimed["version"])
        stopped = asyncio.Event()
        heartbeat_task = asyncio.create_task(self._heartbeat(job, lease_token, stopped))
        outcome = "failed"
        retry_delay: int | None = None
        shutdown_cancelled = False
        await self._publish_heartbeat("busy")

        async def save_checkpoint(value: dict[str, Any]) -> None:
            nonlocal current_version
            if stopped.is_set():
                raise ParallelJobConflict("worker lost its lease")
            saved = await self.store.checkpoint(
                organization_id=job.organization_id, job_id=job.id,
                worker_id=self.worker_id, lease_token=lease_token,
                expected_version=current_version, checkpoint=value,
            )
            current_version = saved.version

        async def cancellation_requested() -> bool:
            if stopped.is_set():
                raise ParallelJobConflict("worker no longer owns its lease")
            return await self.store.cancellation_requested(
                organization_id=job.organization_id, job_id=job.id,
                worker_id=self.worker_id, lease_token=lease_token,
            )

        try:
            result = await self.handler(
                job, payload, checkpoint, save_checkpoint, cancellation_requested,
            )
            cancelled = await cancellation_requested()
            outcome = (
                "cancelled"
                if cancelled or (isinstance(result, dict) and result.get("outcome") == "cancelled")
                else "completed"
            )
        except (RetryableParallelJobError, PyMongoError) as exc:
            retry_delay = min(
                900, self.retry_base_seconds * (2 ** max(0, job.attempt - 1)),
            )
            logger.warning(
                "Parallel job dependency failed transiently (job_id=%s, error=%s)",
                job.id, type(exc).__name__,
            )
        except asyncio.CancelledError:
            # Process shutdown is not a user cancellation. Release for another worker.
            retry_delay = 0
            shutdown_cancelled = True
        except ParallelJobConflict:
            outcome = "lease_lost"
        except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
            logger.warning(
                "Parallel job handler failed (job_id=%s, error=%s)",
                job.id, type(exc).__name__,
            )
            outcome = "failed"
        finally:
            stopped.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            await self._publish_heartbeat("idle")

        try:
            if retry_delay is not None:
                await self.store.retry(
                    organization_id=job.organization_id, job_id=job.id,
                    worker_id=self.worker_id, lease_token=lease_token,
                    expected_version=current_version, delay_seconds=retry_delay,
                )
                if shutdown_cancelled:
                    raise asyncio.CancelledError
                return "retry_scheduled"
            if outcome == "lease_lost":
                return outcome
            await self.store.finish(
                organization_id=job.organization_id, job_id=job.id,
                worker_id=self.worker_id, lease_token=lease_token,
                expected_version=current_version, outcome=outcome,
            )
        except ParallelJobConflict:
            logger.warning("Parallel job finalization lost lease ownership (job_id=%s)", job.id)
            return "lease_lost"
        return outcome

    async def _publish_heartbeat(self, status: str) -> None:
        if self.heartbeats is None:
            return
        try:
            await self.heartbeats.heartbeat(worker_id=self.worker_id, status=status)
        except Exception as exc:  # noqa: BLE001 - telemetry failures must not stop execution
            logger.warning("Parallel worker heartbeat failed (error=%s)", type(exc).__name__)

    async def _finish(
        self, job: ParallelJob, lease_token: str, expected_version: int, outcome: str,
    ) -> None:
        await self.store.finish(
            organization_id=job.organization_id, job_id=job.id,
            worker_id=self.worker_id, lease_token=lease_token,
            expected_version=expected_version, outcome=outcome,
        )

    async def _heartbeat(
        self, job: ParallelJob, lease_token: str, stopped: asyncio.Event,
    ) -> None:
        while not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=self.heartbeat_seconds)
                return
            except TimeoutError:
                pass
            try:
                await self.store.heartbeat(
                    organization_id=job.organization_id, job_id=job.id,
                    worker_id=self.worker_id, lease_token=lease_token,
                    lease_seconds=self.lease_seconds,
                )
            except (ParallelJobConflict, PyMongoError):
                stopped.set()
                return

    async def serve(self, *, idle_seconds: float = 1.0) -> None:
        if not 0.1 <= idle_seconds <= 30:
            raise ValueError("idle_seconds must be between 0.1 and 30")
        try:
            await self._publish_heartbeat("idle")
            while True:
                try:
                    result = await self.run_once()
                except (PyMongoError, OSError) as exc:
                    logger.warning(
                        "Parallel worker storage unavailable (error=%s)",
                        type(exc).__name__,
                    )
                    await asyncio.sleep(max(idle_seconds, 2.0))
                    continue
                if result is None:
                    await asyncio.sleep(idle_seconds)
        finally:
            if self.heartbeats is not None:
                try:
                    await self.heartbeats.mark_stopped(worker_id=self.worker_id)
                except Exception as exc:
                    logger.warning("Parallel worker shutdown heartbeat failed (error=%s)", type(exc).__name__)
