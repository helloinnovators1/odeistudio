"""Durable, tenant-scoped NEXUS execution-run lifecycle and worker leasing."""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_PROFILE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_MAX_ARGS = 32
_MAX_ARG_CHARS = 1024

class ExecutionRunError(RuntimeError):
    """Base error for execution-run lifecycle failures."""
class ExecutionRunConflict(ExecutionRunError):
    """A version, state or lease precondition no longer matches."""
class ExecutionRunNotFound(ExecutionRunError):
    """A tenant-scoped execution run does not exist."""

class ExecutionRunStatus(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    COLLECTING = "collecting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

_TERMINAL = {ExecutionRunStatus.COMPLETED, ExecutionRunStatus.FAILED,
             ExecutionRunStatus.CANCELLED, ExecutionRunStatus.EXPIRED}
_TRANSITIONS = {
    ExecutionRunStatus.QUEUED: {ExecutionRunStatus.LEASED, ExecutionRunStatus.CANCELLED, ExecutionRunStatus.EXPIRED},
    ExecutionRunStatus.LEASED: {ExecutionRunStatus.RUNNING, ExecutionRunStatus.QUEUED, ExecutionRunStatus.CANCELLED, ExecutionRunStatus.FAILED},
    ExecutionRunStatus.RUNNING: {ExecutionRunStatus.COLLECTING, ExecutionRunStatus.CANCELLED, ExecutionRunStatus.FAILED},
    ExecutionRunStatus.COLLECTING: {ExecutionRunStatus.COMPLETED, ExecutionRunStatus.CANCELLED, ExecutionRunStatus.FAILED},
    ExecutionRunStatus.COMPLETED: set(), ExecutionRunStatus.FAILED: set(),
    ExecutionRunStatus.CANCELLED: set(), ExecutionRunStatus.EXPIRED: set(),
}

def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} is invalid")
    return value

def validate_execution_request(*, profile_id: str, snapshot_sha256: str,
                                arguments: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Validate bounded identifiers and argv; never accept shell command strings."""
    if not isinstance(profile_id, str) or not _PROFILE.fullmatch(profile_id):
        raise ValueError("profile_id is invalid")
    if not isinstance(snapshot_sha256, str) or not _SHA256.fullmatch(snapshot_sha256):
        raise ValueError("snapshot_sha256 must be a lowercase SHA-256 digest")
    if isinstance(arguments, (str, bytes)) or not isinstance(arguments, (tuple, list)):
        raise ValueError("arguments must be a bounded argument vector")
    if len(arguments) > _MAX_ARGS:
        raise ValueError("too many execution arguments")
    result = tuple(arguments)
    if any(not isinstance(arg, str) or not arg or len(arg) > _MAX_ARG_CHARS
           or any(ord(char) < 32 or ord(char) == 127 for char in arg) for arg in result):
        raise ValueError("execution argument is invalid")
    return result

@dataclasses.dataclass(frozen=True)
class ExecutionRun:
    id: str
    organization_id: str
    project_id: str
    task_id: str
    requester_issuer: str
    requester_subject: str
    profile_id: str
    snapshot_sha256: str
    arguments: tuple[str, ...]
    status: ExecutionRunStatus = ExecutionRunStatus.QUEUED
    version: int = 0
    attempts: int = 0
    max_attempts: int = 3
    worker_id: str | None = None
    lease_token: str | None = dataclasses.field(default=None, repr=False, compare=False)
    lease_expires_at: datetime | None = None
    cancel_requested: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("id", "organization_id", "project_id", "task_id"):
            _identifier(getattr(self, name), name)
        if not isinstance(self.requester_issuer, str) or not self.requester_issuer.startswith("https://"):
            raise ValueError("requester_issuer must be an HTTPS issuer")
        if (not isinstance(self.requester_subject, str) or not self.requester_subject.strip()
                or len(self.requester_subject) > 512
                or any(ord(char) < 32 or ord(char) == 127 for char in self.requester_subject)):
            raise ValueError("requester_subject is invalid")
        if not 1 <= self.max_attempts <= 10 or self.attempts < 0 or self.version < 0:
            raise ValueError("execution run counters are invalid")
        validate_execution_request(profile_id=self.profile_id,
                                   snapshot_sha256=self.snapshot_sha256,
                                   arguments=self.arguments)

def _event(run: ExecutionRun, *, event_type: str, version: int,
           actor_id: str, **fields: Any) -> dict[str, Any]:
    return {"event_id": str(uuid4()), "organization_id": run.organization_id,
            "project_id": run.project_id, "task_id": run.task_id, "run_id": run.id,
            "actor_id": actor_id, "type": event_type, "version": version,
            "occurred_at": datetime.now(timezone.utc), **fields}

class MongoExecutionRunStore:
    """MongoDB run queue with transactional events and expiring worker leases."""
    def __init__(self, runs: Any, events: Any, client: Any, audit_store: Any | None = None):
        self._runs, self._events, self._client, self._audit = runs, events, client, audit_store

    async def initialize(self) -> None:
        await self._runs.create_index([("organization_id", 1), ("_id", 1)], unique=True)
        await self._runs.create_index([("status", 1), ("created_at", 1), ("available_at", 1)])
        await self._runs.create_index([("status", 1), ("lease_expires_at", 1)])
        await self._runs.create_index([("organization_id", 1), ("project_id", 1), ("created_at", -1)])
        await self._events.create_index([("organization_id", 1), ("run_id", 1), ("version", 1)], unique=True)

    async def _audit_in_transaction(self, event: Mapping[str, Any] | None, session: Any) -> None:
        if event is None:
            return
        if self._audit is None:
            raise RuntimeError("Audit storage is required for execution-run mutations")
        await self._audit.append(**dict(event), session=session)

    @staticmethod
    def _document(run: ExecutionRun, now: datetime) -> dict[str, Any]:
        return {"_id": run.id, "organization_id": run.organization_id,
                "project_id": run.project_id, "task_id": run.task_id,
                "requester_issuer": run.requester_issuer, "requester_subject": run.requester_subject,
                "profile_id": run.profile_id, "snapshot_sha256": run.snapshot_sha256,
                "arguments": list(run.arguments), "status": run.status.value,
                "version": run.version, "attempts": run.attempts, "max_attempts": run.max_attempts,
                "worker_id": None, "lease_token": None, "lease_expires_at": None,
                "cancel_requested": False, "available_at": now, "created_at": now, "updated_at": now}

    async def create(self, run: ExecutionRun, *, audit_event: Mapping[str, Any] | None = None) -> ExecutionRun:
        if run.status is not ExecutionRunStatus.QUEUED or run.version != 0 or run.attempts != 0:
            raise ValueError("new execution runs must begin queued at version and attempt zero")
        now = datetime.now(timezone.utc)
        document = self._document(run, now)
        async with self._client.start_session() as session, await session.start_transaction():
            await self._runs.insert_one(document, session=session)
            await self._events.insert_one(_event(run, event_type="execution.queued", version=0,
                                                  actor_id=run.requester_subject), session=session)
            await self._audit_in_transaction(audit_event, session)
        return self._from_document(document)

    async def get(self, *, organization_id: str, run_id: str) -> ExecutionRun | None:
        _identifier(organization_id, "organization_id")
        _identifier(run_id, "run_id")
        row = await self._runs.find_one({"organization_id": organization_id, "_id": run_id})
        return self._from_document(row) if row else None

    async def claim_next(self, *, worker_id: str, lease_seconds: int = 30) -> ExecutionRun | None:
        """Atomically lease the oldest queued run or reclaim an expired worker lease."""
        _identifier(worker_id, "worker_id")
        if not 5 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be between 5 and 300")
        now, token = datetime.now(timezone.utc), uuid4().hex
        async with self._client.start_session() as session, await session.start_transaction():
            row = await self._runs.find_one_and_update(
                {"$or": [
                    {"status": ExecutionRunStatus.QUEUED.value, "available_at": {"$lte": now},
                     "$expr": {"$lt": ["$attempts", "$max_attempts"]}},
                    {"status": {"$in": [ExecutionRunStatus.LEASED.value, ExecutionRunStatus.RUNNING.value, ExecutionRunStatus.COLLECTING.value]},
                     "lease_expires_at": {"$lte": now},
                     "$expr": {"$lt": ["$attempts", "$max_attempts"]}},
                ]},
                {"$set": {"status": ExecutionRunStatus.LEASED.value, "worker_id": worker_id,
                          "lease_token": token, "lease_expires_at": now + timedelta(seconds=lease_seconds),
                          "updated_at": now}, "$inc": {"version": 1, "attempts": 1}},
                sort=[("created_at", 1)], return_document=ReturnDocument.AFTER, session=session)
            if row is None:
                return None
            claimed = self._from_document(row)
            await self._events.insert_one(_event(claimed, event_type="execution.leased",
                version=claimed.version, actor_id=worker_id, attempt=claimed.attempts), session=session)
        return claimed

    async def heartbeat(self, *, organization_id: str, run_id: str, worker_id: str,
                        lease_token: str, lease_seconds: int = 30) -> datetime:
        now = datetime.now(timezone.utc)
        if not 5 <= lease_seconds <= 300 or not re.fullmatch(r"[a-f0-9]{32}", lease_token or ""):
            raise ValueError("lease heartbeat parameters are invalid")
        expiry = now + timedelta(seconds=lease_seconds)
        result = await self._runs.update_one(
            {"_id": run_id, "organization_id": organization_id, "worker_id": worker_id,
             "lease_token": lease_token, "status": {"$in": ["leased", "running", "collecting"]},
             "lease_expires_at": {"$gt": now}},
            {"$set": {"lease_expires_at": expiry, "updated_at": now}})
        if result.modified_count != 1:
            raise ExecutionRunConflict("worker lease is missing, expired or no longer owned")
        return expiry

    async def mark_running(self, *, organization_id: str, run_id: str,
                           worker_id: str, lease_token: str) -> ExecutionRun:
        return await self._worker_transition(organization_id=organization_id, run_id=run_id,
            worker_id=worker_id, lease_token=lease_token, next_status=ExecutionRunStatus.RUNNING)

    async def mark_collecting(self, *, organization_id: str, run_id: str,
                              worker_id: str, lease_token: str) -> ExecutionRun:
        return await self._worker_transition(organization_id=organization_id, run_id=run_id,
            worker_id=worker_id, lease_token=lease_token, next_status=ExecutionRunStatus.COLLECTING)

    async def finish(self, *, organization_id: str, run_id: str, worker_id: str,
                     lease_token: str, outcome: ExecutionRunStatus,
                     audit_event: Mapping[str, Any] | None = None) -> ExecutionRun:
        if outcome not in {ExecutionRunStatus.COMPLETED, ExecutionRunStatus.FAILED, ExecutionRunStatus.CANCELLED}:
            raise ValueError("execution outcome must be completed, failed or cancelled")
        run = await self.get(organization_id=organization_id, run_id=run_id)
        if run is None:
            raise ExecutionRunNotFound("execution run was not found")
        if outcome is ExecutionRunStatus.CANCELLED and not run.cancel_requested:
            raise ExecutionRunConflict("worker cannot cancel without a cancellation request")
        return await self._worker_transition(organization_id=organization_id, run_id=run_id,
            worker_id=worker_id, lease_token=lease_token, next_status=outcome, audit_event=audit_event)

    async def _worker_transition(self, *, organization_id: str, run_id: str, worker_id: str,
                                 lease_token: str, next_status: ExecutionRunStatus,
                                 audit_event: Mapping[str, Any] | None = None) -> ExecutionRun:
        now = datetime.now(timezone.utc)
        async with self._client.start_session() as session, await session.start_transaction():
            current = await self._runs.find_one(
                {"_id": run_id, "organization_id": organization_id, "worker_id": worker_id,
                 "lease_token": lease_token, "lease_expires_at": {"$gt": now},
                 "status": {"$in": ["leased", "running", "collecting"]}}, session=session)
            if current is None:
                raise ExecutionRunConflict("worker lease is missing, expired or no longer owned")
            current_status = ExecutionRunStatus(current["status"])
            if current.get("cancel_requested") and next_status is not ExecutionRunStatus.CANCELLED:
                raise ExecutionRunConflict("cancellation has been requested; worker must stop and clean up")
            if next_status not in _TRANSITIONS[current_status]:
                raise ExecutionRunConflict("execution run transition is not allowed")
            updated = await self._runs.find_one_and_update(
                {"_id": run_id, "organization_id": organization_id, "worker_id": worker_id,
                 "lease_token": lease_token, "version": current["version"],
                 "status": current["status"], "lease_expires_at": {"$gt": now}},
                {"$set": {"status": next_status.value, "updated_at": now,
                          "worker_id": None if next_status in _TERMINAL else worker_id,
                          "lease_token": None if next_status in _TERMINAL else lease_token,
                          "lease_expires_at": None if next_status in _TERMINAL else current["lease_expires_at"]},
                 "$inc": {"version": 1}},
                return_document=ReturnDocument.AFTER, session=session)
            if updated is None:
                raise ExecutionRunConflict("execution run changed concurrently")
            await self._events.insert_one(_event(self._from_document(updated),
                event_type=f"execution.{next_status.value}", version=updated["version"],
                actor_id=worker_id, from_status=current_status.value, to_status=next_status.value),
                session=session)
            await self._audit_in_transaction(audit_event, session)
        return self._from_document(updated)

    async def request_cancel(self, *, organization_id: str, run_id: str, actor_id: str,
                             audit_event: Mapping[str, Any] | None = None) -> ExecutionRun:
        _identifier(actor_id, "actor_id")
        now = datetime.now(timezone.utc)
        async with self._client.start_session() as session, await session.start_transaction():
            current = await self._runs.find_one({"_id": run_id, "organization_id": organization_id}, session=session)
            if current is None:
                raise ExecutionRunNotFound("execution run was not found")
            status = ExecutionRunStatus(current["status"])
            if status in _TERMINAL:
                raise ExecutionRunConflict("terminal execution runs cannot be cancelled")
            target = ExecutionRunStatus.CANCELLED if status is ExecutionRunStatus.QUEUED else status
            updated = await self._runs.find_one_and_update(
                {"_id": run_id, "organization_id": organization_id, "version": current["version"]},
                {"$set": {"status": target.value, "cancel_requested": True, "updated_at": now,
                          "worker_id": None if target is ExecutionRunStatus.CANCELLED else current.get("worker_id"),
                          "lease_token": None if target is ExecutionRunStatus.CANCELLED else current.get("lease_token"),
                          "lease_expires_at": None if target is ExecutionRunStatus.CANCELLED else current.get("lease_expires_at")},
                 "$inc": {"version": 1}},
                return_document=ReturnDocument.AFTER, session=session)
            if updated is None:
                raise ExecutionRunConflict("execution run changed concurrently")
            await self._events.insert_one(_event(self._from_document(updated),
                event_type="execution.cancel_requested", version=updated["version"],
                actor_id=actor_id, from_status=status.value, to_status=target.value), session=session)
            await self._audit_in_transaction(audit_event, session)
        return self._from_document(updated)

    async def list_events(self, *, organization_id: str, run_id: str,
                          after_version: int = -1, limit: int = 50) -> tuple[list[dict[str, Any]], bool]:
        if after_version < -1 or not 1 <= limit <= 100:
            raise ValueError("event cursor or page size is invalid")
        cursor = self._events.find({"organization_id": organization_id, "run_id": run_id,
                                    "version": {"$gt": after_version}}).sort("version", 1).limit(limit + 1)
        rows = await cursor.to_list(length=limit + 1)
        return rows[:limit], len(rows) > limit

    @staticmethod
    def _from_document(row: dict[str, Any]) -> ExecutionRun:
        return ExecutionRun(id=row["_id"], organization_id=row["organization_id"],
            project_id=row["project_id"], task_id=row["task_id"],
            requester_issuer=row["requester_issuer"], requester_subject=row["requester_subject"],
            profile_id=row["profile_id"], snapshot_sha256=row["snapshot_sha256"],
            arguments=tuple(row["arguments"]), status=ExecutionRunStatus(row["status"]),
            version=row["version"], attempts=row["attempts"], max_attempts=row["max_attempts"],
            worker_id=row.get("worker_id"), lease_token=row.get("lease_token"),
            lease_expires_at=row.get("lease_expires_at"), cancel_requested=row.get("cancel_requested", False),
            created_at=row.get("created_at"), updated_at=row.get("updated_at"))
