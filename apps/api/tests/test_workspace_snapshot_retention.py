from __future__ import annotations

import asyncio

import pytest

from odei_api.services.workspace_snapshot_retention import run_snapshot_retention


@pytest.mark.asyncio
async def test_snapshot_retention_runs_periodically_and_stops_cleanly():
    called = asyncio.Event()

    class Store:
        async def delete_expired(self, *, limit):
            assert limit == 25
            called.set()
            return 1

    worker = asyncio.create_task(
        run_snapshot_retention(Store(), interval_seconds=0.01, batch_size=25)
    )
    await asyncio.wait_for(called.wait(), timeout=1)
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker


@pytest.mark.asyncio
async def test_snapshot_retention_retries_after_a_failed_batch():
    retried = asyncio.Event()
    attempts = 0

    class Store:
        async def delete_expired(self, *, limit):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary storage failure")
            retried.set()
            return 0

    worker = asyncio.create_task(
        run_snapshot_retention(Store(), interval_seconds=0.01)
    )
    await asyncio.wait_for(retried.wait(), timeout=1)
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker
    assert attempts >= 2


@pytest.mark.asyncio
async def test_snapshot_retention_rejects_unbounded_or_invalid_schedule():
    class Store:
        async def delete_expired(self, *, limit):
            return 0

    with pytest.raises(ValueError):
        await run_snapshot_retention(Store(), interval_seconds=0)
    with pytest.raises(ValueError):
        await run_snapshot_retention(Store(), batch_size=1001)
