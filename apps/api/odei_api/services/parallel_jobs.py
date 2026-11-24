"""Durable tenant-scoped parallel NEXUS jobs with leases and resumable checkpoints."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_MAX_CHECKPOINT_BYTES = 256_000
_MAX_JOBS_PER_GROUP = 32
_TERMINAL = frozenset({"completed", "failed", "cancelled"})


class ParallelJobError(RuntimeError):
    """Base error for durable parallel-job operations."""


class ParallelJobConflict(ParallelJobError):
    """The job state or lease changed concurrently."""


@dataclass(frozen=True)
class ParallelJob:
    id: str
    group_id: str
    organization_id: str
    project_id: str
    status: str
    version: int
    attempt: int
    max_attempts: int
    checkpoint: dict[str, Any] | None
    checkpoint_sha256: str | None
    worker_id: str | None
    lease_token: str | None
    lease_expires_at: datetime | None


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} is invalid")
    return value


def _checkpoint(value: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict):
        raise TypeError("checkpoint must be an object")
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ValueError("checkpoint must contain canonical JSON values") from exc
    if len(encoded) > _MAX_CHECKPOINT_BYTES:
        raise ValueError("checkpoint exceeds the size limit")
    return value, hashlib.sha256(encoded).hexdigest()


class MongoParallelJobStore:
    """Mongo-backed job groups; workers coordinate only through atomic leases."""

    def __init__(self, jobs: Any, groups: Any, events: Any):
        self._jobs, self._groups, self._events = jobs, groups, events

    async def initialize(self) -> None:
        await self._groups.create_index(
            [("organization_id", 1), ("project_id", 1), ("group_id", 1)], unique=True
        )
        await self._jobs.create_index([("organization_id", 1), ("project_id", 1), ("group_id", 1)])
        await self._jobs.create_index([("status", 1), ("available_at", 1), ("lease_expires_at", 1)])
        await self._jobs.create_index([("organization_id", 1), ("job_id", 1)], unique=True)
        await self._events.create_index([("organization_id", 1), ("job_id", 1), ("version", 1)], unique=True)

    async def create_group(
        self, *, organization_id: str, project_id: str, group_id: str,
        jobs: list[dict[str, Any]], max_attempts: int = 3,
    ) -> list[ParallelJob]:
        organization_id = _identifier(organization_id, "organization_id")
        project_id = _identifier(project_id, "project_id")
        group_id = _identifier(group_id, "group_id")
        if not isinstance(jobs, list) or not 1 <= len(jobs) <= _MAX_JOBS_PER_GROUP:
            raise ValueError(f"jobs must contain 1 to {_MAX_JOBS_PER_GROUP} entries")
        if isinstance(max_attempts, bool) or not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        now = datetime.now(timezone.utc)
        group = {
            "_id": f"{organization_id}:{project_id}:{group_id}", "group_id": group_id, "organization_id": organization_id, "project_id": project_id,
            "status": "creating", "job_count": len(jobs), "created_at": now, "updated_at": now,
        }
        documents = []
        for index, item in enumerate(jobs):
            if not isinstance(item, dict) or set(item) - {"job_id", "payload", "depends_on"}:
                raise ValueError("job entries may contain only job_id, payload and depends_on")
            job_id = _identifier(item.get("job_id", f"{group_id}-{index}"), "job_id")
            payload = item.get("payload", {})
            if not isinstance(payload, dict):
                raise TypeError("job payload must be an object")
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            if len(encoded) > 32_768:
                raise ValueError("job payload exceeds the size limit")
            dependencies = item.get("depends_on", [])
            if not isinstance(dependencies, list) or any(not isinstance(dep, str) for dep in dependencies) or len(set(dependencies)) != len(dependencies):
                raise ValueError("depends_on must be a list of job identifiers")
            documents.append({
                "_id": uuid4().hex, "job_id": job_id, "group_id": group_id,
                "organization_id": organization_id, "project_id": project_id,
                "payload": payload, "depends_on": dependencies,
                "status": "staging", "initial_status": "queued" if not dependencies else "blocked",
                "version": 0, "attempt": 0, "max_attempts": max_attempts,
                "checkpoint": None, "checkpoint_sha256": None,
                "worker_id": None, "lease_token": None, "lease_expires_at": None,
                "available_at": now, "created_at": now, "updated_at": now,
            })
        ids = {row["job_id"] for row in documents}
        if len(ids) != len(documents) or any(dep not in ids for row in documents for dep in row["depends_on"]):
            raise ValueError("job identifiers must be unique and dependencies must refer to this group")
        if any(row["job_id"] in row["depends_on"] for row in documents):
            raise ValueError("a job cannot depend on itself")
        # Reject dependency cycles before persisting any rows.
        graph = {row["job_id"]: row["depends_on"] for row in documents}
        visiting: set[str] = set()
        visited: set[str] = set()
        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("job dependencies contain a cycle")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)
        for node in graph:
            visit(node)
        await self._groups.insert_one(group)
        try:
            await self._jobs.insert_many(documents, ordered=True)
            for row in documents:
                await self._events.insert_one({
                    "organization_id": organization_id, "job_id": row["job_id"], "version": 0,
                    "event": "job.queued" if row["initial_status"] == "queued" else "job.blocked",
                    "group_id": group_id, "occurred_at": now,
                })
            for row in documents:
                activated = await self._jobs.update_one(
                    {"organization_id": organization_id, "job_id": row["job_id"], "status": "staging"},
                    {"$set": {"status": row["initial_status"], "updated_at": now},
                     "$unset": {"initial_status": ""}},
                )
                if not activated.modified_count:
                    raise ParallelJobConflict("job group activation failed")
            await self._groups.update_one(
                {"_id": group["_id"], "organization_id": organization_id},
                {"$set": {"status": "queued", "updated_at": now}},
            )
        except Exception:
            for row in documents:
                await self._jobs.delete_one({"_id": row["_id"]})
                await self._events.delete_one({
                    "organization_id": organization_id, "job_id": row["job_id"], "version": 0,
                })
            await self._groups.delete_one({"_id": group["_id"], "organization_id": organization_id})
            raise
        for row in documents:
            row["status"] = row["initial_status"]
            row.pop("initial_status", None)
        return [self._from_doc(row) for row in documents]

    async def claim_next(self, *, worker_id: str, lease_seconds: int = 60) -> ParallelJob | None:
        worker_id = _identifier(worker_id, "worker_id")
        if isinstance(lease_seconds, bool) or not 5 <= lease_seconds <= 600:
            raise ValueError("lease_seconds must be between 5 and 600")
        now = datetime.now(timezone.utc)
        # Expired leases are requeued or terminally failed before a fresh claim.
        expired = await self._jobs.find({
            "status": "leased", "lease_expires_at": {"$lte": now},
        }).limit(100).to_list(length=100)
        for row in expired:
            retry = row["attempt"] < row["max_attempts"]
            update = await self._jobs.update_one(
                {"_id": row["_id"], "version": row["version"], "lease_expires_at": {"$lte": now}},
                {"$set": {"status": "queued" if retry else "failed",
                          "worker_id": None, "lease_token": None, "lease_expires_at": None,
                          "available_at": now, "updated_at": now},
                 "$inc": {"version": 1}},
            )
            if update.modified_count:
                await self._events.insert_one({
                    "organization_id": row["organization_id"], "job_id": row["job_id"],
                    "version": row["version"] + 1, "event": "job.lease_expired",
                    "occurred_at": now,
                })
        candidates = await self._jobs.find({
            "status": "queued", "available_at": {"$lte": now},
        }).sort("created_at", 1).limit(100).to_list(length=100)
        for candidate in candidates:
            dependencies = candidate.get("depends_on", [])
            if dependencies:
                rows = await self._jobs.find({
                    "organization_id": candidate["organization_id"],
                    "group_id": candidate["group_id"], "job_id": {"$in": dependencies},
                }).to_list(length=len(dependencies))
                if len(rows) != len(dependencies) or any(r["status"] != "completed" for r in rows):
                    if any(r["status"] in {"failed", "cancelled"} for r in rows):
                        await self._jobs.update_one(
                            {"_id": candidate["_id"], "version": candidate["version"], "status": "queued"},
                            {"$set": {"status": "cancelled", "updated_at": now}, "$inc": {"version": 1}},
                        )
                    continue
            token = uuid4().hex
            claimed = await self._jobs.find_one_and_update(
                {"_id": candidate["_id"], "version": candidate["version"], "status": "queued"},
                {"$set": {"status": "leased", "worker_id": worker_id, "lease_token": token,
                          "lease_expires_at": now + timedelta(seconds=lease_seconds), "updated_at": now},
                 "$inc": {"attempt": 1, "version": 1}},
                return_document=ReturnDocument.AFTER,
            )
            if claimed is not None:
                await self._events.insert_one({
                    "organization_id": claimed["organization_id"], "job_id": claimed["job_id"],
                    "version": claimed["version"], "event": "job.leased",
                    "worker_id": worker_id, "occurred_at": now,
                })
                return self._from_doc(claimed)
        return None

    async def heartbeat(
        self, *, organization_id: str, job_id: str, worker_id: str,
        lease_token: str, lease_seconds: int = 60,
    ) -> None:
        if isinstance(lease_seconds, bool) or not 5 <= lease_seconds <= 600:
            raise ValueError("lease_seconds must be between 5 and 600")
        now = datetime.now(timezone.utc)
        result = await self._jobs.update_one(
            {"organization_id": organization_id, "job_id": job_id,
             "worker_id": worker_id, "lease_token": lease_token,
             "status": "leased", "lease_expires_at": {"$gt": now}},
            {"$set": {"lease_expires_at": now + timedelta(seconds=lease_seconds),
                      "updated_at": now}},
        )
        if result.modified_count != 1:
            raise ParallelJobConflict("worker lease is missing, expired or no longer owned")

    async def checkpoint(
        self, *, organization_id: str, job_id: str, worker_id: str,
        lease_token: str, expected_version: int, checkpoint: dict[str, Any],
    ) -> ParallelJob:
        safe, digest = _checkpoint(checkpoint)
        now = datetime.now(timezone.utc)
        row = await self._jobs.find_one_and_update(
            {"organization_id": organization_id, "job_id": job_id, "worker_id": worker_id,
             "lease_token": lease_token, "lease_expires_at": {"$gt": now},
             "status": "leased", "version": expected_version},
            {"$set": {"checkpoint": safe, "checkpoint_sha256": digest, "updated_at": now},
             "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if row is None:
            raise ParallelJobConflict("job lease expired or checkpoint version changed")
        await self._events.insert_one({
            "organization_id": organization_id, "job_id": job_id, "version": row["version"],
            "event": "job.checkpointed", "checkpoint_sha256": digest, "occurred_at": now,
        })
        return self._from_doc(row)

    async def finish(
        self, *, organization_id: str, job_id: str, worker_id: str,
        lease_token: str, expected_version: int, outcome: str,
    ) -> ParallelJob:
        if outcome not in _TERMINAL:
            raise ValueError("outcome must be completed, failed or cancelled")
        now = datetime.now(timezone.utc)
        row = await self._jobs.find_one_and_update(
            {"organization_id": organization_id, "job_id": job_id, "worker_id": worker_id,
             "lease_token": lease_token, "lease_expires_at": {"$gt": now},
             "status": "leased", "version": expected_version},
            {"$set": {"status": outcome, "worker_id": None, "lease_token": None,
                      "lease_expires_at": None, "updated_at": now},
             "$inc": {"version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if row is None:
            raise ParallelJobConflict("job lease expired or job state changed")
        await self._events.insert_one({
            "organization_id": organization_id, "job_id": job_id, "version": row["version"],
            "event": f"job.{outcome}", "occurred_at": now,
        })
        if outcome == "completed":
            await self._jobs.update_many(
                {"organization_id": organization_id, "group_id": row["group_id"],
                 "status": "blocked", "depends_on": job_id},
                {"$set": {"status": "queued", "available_at": now, "updated_at": now},
                 "$inc": {"version": 1}},
            )
        return self._from_doc(row)

    async def cancel_group(self, *, organization_id: str, project_id: str, group_id: str) -> int:
        now = datetime.now(timezone.utc)
        queued = await self._jobs.update_many(
            {"organization_id": organization_id, "project_id": project_id,
             "group_id": group_id, "status": {"$in": ["queued", "blocked"]}},
            {"$set": {"status": "cancelled", "updated_at": now}, "$inc": {"version": 1}},
        )
        leased = await self._jobs.update_many(
            {"organization_id": organization_id, "project_id": project_id,
             "group_id": group_id, "status": "leased"},
            {"$set": {"cancel_requested": True, "updated_at": now}},
        )
        return queued.modified_count + leased.modified_count

    async def cancellation_requested(
        self, *, organization_id: str, job_id: str, worker_id: str, lease_token: str,
    ) -> bool:
        row = await self._jobs.find_one({
            "organization_id": organization_id, "job_id": job_id,
            "worker_id": worker_id, "lease_token": lease_token, "status": "leased",
        })
        if row is None:
            raise ParallelJobConflict("worker no longer owns this job lease")
        return bool(row.get("cancel_requested", False))

    async def get(self, *, organization_id: str, project_id: str, job_id: str) -> ParallelJob | None:
        row = await self._jobs.find_one({
            "organization_id": organization_id, "project_id": project_id, "job_id": job_id,
        })
        return self._from_doc(row) if row else None

    @staticmethod
    def _from_doc(row: dict[str, Any]) -> ParallelJob:
        return ParallelJob(
            id=row["job_id"], group_id=row["group_id"],
            organization_id=row["organization_id"], project_id=row["project_id"],
            status=row["status"], version=row["version"], attempt=row["attempt"],
            max_attempts=row["max_attempts"], checkpoint=row.get("checkpoint"),
            checkpoint_sha256=row.get("checkpoint_sha256"), worker_id=row.get("worker_id"),
            lease_token=row.get("lease_token"), lease_expires_at=row.get("lease_expires_at"),
        )


class GitWorktreeManager:
    """Create isolated Git worktrees under one trusted root without shell execution."""

    def __init__(self, repository: str | Path, worktree_root: str | Path):
        repository_path = Path(repository)
        root_path = Path(worktree_root)
        if repository_path.is_symlink() or root_path.is_symlink():
            raise ValueError("repository and worktree root cannot be symbolic links")
        self.repository = repository_path.resolve(strict=True)
        self.root = root_path.resolve(strict=True)
        if not (self.repository / ".git").exists() or not self.root.is_dir() or self.repository == self.root:
            raise ValueError("repository must be a Git worktree and root must be separate")

    def create(self, *, job_id: str, base_commit: str) -> Path:
        _identifier(job_id, "job_id")
        if not re.fullmatch(r"[a-f0-9]{40,64}", base_commit):
            raise ValueError("base_commit must be a full Git object ID")
        target = (self.root / job_id).resolve()
        if target.parent != self.root or target.exists() or target.is_symlink():
            raise ValueError("worktree target is not a fresh child of the trusted root")
        result = subprocess.run(
            ["git", "-C", str(self.repository), "worktree", "add", "--detach", str(target), base_commit],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode:
            raise ParallelJobError("Git could not create an isolated worktree")
        return target

    def remove(self, worktree: str | Path) -> None:
        target = Path(worktree)
        if target.is_symlink() or target.resolve(strict=True).parent != self.root:
            raise ValueError("worktree is outside the trusted root")
        result = subprocess.run(
            ["git", "-C", str(self.repository), "worktree", "remove", "--force", str(target)],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode:
            raise ParallelJobError("Git could not remove the isolated worktree")
