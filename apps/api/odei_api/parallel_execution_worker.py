"""Standalone NEXUS parallel-job worker process.

Run with: python -m odei_api.parallel_execution_worker
This process only coordinates previously approved NEXUS execution runs.
The isolated execution worker remains responsible for running the sandbox.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import uuid

from odei_api.config import get_settings
from odei_api.mongo_client import create_mongo_client
from odei_api.services.audit_store import MongoAuditEventStore
from odei_api.services.execution_runs import MongoExecutionRunStore
from odei_api.services.mad_telemetry import MongoWorkerHeartbeatStore
from odei_api.services.nexus_parallel_execution import NexusParallelExecutionHandler
from odei_api.services.parallel_job_worker import ParallelJobWorker
from odei_api.services.parallel_jobs import MongoParallelJobStore

logger = logging.getLogger("odei.parallel.worker")


def _create_worker_stores(database, client, audit):
    """Build project-fenced stores shared by the parallel worker."""
    projects = database["projects"]
    runs = MongoExecutionRunStore(
        database["execution_runs"], database["execution_run_events"], client,
        audit_store=audit, projects=projects,
    )
    jobs = MongoParallelJobStore(
        database["nexus_parallel_jobs"], database["nexus_parallel_job_groups"],
        database["nexus_parallel_job_events"], client, projects,
    )
    return runs, jobs


async def _main() -> None:
    settings = get_settings()
    if settings.mongodb_uri is None or not settings.mongodb_uri.get_secret_value():
        raise RuntimeError("MONGODB_URI is required for the parallel execution worker")
    client, database_name = create_mongo_client(settings)
    database = client[database_name]
    worker_id = os.getenv("PARALLEL_JOB_WORKER_ID") or f"parallel-{uuid.uuid4().hex}"
    if len(worker_id) > 128:
        raise ValueError("PARALLEL_JOB_WORKER_ID is too long")

    audit = MongoAuditEventStore(database["audit_events"])
    await audit.initialize()
    runs, jobs = _create_worker_stores(database, client, audit)
    await runs.initialize()
    await jobs.initialize()
    heartbeats = MongoWorkerHeartbeatStore(database["execution_worker_heartbeats"])
    await heartbeats.initialize()

    handler = NexusParallelExecutionHandler(
        runs=runs, audit=audit, tasks=database["tasks"],
        task_events=database["task_events"],
    )
    worker = ParallelJobWorker(
        jobs, worker_id=worker_id, handler=handler,
        lease_seconds=60, heartbeat_seconds=15, retry_base_seconds=5,
        heartbeats=heartbeats,
    )
    try:
        logger.info("NEXUS parallel worker started")
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, stop.set)
            except NotImplementedError:
                pass
        serving = asyncio.create_task(worker.serve())
        stopping = asyncio.create_task(stop.wait())
        done, _pending = await asyncio.wait(
            {serving, stopping}, return_when=asyncio.FIRST_COMPLETED,
        )
        if serving in done:
            await serving
        else:
            serving.cancel()
            await asyncio.gather(serving, return_exceptions=True)
        stopping.cancel()
        await asyncio.gather(stopping, return_exceptions=True)
    finally:
        await client.close()


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(_main())


if __name__ == "__main__":
    main()
