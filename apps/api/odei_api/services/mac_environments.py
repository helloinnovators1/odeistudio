"""Versioned MAC environment configuration with two-person approval.

Configuration is metadata-only: secret material must be stored by an external
secret manager and referenced by opaque secret:// identifiers. This store does
not perform deployments; callers must invoke a separately authorized deployer
only after a revision reaches the approved state.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING

_ENVIRONMENTS = frozenset({"development", "staging", "production"})
_ENV_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_ACTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_CONFIG_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_SECRET_KEY = re.compile(r"(?:secret|password|passwd|token|api[_-]?key|private[_-]?key|credential)", re.IGNORECASE)
_SECRET_REF = re.compile(r"^secret://[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")


class MacEnvironmentError(ValueError):
    """Invalid environment configuration or lifecycle operation."""


class MacEnvironmentNotFound(LookupError):
    """Environment or revision does not exist."""


class MacEnvironmentConflict(RuntimeError):
    """A compare-and-set precondition failed."""


def validate_environment_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Accept bounded JSON scalars; never persist secret material."""
    if not isinstance(config, Mapping) or not 1 <= len(config) <= 100:
        raise MacEnvironmentError("Configuration must contain 1 to 100 entries")
    result: dict[str, Any] = {}
    for key, value in config.items():
        if not isinstance(key, str) or not _CONFIG_KEY.fullmatch(key):
            raise MacEnvironmentError("Configuration key is invalid")
        if isinstance(value, str):
            if len(value) > 2048:
                raise MacEnvironmentError("Configuration value is too long")
            if _SECRET_KEY.search(key) and not _SECRET_REF.fullmatch(value):
                raise MacEnvironmentError("Secret values must be external secret:// references")
        elif (not isinstance(value, (bool, int, float))
              or isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**53
              or isinstance(value, float) and not math.isfinite(value)):
            raise MacEnvironmentError("Configuration values must be bounded JSON scalars")
        result[key] = value
    return result


def _validate_identity(environment: str, actor: str) -> None:
    if environment not in _ENVIRONMENTS or not _ENV_ID.fullmatch(environment.replace("_", "-")):
        raise MacEnvironmentError("Environment is invalid")
    if not isinstance(actor, str) or not _ACTOR.fullmatch(actor):
        raise MacEnvironmentError("Verified actor identity is invalid")


class MongoMacEnvironmentStore:
    """Atomic per-environment revision store; no update/delete of published history."""

    def __init__(self, collection: Any):
        self.collection = collection

    async def initialize(self) -> None:
        await self.collection.create_index(
            [("versions.version", ASCENDING)], name="mac_environment_revision_lookup"
        )

    async def get(self, environment: str) -> dict[str, Any]:
        if environment not in _ENVIRONMENTS:
            raise MacEnvironmentError("Environment is invalid")
        record = await self.collection.find_one({"_id": environment})
        if record is None:
            raise MacEnvironmentNotFound("Environment does not exist")
        return record

    async def create_draft(
        self, *, environment: str, actor: str, config: Mapping[str, Any],
        change_summary: str,
    ) -> dict[str, Any]:
        _validate_identity(environment, actor)
        if not isinstance(change_summary, str) or not 1 <= len(change_summary.strip()) <= 500:
            raise MacEnvironmentError("Change summary is required and must be at most 500 characters")
        now = datetime.now(timezone.utc)
        revision = {
            "version": 1, "status": "draft",
            "config": validate_environment_config(config),
            "created_by": actor, "created_at": now,
            "change_summary": change_summary.strip(),
            "approvals": [], "promoted_at": None,
        }
        try:
            await self.collection.insert_one({
                "_id": environment, "environment": environment,
                "active_version": 0, "latest_version": 1,
                "created_at": now, "updated_at": now,
                "versions": [revision],
            })
        except Exception as exc:
            if type(exc).__name__ == "DuplicateKeyError":
                raise MacEnvironmentConflict("Environment already exists") from exc
            raise
        return {"environment": environment, **revision}

    async def create_revision(
        self, *, environment: str, expected_latest_version: int,
        actor: str, config: Mapping[str, Any], change_summary: str,
    ) -> dict[str, Any]:
        """Append a new draft revision using a latest-version compare-and-set."""
        _validate_identity(environment, actor)
        if not isinstance(change_summary, str) or not 1 <= len(change_summary.strip()) <= 500:
            raise MacEnvironmentError("Change summary is required and must be at most 500 characters")
        safe_config = validate_environment_config(config)
        now = datetime.now(timezone.utc)
        new_version = expected_latest_version + 1
        revision = {
            "version": new_version, "status": "draft", "config": safe_config,
            "created_by": actor, "created_at": now,
            "change_summary": change_summary.strip(),
            "approvals": [], "promoted_at": None,
        }
        result = await self.collection.update_one(
            {"_id": environment, "latest_version": expected_latest_version},
            {"$set": {"latest_version": new_version, "updated_at": now},
             "$push": {"versions": revision}},
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Environment changed; refresh before creating a revision")
        return {"environment": environment, **revision}
    async def update_draft(
        self, *, environment: str, version: int, expected_latest_version: int,
        actor: str, config: Mapping[str, Any], change_summary: str,
    ) -> dict[str, Any]:
        _validate_identity(environment, actor)
        if version != expected_latest_version:
            raise MacEnvironmentConflict("Draft version does not match expected latest version")
        safe_config = validate_environment_config(config)
        if not isinstance(change_summary, str) or not 1 <= len(change_summary.strip()) <= 500:
            raise MacEnvironmentError("Change summary is required and must be at most 500 characters")
        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"_id": environment, "latest_version": expected_latest_version,
             "versions": {"$elemMatch": {"version": version, "status": "draft", "created_by": actor}}},
            {"$set": {
                "versions.$.config": safe_config,
                "versions.$.change_summary": change_summary.strip(),
                "versions.$.updated_by": actor,
                "versions.$.updated_at": now,
                "updated_at": now,
            }},
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Draft is missing, immutable, or stale")
        return await self.get(environment)

    async def submit_for_approval(
        self, *, environment: str, version: int, expected_latest_version: int,
        actor: str,
    ) -> dict[str, Any]:
        _validate_identity(environment, actor)
        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"_id": environment, "latest_version": expected_latest_version,
             "versions": {"$elemMatch": {"version": version, "status": "draft", "created_by": actor}}},
            {"$set": {"versions.$.status": "pending_approval",
                      "versions.$.submitted_at": now, "updated_at": now}},
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Only the draft author may submit the current draft")
        return await self.get(environment)

    async def approve(
        self, *, environment: str, version: int, expected_latest_version: int,
        actor: str,
    ) -> dict[str, Any]:
        _validate_identity(environment, actor)
        record = await self.get(environment)
        revision = next((item for item in record["versions"] if item["version"] == version), None)
        if revision is None:
            raise MacEnvironmentNotFound("Revision does not exist")
        if revision["status"] != "pending_approval":
            raise MacEnvironmentConflict("Revision is not awaiting approval")
        if revision["created_by"] == actor:
            raise MacEnvironmentError("The author cannot approve their own change")
        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"_id": environment, "latest_version": expected_latest_version,
             "versions": {"$elemMatch": {"version": version, "status": "pending_approval",
                                         "created_by": {"$ne": actor}}}},
            {"$set": {"versions.$.status": "approved",
                      "versions.$.approved_by": actor,
                      "versions.$.approved_at": now, "updated_at": now}},
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Revision changed or approval precondition failed")
        return await self.get(environment)

    async def promote(
        self, *, environment: str, version: int, expected_active_version: int,
        expected_latest_version: int, actor: str,
    ) -> dict[str, Any]:
        _validate_identity(environment, actor)
        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"_id": environment, "active_version": expected_active_version,
             "latest_version": expected_latest_version,
             "versions": {"$elemMatch": {"version": version, "status": "approved"}}},
            {"$set": {"active_version": version,
                      "versions.$.status": "promoted",
                      "versions.$.promoted_by": actor,
                      "versions.$.promoted_at": now,
                      "updated_at": now}},
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Promotion requires an approved revision and current active version")
        return await self.get(environment)

    async def create_rollback_draft(
        self, *, environment: str, target_version: int,
        expected_latest_version: int, actor: str, change_summary: str,
    ) -> dict[str, Any]:
        _validate_identity(environment, actor)
        record = await self.get(environment)
        if record["latest_version"] != expected_latest_version:
            raise MacEnvironmentConflict("Environment has changed; refresh before rollback")
        target = next((item for item in record["versions"] if item["version"] == target_version), None)
        if target is None or target["status"] not in {"promoted", "approved"}:
            raise MacEnvironmentError("Rollback target must be a previously approved revision")
        if not isinstance(change_summary, str) or not 1 <= len(change_summary.strip()) <= 500:
            raise MacEnvironmentError("Rollback reason is required")
        new_version = expected_latest_version + 1
        now = datetime.now(timezone.utc)
        revision = {
            "version": new_version, "status": "draft",
            "config": deepcopy(target["config"]),
            "created_by": actor, "created_at": now,
            "change_summary": f"Rollback to revision {target_version}: {change_summary.strip()}",
            "rollback_of": target_version, "approvals": [], "promoted_at": None,
        }
        result = await self.collection.update_one(
            {"_id": environment, "latest_version": expected_latest_version},
            {"$set": {"latest_version": new_version, "updated_at": now},
             "$push": {"versions": revision}},
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Environment changed while creating rollback draft")
        return {"environment": environment, **revision}
