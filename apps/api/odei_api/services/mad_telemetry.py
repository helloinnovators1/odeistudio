"""Authoritative worker telemetry and MAD operational aggregates."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


_WORKER_STALE_SECONDS = 45
_QUEUE_DELAY_ALERT_SECONDS = 300
_RUN_STATES = ("queued", "leased", "running", "collecting", "completed", "failed", "cancelled", "expired")
_TASK_STATES = (
    "created", "context_gathering", "planning", "awaiting_approval", "approved",
    "executing", "validating", "repairing", "review_ready", "completed", "failed", "cancelled",
)


class MADTelemetryError(RuntimeError):
    """MAD telemetry persistence or lifecycle operation failed."""


class MongoMADTelemetryStore:
    """Persist worker heartbeats and compute dashboard values from authoritative collections."""

    def __init__(self, database: Any):
        self._workers = database["worker_heartbeats"]
        self._runs = database["execution_runs"]
        self._tasks = database["tasks"]
        self._alerts = database["mad_alerts"]
        self._audit = database["audit_events"]

    async def initialize(self) -> None:
        await self._workers.create_index([("last_seen_at", -1)])
        await self._alerts.create_index([("dedupe_key", 1)], unique=True)
        await self._alerts.create_index([("status", 1), ("severity", 1), ("updated_at", -1)])
        await self._alerts.create_index([("created_at", -1)])

    async def heartbeat(
        self, *, worker_id: str, status: str, active_run_id: str | None = None,
    ) -> None:
        if status not in {"idle", "running", "draining"}:
            raise ValueError("worker heartbeat status is invalid")
        if active_run_id is not None and (
            not isinstance(active_run_id, str) or not active_run_id
            or len(active_run_id) > 128
        ):
            raise ValueError("active execution run identifier is invalid")
        now = datetime.now(timezone.utc)
        await self._workers.update_one(
            {"_id": worker_id},
            {
                "$set": {
                    "status": status, "active_run_id": active_run_id,
                    "last_seen_at": now, "updated_at": now,
                },
                "$setOnInsert": {"worker_id": worker_id, "started_at": now},
            },
            upsert=True,
        )

    async def evaluate_alerts(self, *, limit: int = 100) -> int:
        if not 1 <= limit <= 500:
            raise ValueError("alert evaluation limit is invalid")
        now = datetime.now(timezone.utc)
        cursor = self._workers.find({}).sort("last_seen_at", -1).limit(limit)
        workers = await cursor.to_list(length=limit)
        created = 0
        for worker in workers:
            last_seen = worker.get("last_seen_at")
            if not isinstance(last_seen, datetime):
                continue
            age = (now - last_seen).total_seconds()
            if age <= _WORKER_STALE_SECONDS:
                continue
            dedupe_key = "worker-stale:" + worker["_id"]
            result = await self._alerts.update_one(
                {"dedupe_key": dedupe_key},
                {
                    "$setOnInsert": {
                        "_id": uuid4().hex, "dedupe_key": dedupe_key,
                        "type": "worker_stale", "severity": "high",
                        "status": "open", "affected_service": "execution-worker",
                        "affected_resource": worker["_id"],
                        "title": "Execution worker heartbeat is stale",
                        "description": "No worker heartbeat has been observed within the expected interval.",
                        "created_at": now,
                    },
                    "$set": {"last_seen_at": now, "updated_at": now, "age_seconds": int(age)},
                },
                upsert=True,
            )
            if result.upserted_id is not None:
                created += 1

        oldest = await self._runs.find_one(
            {"status": "queued"}, sort=[("created_at", 1)],
        )
        if oldest and isinstance(oldest.get("created_at"), datetime):
            age = (now - oldest["created_at"]).total_seconds()
            if age > _QUEUE_DELAY_ALERT_SECONDS:
                dedupe_key = "execution-queue-delay"
                result = await self._alerts.update_one(
                    {"dedupe_key": dedupe_key},
                    {
                        "$setOnInsert": {
                            "_id": uuid4().hex, "dedupe_key": dedupe_key,
                            "type": "execution_queue_delay", "severity": "medium",
                            "status": "open", "affected_service": "execution-queue",
                            "affected_resource": "queued-executions",
                            "title": "Execution queue delay exceeds threshold",
                            "description": "The oldest queued execution has exceeded the expected queue delay.",
                            "created_at": now,
                        },
                        "$set": {"last_seen_at": now, "updated_at": now, "age_seconds": int(age)},
                    },
                    upsert=True,
                )
                if result.upserted_id is not None:
                    created += 1
        return created

    async def overview(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        run_counts = {
            state: await self._runs.count_documents({"status": state})
            for state in _RUN_STATES
        }
        task_counts = {
            state: await self._tasks.count_documents({"status": state})
            for state in _TASK_STATES
        }
        worker_cursor = self._workers.find({}).sort("last_seen_at", -1).limit(100)
        worker_rows = await worker_cursor.to_list(length=100)
        workers = []
        stale_workers = 0
        for row in worker_rows:
            last_seen = row.get("last_seen_at")
            age = (
                max(0, int((now - last_seen).total_seconds()))
                if isinstance(last_seen, datetime) else None
            )
            is_stale = age is None or age > _WORKER_STALE_SECONDS
            stale_workers += int(is_stale)
            workers.append({
                "worker_id": row.get("worker_id", row.get("_id")),
                "status": "stale" if is_stale else row.get("status", "unknown"),
                "last_seen_at": last_seen.isoformat() if isinstance(last_seen, datetime) else None,
                "age_seconds": age,
                "active_run_id": row.get("active_run_id"),
            })
        oldest = await self._runs.find_one({"status": "queued"}, sort=[("created_at", 1)])
        queue_age = (
            max(0, int((now - oldest["created_at"]).total_seconds()))
            if oldest and isinstance(oldest.get("created_at"), datetime) else None
        )
        open_alerts = await self._alerts.count_documents({"status": {"$in": ["open", "acknowledged"]}})
        audit_since = now - timedelta(hours=24)
        audit_count = await self._audit.count_documents({"occurred_at": {"$gte": audit_since}})
        if not worker_rows:
            platform_status = "unknown"
        elif stale_workers or (queue_age is not None and queue_age > _QUEUE_DELAY_ALERT_SECONDS):
            platform_status = "degraded"
        else:
            platform_status = "healthy"
        latest_heartbeat = worker_rows[0].get("last_seen_at") if worker_rows else None
        return {
            "generated_at": now.isoformat(),
            "platform_status": platform_status,
            "sources": {
                "workers": {
                    "status": "unknown" if not worker_rows else "stale" if stale_workers else "fresh",
                    "last_seen_at": latest_heartbeat.isoformat() if isinstance(latest_heartbeat, datetime) else None,
                },
                "execution_runs": {"status": "available", "count": sum(run_counts.values())},
                "tasks": {"status": "available", "count": sum(task_counts.values())},
                "audit": {"status": "available", "window_hours": 24, "event_count": audit_count},
            },
            "execution": {
                "runs_by_status": run_counts,
                "oldest_queued_age_seconds": queue_age,
            },
            "tasks": {"tasks_by_status": task_counts},
            "workers": {
                "observed": len(worker_rows),
                "fresh": len(worker_rows) - stale_workers,
                "stale": stale_workers,
                "items": workers,
            },
            "alerts": {"open_or_acknowledged": open_alerts},
        }

    async def list_alerts(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if status not in {None, "open", "acknowledged", "resolved"} or not 1 <= limit <= 200:
            raise ValueError("alert query is invalid")
        query = {} if status is None else {"status": status}
        cursor = self._alerts.find(query).sort("updated_at", -1).limit(limit)
        rows = await cursor.to_list(length=limit)
        return [self._public_alert(row) for row in rows]

    async def update_alert(
        self, *, alert_id: str, action: str, actor_issuer: str, actor_subject: str,
    ) -> dict[str, Any] | None:
        if action not in {"acknowledge", "resolve"}:
            raise ValueError("alert action is invalid")
        now = datetime.now(timezone.utc)
        target = "acknowledged" if action == "acknowledge" else "resolved"
        result = await self._alerts.find_one_and_update(
            {"_id": alert_id, "status": {"$in": ["open", "acknowledged"]}},
            {"$set": {
                "status": target, "updated_at": now,
                "acknowledged_by": actor_subject if action == "acknowledge" else None,
                "resolved_by": actor_subject if action == "resolve" else None,
                "resolved_at": now if action == "resolve" else None,
            }},
            return_document=True,
        )
        return self._public_alert(result) if result else None

    @staticmethod
    def _public_alert(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "alert_id": row["_id"], "type": row["type"], "severity": row["severity"],
            "status": row["status"], "affected_service": row["affected_service"],
            "affected_resource": row["affected_resource"], "title": row["title"],
            "description": row["description"], "age_seconds": row.get("age_seconds"),
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
            "acknowledged_by": row.get("acknowledged_by"),
            "resolved_by": row.get("resolved_by"),
            "resolved_at": row["resolved_at"].isoformat() if row.get("resolved_at") else None,
        }
