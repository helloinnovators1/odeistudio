"""Durable, idempotent MAC provider deployment-attempt ledger.

This ledger records execution attempts; it deliberately does not execute providers.
A deployment worker must obtain secrets server-side and call a provider adapter.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING

_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_ACTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_PROVIDER = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_WORKER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


class MacDeploymentError(ValueError):
    """Invalid deployment request or result."""


class MacDeploymentConflict(RuntimeError):
    """Deployment compare-and-set or idempotency conflict."""


class MacDeploymentNotFound(LookupError):
    """Deployment attempt does not exist."""


class MongoMacDeploymentStore:
    """Append-oriented deployment ledger with explicit worker state transitions."""

    def __init__(self, attempts: Any, environment_store: Any):
        self.attempts = attempts
        self.environment_store = environment_store

    async def initialize(self) -> None:
        await self.attempts.create_index(
            [("environment", ASCENDING), ("idempotency_key", ASCENDING)],
            unique=True, name="mac_deployment_idempotency",
        )
        await self.attempts.create_index(
            [("environment", ASCENDING), ("created_at", DESCENDING)],
            name="mac_deployment_environment_history",
        )
        await self.attempts.create_index(
            [("state", ASCENDING), ("created_at", ASCENDING)],
            name="mac_deployment_worker_queue",
        )
        await self.attempts.create_index(
            [("state", ASCENDING), ("lease_expires_at", ASCENDING)],
            name="mac_deployment_worker_leases",
        )

    async def create_attempt(
        self, *, environment: str, version: int, provider: str,
        idempotency_key: str, actor: str, session: Any | None = None,
    ) -> dict[str, Any]:
        if not isinstance(environment, str) or environment not in {
            "development", "staging", "production"
        }:
            raise MacDeploymentError("Environment is invalid")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise MacDeploymentError("Revision version must be a positive integer")
        if not isinstance(provider, str) or not _PROVIDER.fullmatch(provider):
            raise MacDeploymentError("Provider identifier is invalid")
        if not isinstance(idempotency_key, str) or not _KEY.fullmatch(idempotency_key):
            raise MacDeploymentError("A bounded idempotency key is required")
        if not isinstance(actor, str) or not _ACTOR.fullmatch(actor):
            raise MacDeploymentError("Verified actor identity is invalid")

        record = await self.environment_store.get(environment, session=session)
        revision = next(
            (item for item in record.get("versions", []) if item.get("version") == version),
            None,
        )
        if revision is None:
            raise MacDeploymentNotFound("Approved environment revision does not exist")
        if revision.get("status") not in {"approved", "promoted"}:
            raise MacDeploymentError("Only approved revisions can be deployed")

        fingerprint = hashlib.sha256(json.dumps(
            {"environment": environment, "version": version, "provider": provider},
            sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        now = datetime.now(timezone.utc)
        attempt = {
            "_id": uuid4().hex,
            "environment": environment,
            "revision": version,
            "provider": provider,
            "idempotency_key": idempotency_key,
            "request_fingerprint": fingerprint,
            "requested_by": actor,
            "state": "queued",
            "created_at": now,
            "updated_at": now,
            "worker_id": None,
            "attempt_count": 0,
            "lease_expires_at": None,
            "started_at": None,
            "finished_at": None,
            "provider_deployment_id": None,
            "verified": None,
            "result_summary": None,
        }
        try:
            await self.attempts.insert_one(attempt, session=session)
            return attempt
        except Exception as exc:
            if type(exc).__name__ != "DuplicateKeyError":
                raise
            existing = await self.attempts.find_one(
                {"environment": environment, "idempotency_key": idempotency_key},
                session=session,
            )
            if existing is None or existing.get("request_fingerprint") != fingerprint:
                raise MacDeploymentConflict(
                    "Idempotency key was already used for a different deployment request"
                ) from exc
            return existing

    async def claim_next(
        self, *, worker_id: str, lease_seconds: int = 120, max_attempts: int = 5,
    ) -> dict[str, Any] | None:
        if not isinstance(worker_id, str) or not _WORKER.fullmatch(worker_id):
            raise MacDeploymentError("Worker identity is invalid")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 15 <= lease_seconds <= 900:
            raise MacDeploymentError("Worker lease must be between 15 and 900 seconds")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 20:
            raise MacDeploymentError("Maximum attempts must be between 1 and 20")
        now = datetime.now(timezone.utc)
        return await self.attempts.find_one_and_update(
            {"state": "queued", "attempt_count": {"$lt": max_attempts}},
            {"$set": {"state": "running", "worker_id": worker_id,
                      "lease_expires_at": now + timedelta(seconds=lease_seconds),
                      "started_at": now, "updated_at": now},
             "$inc": {"attempt_count": 1}},
            sort=[("created_at", ASCENDING)],
            return_document=True,
        )

    async def claim(
        self, *, attempt_id: str, worker_id: str, lease_seconds: int = 120,
        max_attempts: int = 5,
    ) -> dict[str, Any]:
        if not isinstance(attempt_id, str) or not re.fullmatch(r"[a-f0-9]{32}", attempt_id):
            raise MacDeploymentError("Deployment attempt identifier is invalid")
        if not isinstance(worker_id, str) or not _WORKER.fullmatch(worker_id):
            raise MacDeploymentError("Worker identity is invalid")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 15 <= lease_seconds <= 900:
            raise MacDeploymentError("Worker lease must be between 15 and 900 seconds")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 20:
            raise MacDeploymentError("Maximum attempts must be between 1 and 20")
        now = datetime.now(timezone.utc)
        result = await self.attempts.find_one_and_update(
            {"_id": attempt_id, "attempt_count": {"$lt": max_attempts},
             "$or": [
                 {"state": "queued"},
                 {"state": "running", "lease_expires_at": {"$lte": now}},
             ]},
            {"$set": {"state": "running", "worker_id": worker_id,
                      "lease_expires_at": now + timedelta(seconds=lease_seconds),
                      "started_at": now, "updated_at": now},
             "$inc": {"attempt_count": 1}},
            return_document=True,
        )
        if result is None:
            raise MacDeploymentConflict("Attempt is not claimable, its lease is active, or retry limit was reached")
        return result

    async def heartbeat(
        self, *, attempt_id: str, worker_id: str, lease_seconds: int = 120,
    ) -> dict[str, Any]:
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 15 <= lease_seconds <= 900:
            raise MacDeploymentError("Worker lease must be between 15 and 900 seconds")
        now = datetime.now(timezone.utc)
        result = await self.attempts.find_one_and_update(
            {"_id": attempt_id, "state": "running", "worker_id": worker_id,
             "lease_expires_at": {"$gt": now}},
            {"$set": {"lease_expires_at": now + timedelta(seconds=lease_seconds),
                      "updated_at": now}},
            return_document=True,
        )
        if result is None:
            raise MacDeploymentConflict("Worker lease expired or is not owned by this worker")
        return result

    async def record_provider_deployment(
        self, *, attempt_id: str, worker_id: str, provider_deployment_id: str,
    ) -> dict[str, Any]:
        if not isinstance(provider_deployment_id, str) or not 1 <= len(provider_deployment_id) <= 200 or any(
            ord(char) < 32 for char in provider_deployment_id
        ):
            raise MacDeploymentError("Provider deployment identifier is invalid")
        now = datetime.now(timezone.utc)
        result = await self.attempts.find_one_and_update(
            {"_id": attempt_id, "state": "running", "worker_id": worker_id,
             "lease_expires_at": {"$gt": now},
             "$or": [
                 {"provider_deployment_id": None},
                 {"provider_deployment_id": provider_deployment_id},
             ]},
            {"$set": {"provider_deployment_id": provider_deployment_id,
                      "updated_at": now}},
            return_document=True,
        )
        if result is None:
            raise MacDeploymentConflict("Worker lease expired or provider deployment identity conflicts")
        return result

    async def finish(
        self, *, attempt_id: str, worker_id: str, verified: bool,
        provider_deployment_id: str | None, result_summary: str,
    ) -> dict[str, Any]:
        if not isinstance(verified, bool):
            raise MacDeploymentError("Verification result must be boolean")
        if provider_deployment_id is not None and (
            not isinstance(provider_deployment_id, str)
            or not 1 <= len(provider_deployment_id) <= 200
            or any(ord(char) < 32 for char in provider_deployment_id)
        ):
            raise MacDeploymentError("Provider deployment identifier is invalid")
        if not isinstance(result_summary, str) or not 1 <= len(result_summary.strip()) <= 500:
            raise MacDeploymentError("A bounded result summary is required")
        now = datetime.now(timezone.utc)
        state = "succeeded" if verified else "verification_failed"
        result = await self.attempts.find_one_and_update(
            {"_id": attempt_id, "state": "running", "worker_id": worker_id,
             "lease_expires_at": {"$gt": now}},
            {"$set": {
                "state": state, "lease_expires_at": None, "verified": verified,
                "provider_deployment_id": provider_deployment_id,
                "result_summary": result_summary.strip(),
                "finished_at": now, "updated_at": now,
            }},
            return_document=True,
        )
        if result is None:
            raise MacDeploymentConflict("Only the worker holding the running attempt may finish it")
        return result

    async def fail(
        self, *, attempt_id: str, worker_id: str, reason: str,
    ) -> dict[str, Any]:
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise MacDeploymentError("A bounded failure reason is required")
        now = datetime.now(timezone.utc)
        result = await self.attempts.find_one_and_update(
            {"_id": attempt_id, "state": "running", "worker_id": worker_id,
             "lease_expires_at": {"$gt": now}},
            {"$set": {"state": "failed", "lease_expires_at": None, "result_summary": reason.strip(),
                      "verified": False, "finished_at": now, "updated_at": now}},
            return_document=True,
        )
        if result is None:
            raise MacDeploymentConflict("Only the worker holding the running attempt may fail it")
        return result

    async def get(self, attempt_id: str) -> dict[str, Any]:
        record = await self.attempts.find_one({"_id": attempt_id})
        if record is None:
            raise MacDeploymentNotFound("Deployment attempt does not exist")
        return record
