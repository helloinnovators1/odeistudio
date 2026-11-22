"""Low-cardinality worker heartbeat and MAD execution telemetry."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ASCENDING

_WORKER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WORKER_STALE_SECONDS = 60
_HEARTBEAT_RETENTION_SECONDS = 30 * 24 * 60 * 60


class MongoWorkerHeartbeatStore:
    """Stores low-cardinality process liveness; never stores hostnames or secrets."""

    def __init__(self, collection: Any):
        self.collection = collection

    async def initialize(self) -> None:
        await self.collection.create_index(
            [("last_seen_at", ASCENDING)],
            expireAfterSeconds=_HEARTBEAT_RETENTION_SECONDS,
        )
        await self.collection.create_index([("status", ASCENDING), ("last_seen_at", ASCENDING)])

    async def heartbeat(
        self,
        *,
        worker_id: str,
        status: str,
        active_run_id: str | None = None,
    ) -> datetime:
        if not isinstance(worker_id, str) or not _WORKER_ID.fullmatch(worker_id):
            raise ValueError("worker_id is invalid")
        if status not in {"idle", "busy", "stopping"}:
            raise ValueError("worker status is invalid")
        if active_run_id is not None and (
            not isinstance(active_run_id, str) or not re.fullmatch(r"[A-Fa-f0-9-]{1,64}", active_run_id)
        ):
            raise ValueError("active_run_id is invalid")
        now = datetime.now(timezone.utc)
        await self.collection.update_one(
            {"_id": worker_id},
            {
                "$set": {
                    "worker_id": worker_id,
                    "status": status,
                    "active_run_id": active_run_id,
                    "last_seen_at": now,
                    "protocol_version": 1,
                },
                "$setOnInsert": {"started_at": now},
            },
            upsert=True,
        )
        return now

    async def mark_stopped(self, *, worker_id: str) -> datetime:
        return await self.heartbeat(worker_id=worker_id, status="stopping")


def _utc_iso(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


async def collect_mad_execution_metrics(database: Any) -> dict[str, Any]:
    """Return platform-level execution counters without tenant or artifact content."""
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(seconds=_WORKER_STALE_SECONDS)
    day_ago = now - timedelta(hours=24)
    runs = database["execution_runs"]
    workers = database["execution_worker_heartbeats"]

    (
        queued, leased, running, collecting, completed_24h, failed_24h,
        cancelled_24h, worker_total, worker_fresh, worker_offline,
    ) = (
        await runs.count_documents({"status": "queued"}),
        await runs.count_documents({"status": "leased"}),
        await runs.count_documents({"status": "running"}),
        await runs.count_documents({"status": "collecting"}),
        await runs.count_documents({"status": "completed", "updated_at": {"$gte": day_ago}}),
        await runs.count_documents({"status": "failed", "updated_at": {"$gte": day_ago}}),
        await runs.count_documents({"status": "cancelled", "updated_at": {"$gte": day_ago}}),
        await workers.count_documents({}),
        await workers.count_documents({
            "status": {"$in": ["idle", "busy"]},
            "last_seen_at": {"$gte": stale_before},
        }),
        await workers.count_documents({"status": "stopping"}),
    )
    oldest = await runs.find_one({"status": "queued"}, sort=[("created_at", ASCENDING)])
    active_runs = leased + running + collecting
    worker_stopping = min(worker_total - worker_fresh, worker_offline)
    worker_stale = max(0, worker_total - worker_fresh - worker_stopping)
    worker_state = (
        "unknown" if worker_total == 0
        else "healthy" if worker_fresh and not worker_stale and not worker_stopping
        else "degraded"
    )
    queue_state = "degraded" if (queued or active_runs) and worker_fresh == 0 else "healthy"
    return {
        "observed_at": now.isoformat(),
        "freshness": "fresh",
        "worker_stale_after_seconds": _WORKER_STALE_SECONDS,
        "workers": {
            "state": worker_state,
            "known": worker_total,
            "fresh": worker_fresh,
            "stale": worker_stale,
            "stopping": worker_stopping,
        },
        "queue": {
            "state": queue_state,
            "queued": queued,
            "active": active_runs,
            "oldest_queued_at": _utc_iso(oldest.get("created_at")) if oldest else None,
        },
        "executions_24h": {
            "completed": completed_24h,
            "failed": failed_24h,
            "cancelled": cancelled_24h,
        },
    }


# Conservative defaults; tune against real staging workload before production paging.
_QUEUE_BACKLOG_ALERT_SECONDS = 15 * 60
_FAILED_EXECUTIONS_ALERT_COUNT = 5


def evaluate_mad_alerts(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive deterministic operational alerts from aggregate telemetry only."""
    workers = metrics.get("workers", {})
    queue = metrics.get("queue", {})
    executions = metrics.get("executions_24h", {})
    observed_at = metrics.get("observed_at")
    alerts: list[dict[str, Any]] = []
    queued = int(queue.get("queued", 0) or 0)
    active = int(queue.get("active", 0) or 0)
    fresh_workers = int(workers.get("fresh", 0) or 0)
    if (queued or active) and fresh_workers == 0:
        alerts.append({
            "id": "mad.execution.worker_pool_unavailable",
            "deduplication_key": "execution-worker-pool-unavailable",
            "severity": "critical", "status": "firing",
            "summary": "Execution work exists but no worker heartbeat is fresh.",
            "observed_at": observed_at,
            "runbook": "docs/runbooks/MAD_EXECUTION_WORKERS.md",
        })
    elif workers.get("state") == "degraded":
        alerts.append({
            "id": "mad.execution.worker_pool_degraded",
            "deduplication_key": "execution-worker-pool-degraded",
            "severity": "warning", "status": "firing",
            "summary": "One or more execution workers are stale or stopping.",
            "observed_at": observed_at,
            "runbook": "docs/runbooks/MAD_EXECUTION_WORKERS.md",
        })
    oldest = queue.get("oldest_queued_at")
    if queued and isinstance(oldest, str) and isinstance(observed_at, str):
        try:
            oldest_at = datetime.fromisoformat(oldest.replace("Z", "+00:00"))
            observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            if oldest_at.tzinfo is None:
                oldest_at = oldest_at.replace(tzinfo=timezone.utc)
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            age_seconds = max(0, int((observed - oldest_at).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            age_seconds = 0
        if age_seconds >= _QUEUE_BACKLOG_ALERT_SECONDS:
            alerts.append({
                "id": "mad.execution.queue_backlog",
                "deduplication_key": "execution-queue-backlog",
                "severity": "warning", "status": "firing",
                "summary": "The oldest queued execution has exceeded the 15-minute baseline.",
                "observed_at": observed_at, "age_seconds": age_seconds,
                "runbook": "docs/runbooks/MAD_EXECUTION_WORKERS.md",
            })
    failed = int(executions.get("failed", 0) or 0)
    if failed >= _FAILED_EXECUTIONS_ALERT_COUNT:
        alerts.append({
            "id": "mad.execution.failure_burst",
            "deduplication_key": "execution-failure-burst",
            "severity": "warning", "status": "firing",
            "summary": "At least five executions failed in the rolling 24-hour window.",
            "observed_at": observed_at, "failed_24h": failed,
            "runbook": "docs/runbooks/MAD_EXECUTION_WORKERS.md",
        })
    return alerts
