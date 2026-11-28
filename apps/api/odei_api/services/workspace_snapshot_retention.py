"""Background retention worker for immutable workspace snapshots."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def run_snapshot_retention(
    snapshot_store: Any, *, interval_seconds: float = 300.0, batch_size: int = 100,
) -> None:
    """Repeatedly delete expired snapshots without interrupting API availability.

    MongoWorkspaceSnapshotStore.delete_expired is idempotent: it tolerates an
    already-missing GridFS blob and leaves snapshots referenced by active runs
    untouched. A failed batch is retried on the next interval.
    """
    if interval_seconds <= 0 or not 1 <= batch_size <= 1000:
        raise ValueError("snapshot retention worker bounds are invalid")
    while True:
        try:
            reconciled = await snapshot_store.reconcile_upload_intents(limit=batch_size)
            deleted = await snapshot_store.delete_expired(limit=batch_size)
            if reconciled:
                logger.info("GridFS snapshot upload reconciliation processed %d intent(s)", reconciled)
            if deleted:
                logger.info("Expired workspace snapshot retention removed %d snapshot(s)", deleted)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - retry transient storage and reconciliation failures
            logger.warning(
                "Expired workspace snapshot cleanup failed (%s); it will be retried",
                type(exc).__name__,
            )
        await asyncio.sleep(interval_seconds)


async def run_execution_artifact_retention(
    artifact_store: Any, *, interval_seconds: float = 300.0, batch_size: int = 100,
) -> None:
    """Repeatedly expire execution artifacts; failures remain retryable.

    Artifact deletion tombstones survive partial GridFS failures and are picked
    up by the next pass. Cancellation is always propagated during shutdown.
    """
    if interval_seconds <= 0 or not 1 <= batch_size <= 1000:
        raise ValueError("execution artifact retention worker bounds are invalid")
    while True:
        try:
            reconciled = await artifact_store.reconcile_upload_intents(limit=batch_size)
            deleted = await artifact_store.delete_expired(limit=batch_size)
            if reconciled:
                logger.info("GridFS execution upload reconciliation processed %d intent(s)", reconciled)
            if deleted:
                logger.info("Execution artifact retention removed %d artifact(s)", deleted)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Execution artifact cleanup failed (%s); it will be retried",
                type(exc).__name__,
            )
        await asyncio.sleep(interval_seconds)
