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

from odei_api.services.project_lifecycle import fence_project_write

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
        raise TypeError("arguments must be a bounded argument vector")
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
    snapshot_id: str | None = None
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
    repository_binding_version: int | None = None
    repository_id: int | None = None
    repository_node_id: str | None = None
    repository_installation_id: int | None = None
    repository_owner: str | None = None
    repository_name: str | None = None
    repository_default_branch: str | None = None
    repository_base_sha: str | None = None
    worker_commit_sha: str | None = None
    worker_tree_sha: str | None = None
    worker_branch: str | None = None
    worker_pull_request_number: int | None = None
    worker_pull_request_url: str | None = None
    worker_provenance_at: datetime | None = None

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
        repository_fields = (
            self.repository_binding_version, self.repository_id, self.repository_node_id,
            self.repository_installation_id, self.repository_owner, self.repository_name,
            self.repository_default_branch, self.repository_base_sha,
        )
        if any(value is not None for value in repository_fields) and (
                any(value is None for value in repository_fields)
                or isinstance(self.repository_binding_version, bool)
                or not isinstance(self.repository_binding_version, int)
                or self.repository_binding_version < 1
                or isinstance(self.repository_id, bool) or not isinstance(self.repository_id, int)
                or self.repository_id < 1
                or isinstance(self.repository_installation_id, bool)
                or not isinstance(self.repository_installation_id, int)
                or self.repository_installation_id < 1
                or not isinstance(self.repository_node_id, str) or not self.repository_node_id
                or not isinstance(self.repository_owner, str) or not self.repository_owner
                or not isinstance(self.repository_name, str) or not self.repository_name
                or not isinstance(self.repository_default_branch, str) or not self.repository_default_branch
                or not isinstance(self.repository_base_sha, str)
                or not re.fullmatch(r"[0-9a-f]{40}", self.repository_base_sha)
        ):
            raise ValueError("trusted repository execution binding is incomplete or invalid")
        provenance_fields = (
            self.worker_commit_sha, self.worker_tree_sha, self.worker_branch,
            self.worker_pull_request_number, self.worker_pull_request_url,
            self.worker_provenance_at,
        )
        if any(value is not None for value in provenance_fields) and (
                any(value is None for value in provenance_fields)
                or not self.repository_binding_version
                or not isinstance(self.worker_commit_sha, str)
                or not re.fullmatch(r"[0-9a-f]{40}", self.worker_commit_sha)
                or not isinstance(self.worker_tree_sha, str)
                or not re.fullmatch(r"[0-9a-f]{40}", self.worker_tree_sha)
                or self.worker_branch != f"odei/nexus/{self.id}"
                or isinstance(self.worker_pull_request_number, bool)
                or not isinstance(self.worker_pull_request_number, int)
                or self.worker_pull_request_number < 1
                or not isinstance(self.worker_pull_request_url, str)
                or self.worker_pull_request_url.casefold() != f"https://github.com/{self.repository_owner}/{self.repository_name}/pull/{self.worker_pull_request_number}".casefold()
                or not isinstance(self.worker_provenance_at, datetime)
        ):
            raise ValueError("worker repository provenance is incomplete or invalid")

def _event(run: ExecutionRun, *, event_type: str, version: int,
           actor_id: str, **fields: Any) -> dict[str, Any]:
    return {"event_id": str(uuid4()), "organization_id": run.organization_id,
            "project_id": run.project_id, "task_id": run.task_id, "run_id": run.id,
            "actor_id": actor_id, "type": event_type, "version": version,
            "occurred_at": datetime.now(timezone.utc), **fields}

class MongoExecutionRunStore:
    """MongoDB run queue with transactional events and expiring worker leases."""
    def __init__(self, runs: Any, events: Any, client: Any, audit_store: Any | None = None, projects: Any | None = None):
        self._runs, self._events, self._client, self._audit = runs, events, client, audit_store
        self._projects = projects

    async def initialize(self) -> None:
        await self._runs.create_index([("organization_id", 1), ("_id", 1)], unique=True)
        await self._runs.create_index([("status", 1), ("created_at", 1), ("available_at", 1)])
        await self._runs.create_index([("status", 1), ("lease_expires_at", 1)])
        await self._runs.create_index([("organization_id", 1), ("project_id", 1), ("created_at", -1)])
        await self._runs.create_index([("organization_id", 1), ("project_id", 1), ("status", 1)])
        await self._runs.create_index(
            [("organization_id", 1), ("active_task_id", 1)], unique=True,
            partialFilterExpression={"active_task_id": {"$exists": True}},
        )
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
                "snapshot_id": run.snapshot_id, "arguments": list(run.arguments), "status": run.status.value,
                "version": run.version, "attempts": run.attempts, "max_attempts": run.max_attempts,
                "worker_id": None, "lease_token": None, "lease_expires_at": None,
                "cancel_requested": False, "active_task_id": run.task_id,
                "repository_binding_version": run.repository_binding_version,
                "repository_id": run.repository_id,
                "repository_node_id": run.repository_node_id,
                "repository_installation_id": run.repository_installation_id,
                "repository_owner": run.repository_owner,
                "repository_name": run.repository_name,
                "repository_default_branch": run.repository_default_branch,
                "repository_base_sha": run.repository_base_sha,
                "worker_commit_sha": run.worker_commit_sha,
                "worker_tree_sha": run.worker_tree_sha,
                "worker_branch": run.worker_branch,
                "worker_pull_request_number": run.worker_pull_request_number,
                "worker_pull_request_url": run.worker_pull_request_url,
                "worker_provenance_at": run.worker_provenance_at,
                "available_at": now, "created_at": now, "updated_at": now}

    async def create(self, run: ExecutionRun, *, audit_event: Mapping[str, Any] | None = None) -> ExecutionRun:
        if run.status is not ExecutionRunStatus.QUEUED or run.version != 0 or run.attempts != 0:
            raise ValueError("new execution runs must begin queued at version and attempt zero")
        now = datetime.now(timezone.utc)
        document = self._document(run, now)
        async with self._client.start_session() as session, await session.start_transaction():
            if self._projects is not None:
                await fence_project_write(
                    self._projects, organization_id=run.organization_id,
                    project_id=run.project_id, session=session,
                )
            await self._runs.insert_one(document, session=session)
            await self._events.insert_one(_event(run, event_type="execution.queued", version=0,
                                                  actor_id=run.requester_subject), session=session)
            await self._audit_in_transaction(audit_event, session)
        return self._from_document(document)

    async def create_approved_task_run(
        self, run: ExecutionRun, *, tasks: Any, task_events: Any,
        expected_task_version: int, audit_event: Mapping[str, Any],
    ) -> ExecutionRun:
        """Atomically consume an approved or repairable task and enqueue exactly one run."""
        if run.status is not ExecutionRunStatus.QUEUED or run.version != 0 or run.attempts != 0:
            raise ValueError("new execution runs must begin queued at version and attempt zero")
        if not run.snapshot_id:
            raise ValueError("approved execution runs must reference a durable workspace snapshot")
        now = datetime.now(timezone.utc)
        document = self._document(run, now)
        async with self._client.start_session() as session, await session.start_transaction():
            if self._projects is not None:
                await fence_project_write(
                    self._projects, organization_id=run.organization_id,
                    project_id=run.project_id, session=session,
                )
            task = await tasks.find_one({
                "_id": run.task_id, "organization_id": run.organization_id,
                "project_id": run.project_id, "status": {"$in": ["approved", "repairing"]},
                "version": expected_task_version,
            }, session=session)
            if task is None:
                raise ExecutionRunConflict("task is not approved or repairable, or its version has changed")
            prior_status = task["status"]
            changed = await tasks.update_one({
                "_id": run.task_id, "organization_id": run.organization_id,
                "project_id": run.project_id, "status": prior_status,
                "version": expected_task_version,
            }, {"$set": {"status": "executing", "updated_at": now},
                "$inc": {"version": 1}}, session=session)
            if changed.modified_count != 1:
                raise ExecutionRunConflict("task changed concurrently before execution")
            await task_events.insert_one({
                "event_id": str(uuid4()), "organization_id": run.organization_id,
                "project_id": run.project_id, "task_id": run.task_id,
                "actor_id": run.requester_subject,
                "type": "task.execution.started" if prior_status == "approved" else "task.repair.execution.started",
                "from_status": prior_status, "to_status": "executing",
                "version": expected_task_version + 1, "occurred_at": now,
            }, session=session)
            await self._runs.insert_one(document, session=session)
            await self._events.insert_one(_event(
                run, event_type="execution.queued", version=0,
                actor_id=run.requester_subject, task_version=expected_task_version + 1,
            ), session=session)
            await self._audit_in_transaction(audit_event, session)
        return self._from_document(document)

    async def get_active_for_task(
        self, *, organization_id: str, project_id: str, task_id: str,
    ) -> ExecutionRun | None:
        row = await self._runs.find_one({
            "organization_id": organization_id, "project_id": project_id,
            "task_id": task_id,
            "status": {"$in": ["queued", "leased", "running", "collecting"]},
        })
        return self._from_document(row) if row else None

    async def list_for_project(
        self, *, organization_id: str, project_id: str, limit: int = 50,
        requester_issuer: str | None = None, requester_subject: str | None = None,
        before_created_at: datetime | None = None, before_run_id: str | None = None,
    ) -> tuple[list[ExecutionRun], bool]:
        """Return a stable, bounded project history; optional requester scope limits members to their own runs."""
        _identifier(organization_id, "organization_id")
        _identifier(project_id, "project_id")
        if not 1 <= limit <= 100:
            raise ValueError("execution history page size must be between 1 and 100")
        if (requester_issuer is None) != (requester_subject is None):
            raise ValueError("requester identity must include both issuer and subject")
        query: dict[str, Any] = {
            "organization_id": organization_id, "project_id": project_id,
        }
        if requester_issuer is not None:
            query["requester_issuer"] = requester_issuer
            query["requester_subject"] = requester_subject
        if (before_created_at is None) != (before_run_id is None):
            raise ValueError("execution history cursor requires timestamp and run id")
        if before_created_at is not None and before_run_id is not None:
            _identifier(before_run_id, "before_run_id")
            query["$or"] = [
                {"created_at": {"$lt": before_created_at}},
                {"created_at": before_created_at, "_id": {"$lt": before_run_id}},
            ]
        cursor = self._runs.find(query).sort([("created_at", -1), ("_id", -1)]).limit(limit + 1)
        rows = await cursor.to_list(length=limit + 1)
        return [self._from_document(row) for row in rows[:limit]], len(rows) > limit

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
            if self._projects is not None:
                await fence_project_write(
                    self._projects, organization_id=row["organization_id"],
                    project_id=row["project_id"], session=session,
                )
            claimed = self._from_document(row)
            await self._events.insert_one(_event(claimed, event_type="execution.leased",
                version=claimed.version, actor_id=worker_id, attempt=claimed.attempts), session=session)
        return claimed

    async def expire_exhausted(self, *, actor_id: str, limit: int = 50,
                               tasks: Any | None = None, task_events: Any | None = None) -> int:
        """Fail runs whose queue or expired lease exhausted the bounded attempt budget."""
        _identifier(actor_id, "actor_id")
        if not 1 <= limit <= 500:
            raise ValueError("expiry batch limit is invalid")
        now = datetime.now(timezone.utc)
        exhausted = {"$expr": {"$gte": ["$attempts", "$max_attempts"]}}
        query = {"$or": [
            {"status": ExecutionRunStatus.QUEUED.value, **exhausted},
            {"status": {"$in": ["leased", "running", "collecting"]},
             "lease_expires_at": {"$lte": now}, **exhausted},
        ]}
        count = 0
        async with self._client.start_session() as session, await session.start_transaction():
            cursor = self._runs.find(query, session=session).sort("created_at", 1).limit(limit)
            rows = await cursor.to_list(length=limit)
            for row in rows:
                if self._projects is not None:
                    await fence_project_write(
                        self._projects, organization_id=row["organization_id"],
                        project_id=row["project_id"], session=session, allow_deleting=True,
                    )
                status = ExecutionRunStatus(row["status"])
                updated = await self._runs.find_one_and_update(
                    {"_id": row["_id"], "organization_id": row["organization_id"],
                     "version": row["version"], "status": row["status"]},
                    {"$set": {"status": ExecutionRunStatus.FAILED.value,
                              "worker_id": None, "lease_token": None,
                              "lease_expires_at": None, "updated_at": now},
                     "$unset": {"active_task_id": ""},
                     "$inc": {"version": 1}},
                    return_document=ReturnDocument.AFTER, session=session,
                )
                if updated is None:
                    continue
                run = self._from_document(updated)
                await self._events.insert_one(_event(
                    run, event_type="execution.failed", version=run.version,
                    actor_id=actor_id, from_status=status.value,
                    to_status=ExecutionRunStatus.FAILED.value,
                    reason="attempt_budget_exhausted",
                ), session=session)
                if tasks is not None and task_events is not None:
                    task = await tasks.find_one({
                        "_id": run.task_id, "organization_id": run.organization_id,
                        "project_id": run.project_id, "status": "executing",
                    }, session=session)
                    if task is not None:
                        task_updated = await tasks.find_one_and_update(
                            {"_id": task["_id"], "organization_id": run.organization_id,
                             "version": task["version"], "status": "executing"},
                            {"$set": {"status": "repairing", "updated_at": now},
                             "$inc": {"version": 1}},
                            return_document=ReturnDocument.AFTER, session=session,
                        )
                        if task_updated is None:
                            raise ExecutionRunConflict("task changed while exhausted execution was finalized")
                        await task_events.insert_one({
                            "event_id": str(uuid4()), "organization_id": run.organization_id,
                            "project_id": run.project_id, "task_id": run.task_id,
                            "actor_id": actor_id, "type": "task.status_changed",
                            "from_status": "executing", "to_status": "repairing",
                            "version": task_updated["version"], "occurred_at": now,
                        }, session=session)
                await self._audit_in_transaction({
                    "organization_id": run.organization_id,
                    "actor_issuer": "https://odei-studio.internal",
                    "actor_subject": actor_id,
                    "action": "nexus.execution.exhausted",
                    "target_type": "nexus_execution_run",
                    "target_id": run.id,
                    "outcome": "failure",
                    "request_id": uuid4().hex,
                    "metadata": {"attempts": run.attempts, "max_attempts": run.max_attempts},
                }, session)
                count += 1
        return count

    async def heartbeat(self, *, organization_id: str, run_id: str, worker_id: str,
                        lease_token: str, lease_seconds: int = 30) -> datetime:
        now = datetime.now(timezone.utc)
        if not 5 <= lease_seconds <= 300 or not re.fullmatch(r"[a-f0-9]{32}", lease_token or ""):
            raise ValueError("lease heartbeat parameters are invalid")
        expiry = now + timedelta(seconds=lease_seconds)
        async with self._client.start_session() as session, await session.start_transaction():
            current = await self._runs.find_one(
                {"_id": run_id, "organization_id": organization_id,
                 "worker_id": worker_id, "lease_token": lease_token,
                 "status": {"$in": ["leased", "running", "collecting"]},
                 "lease_expires_at": {"$gt": now}},
                session=session,
            )
            if current is None:
                raise ExecutionRunConflict("worker lease is missing, expired or no longer owned")
            if self._projects is not None:
                await fence_project_write(
                    self._projects, organization_id=current["organization_id"],
                    project_id=current["project_id"], session=session, allow_deleting=True,
                )
            result = await self._runs.update_one(
                {"_id": run_id, "organization_id": organization_id,
                 "worker_id": worker_id, "lease_token": lease_token,
                 "status": {"$in": ["leased", "running", "collecting"]},
                 "lease_expires_at": {"$gt": now}},
                {"$set": {"lease_expires_at": expiry, "updated_at": now}},
                session=session,
            )
            if result.modified_count != 1:
                raise ExecutionRunConflict("worker lease is missing, expired or no longer owned")
        return expiry


    async def record_worker_provenance(
        self, *, organization_id: str, run_id: str, worker_id: str,
        lease_token: str, provenance: Mapping[str, Any],
        audit_event: Mapping[str, Any] | None = None,
    ) -> ExecutionRun:
        """Persist verified GitHub commit and PR provenance under the active worker lease."""
        required = {
            "repository_id", "repository_node_id", "installation_id", "binding_version",
            "owner", "name", "default_branch", "base_sha", "commit_sha", "tree_sha",
            "branch", "pull_request_number", "pull_request_url",
        }
        if not isinstance(provenance, Mapping) or not required.issubset(provenance):
            raise ValueError("worker provenance payload is incomplete")
        now = datetime.now(timezone.utc)
        async with self._client.start_session() as session, await session.start_transaction():
            current = await self._runs.find_one({
                "_id": run_id, "organization_id": organization_id,
                "worker_id": worker_id, "lease_token": lease_token,
                "status": ExecutionRunStatus.COLLECTING.value,
                "lease_expires_at": {"$gt": now},
            }, session=session)
            if current is None:
                raise ExecutionRunConflict("worker lease is missing or no longer collecting")
            if self._projects is not None:
                await fence_project_write(
                    self._projects, organization_id=current["organization_id"],
                    project_id=current["project_id"], session=session,
                )
            if (
                current.get("worker_commit_sha") is not None
                or current.get("repository_binding_version") != provenance["binding_version"]
                or current.get("repository_id") != provenance["repository_id"]
                or current.get("repository_node_id") != provenance["repository_node_id"]
                or current.get("repository_installation_id") != provenance["installation_id"]
                or current.get("repository_owner") != provenance["owner"]
                or current.get("repository_name") != provenance["name"]
                or current.get("repository_default_branch") != provenance["default_branch"]
                or current.get("repository_base_sha") != provenance["base_sha"]
            ):
                raise ExecutionRunConflict("worker provenance does not match the run's trusted repository binding")
            updated = await self._runs.find_one_and_update(
                {"_id": run_id, "organization_id": organization_id,
                 "version": current["version"], "worker_id": worker_id,
                 "lease_token": lease_token, "status": ExecutionRunStatus.COLLECTING.value,
                 "lease_expires_at": {"$gt": now}},
                {"$set": {
                    "worker_commit_sha": provenance["commit_sha"],
                    "worker_tree_sha": provenance["tree_sha"],
                    "worker_branch": provenance["branch"],
                    "worker_pull_request_number": provenance["pull_request_number"],
                    "worker_pull_request_url": provenance["pull_request_url"],
                    "worker_provenance_at": now, "updated_at": now,
                }, "$inc": {"version": 1}},
                return_document=ReturnDocument.AFTER, session=session,
            )
            if updated is None:
                raise ExecutionRunConflict("execution run changed while worker provenance was recorded")
            run = self._from_document(updated)
            await self._events.insert_one(_event(
                run, event_type="execution.repository_provenance_recorded",
                version=run.version, actor_id=worker_id,
                repository_id=run.repository_id, commit_sha=run.worker_commit_sha,
                tree_sha=run.worker_tree_sha, pull_request_number=run.worker_pull_request_number,
            ), session=session)
            await self._audit_in_transaction(audit_event, session)
        return run

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
                     audit_event: Mapping[str, Any] | None = None,
                     tasks: Any | None = None, task_events: Any | None = None) -> ExecutionRun:
        if outcome not in {ExecutionRunStatus.COMPLETED, ExecutionRunStatus.FAILED, ExecutionRunStatus.CANCELLED}:
            raise ValueError("execution outcome must be completed, failed or cancelled")
        run = await self.get(organization_id=organization_id, run_id=run_id)
        if run is None:
            raise ExecutionRunNotFound("execution run was not found")
        if outcome is ExecutionRunStatus.CANCELLED and not run.cancel_requested:
            raise ExecutionRunConflict("worker cannot cancel without a cancellation request")
        return await self._worker_transition(organization_id=organization_id, run_id=run_id,
            worker_id=worker_id, lease_token=lease_token, next_status=outcome,
            audit_event=audit_event, task_collection=tasks, task_events=task_events)

    async def _worker_transition(self, *, organization_id: str, run_id: str, worker_id: str,
                                 lease_token: str, next_status: ExecutionRunStatus,
                                 audit_event: Mapping[str, Any] | None = None,
                                 task_collection: Any | None = None,
                                 task_events: Any | None = None) -> ExecutionRun:
        now = datetime.now(timezone.utc)
        async with self._client.start_session() as session, await session.start_transaction():
            current = await self._runs.find_one(
                {"_id": run_id, "organization_id": organization_id, "worker_id": worker_id,
                 "lease_token": lease_token, "lease_expires_at": {"$gt": now},
                 "status": {"$in": ["leased", "running", "collecting"]}}, session=session)
            if current is None:
                raise ExecutionRunConflict("worker lease is missing, expired or no longer owned")
            if self._projects is not None:
                await fence_project_write(
                    self._projects, organization_id=current["organization_id"],
                    project_id=current["project_id"], session=session,
                )
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
                 "$inc": {"version": 1},
                 **({"$unset": {"active_task_id": ""}} if next_status in _TERMINAL else {})},
                return_document=ReturnDocument.AFTER, session=session)
            if updated is None:
                raise ExecutionRunConflict("execution run changed concurrently")
            await self._events.insert_one(_event(self._from_document(updated),
                event_type=f"execution.{next_status.value}", version=updated["version"],
                actor_id=worker_id, from_status=current_status.value, to_status=next_status.value),
                session=session)
            if next_status in _TERMINAL and task_collection is not None and task_events is not None:
                target_task_status = {
                    ExecutionRunStatus.COMPLETED: "validating",
                    ExecutionRunStatus.FAILED: "repairing",
                    ExecutionRunStatus.CANCELLED: "cancelled",
                }[next_status]
                task = await task_collection.find_one({
                    "_id": updated["task_id"], "organization_id": organization_id,
                    "project_id": updated["project_id"], "status": "executing",
                }, session=session)
                if task is not None:
                    task_updated = await task_collection.find_one_and_update(
                        {"_id": task["_id"], "organization_id": organization_id,
                         "version": task["version"], "status": "executing"},
                        {"$set": {"status": target_task_status, "updated_at": now},
                         "$inc": {"version": 1}},
                        return_document=ReturnDocument.AFTER, session=session,
                    )
                    if task_updated is None:
                        raise ExecutionRunConflict("task changed while execution was being finalized")
                    await task_events.insert_one({
                        "event_id": str(uuid4()), "organization_id": organization_id,
                        "project_id": updated["project_id"], "task_id": updated["task_id"],
                        "actor_id": worker_id, "type": "task.status_changed",
                        "from_status": "executing", "to_status": target_task_status,
                        "version": task_updated["version"], "occurred_at": now,
                    }, session=session)
            await self._audit_in_transaction(audit_event, session)
        return self._from_document(updated)

    async def request_cancel(self, *, organization_id: str, run_id: str, actor_id: str,
                             audit_event: Mapping[str, Any] | None = None,
                             tasks: Any | None = None, task_events: Any | None = None,
                             task_audit_event: Mapping[str, Any] | None = None) -> ExecutionRun:
        _identifier(actor_id, "actor_id")
        now = datetime.now(timezone.utc)
        async with self._client.start_session() as session, await session.start_transaction():
            current = await self._runs.find_one({"_id": run_id, "organization_id": organization_id}, session=session)
            if current is None:
                raise ExecutionRunNotFound("execution run was not found")
            if self._projects is not None:
                await fence_project_write(
                    self._projects, organization_id=current["organization_id"],
                    project_id=current["project_id"], session=session,
                )
            status = ExecutionRunStatus(current["status"])
            if status is ExecutionRunStatus.CANCELLED and current.get("cancel_requested"):
                return self._from_document(current)
            if status in _TERMINAL:
                raise ExecutionRunConflict("terminal execution runs cannot be cancelled")
            if current.get("cancel_requested"):
                return self._from_document(current)
            target = ExecutionRunStatus.CANCELLED if status is ExecutionRunStatus.QUEUED else status
            updated = await self._runs.find_one_and_update(
                {"_id": run_id, "organization_id": organization_id, "version": current["version"]},
                {"$set": {"status": target.value, "cancel_requested": True, "updated_at": now,
                          "worker_id": None if target is ExecutionRunStatus.CANCELLED else current.get("worker_id"),
                          "lease_token": None if target is ExecutionRunStatus.CANCELLED else current.get("lease_token"),
                          "lease_expires_at": None if target is ExecutionRunStatus.CANCELLED else current.get("lease_expires_at")},
                 "$inc": {"version": 1},
                 **({"$unset": {"active_task_id": ""}} if target is ExecutionRunStatus.CANCELLED else {})},
                return_document=ReturnDocument.AFTER, session=session)
            if updated is None:
                raise ExecutionRunConflict("execution run changed concurrently")
            await self._events.insert_one(_event(self._from_document(updated),
                event_type="execution.cancel_requested", version=updated["version"],
                actor_id=actor_id, from_status=status.value, to_status=target.value), session=session)
            if target is ExecutionRunStatus.CANCELLED and tasks is not None and task_events is not None:
                task = await tasks.find_one({
                    "_id": current["task_id"], "organization_id": organization_id,
                    "project_id": current["project_id"], "status": "executing",
                }, session=session)
                if task is not None:
                    task_updated = await tasks.find_one_and_update(
                        {"_id": task["_id"], "organization_id": organization_id,
                         "version": task["version"], "status": "executing"},
                        {"$set": {"status": "cancelled", "updated_at": now},
                         "$inc": {"version": 1}},
                        return_document=ReturnDocument.AFTER, session=session,
                    )
                    if task_updated is None:
                        raise ExecutionRunConflict("task changed while queued execution was cancelled")
                    await task_events.insert_one({
                        "event_id": str(uuid4()), "organization_id": organization_id,
                        "project_id": current["project_id"], "task_id": current["task_id"],
                        "actor_id": actor_id, "type": "task.cancelled",
                        "from_status": "executing", "to_status": "cancelled",
                        "version": task_updated["version"], "occurred_at": now,
                    }, session=session)
                    await self._audit_in_transaction(task_audit_event, session)
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
            arguments=tuple(row["arguments"]), snapshot_id=row.get("snapshot_id"),
            status=ExecutionRunStatus(row["status"]),
            version=row["version"], attempts=row["attempts"], max_attempts=row["max_attempts"],
            worker_id=row.get("worker_id"), lease_token=row.get("lease_token"),
            lease_expires_at=row.get("lease_expires_at"), cancel_requested=row.get("cancel_requested", False),
            created_at=row.get("created_at"), updated_at=row.get("updated_at"),
            repository_binding_version=row.get("repository_binding_version"),
            repository_id=row.get("repository_id"), repository_node_id=row.get("repository_node_id"),
            repository_installation_id=row.get("repository_installation_id"),
            repository_owner=row.get("repository_owner"), repository_name=row.get("repository_name"),
            repository_default_branch=row.get("repository_default_branch"),
            repository_base_sha=row.get("repository_base_sha"),
            worker_commit_sha=row.get("worker_commit_sha"), worker_tree_sha=row.get("worker_tree_sha"),
            worker_branch=row.get("worker_branch"),
            worker_pull_request_number=row.get("worker_pull_request_number"),
            worker_pull_request_url=row.get("worker_pull_request_url"),
            worker_provenance_at=row.get("worker_provenance_at"))
