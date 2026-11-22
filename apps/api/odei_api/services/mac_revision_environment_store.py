"""Runtime MAC environment store backed by separately immutable revision documents.

Environment metadata contains only active/latest pointers. Revision configuration
and provenance live in a separately indexed collection. Lifecycle state changes
are guarded by Mongo transactions supplied by the API layer.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING

from odei_api.services.mac_environments import (
    MacEnvironmentConflict,
    MacEnvironmentError,
    MacEnvironmentNotFound,
    _validate_identity,
    validate_environment_config,
)


class MongoMacRevisionEnvironmentStore:
    """Environment metadata plus separately persisted, append-only revision history."""

    def __init__(self, environments: Any, revisions: Any):
        self.collection = environments
        self.revisions = revisions

    async def initialize(self) -> None:
        await self.collection.create_index(
            [("environment", ASCENDING)], unique=True,
            name="mac_environment_identity_unique",
        )
        await self.revisions.create_index(
            [("environment", ASCENDING), ("version", ASCENDING)],
            unique=True, name="mac_environment_version_unique",
        )
        await self.revisions.create_index(
            [("environment", ASCENDING), ("created_at", DESCENDING)],
            name="mac_environment_revision_history",
        )

    async def get(self, environment: str, *, session: Any | None = None) -> dict[str, Any]:
        if environment not in {"development", "staging", "production"}:
            raise MacEnvironmentError("Environment is invalid")
        record = await self.collection.find_one({"_id": environment}, session=session)
        if record is None:
            raise MacEnvironmentNotFound("Environment does not exist")
        cursor = self.revisions.find({"environment": environment}, session=session).sort("version", ASCENDING)
        versions = [item async for item in cursor]
        for item in versions:
            item.pop("_id", None)
            item.pop("environment", None)
        return {**record, "versions": versions}

    @staticmethod
    def _summary(value: str) -> str:
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 500:
            raise MacEnvironmentError("Change summary is required and must be at most 500 characters")
        return value.strip()

    @staticmethod
    def _revision(environment: str, version: int, revision: dict[str, Any]) -> dict[str, Any]:
        return {"_id": f"{environment}:{version}", "environment": environment, **revision}

    async def create_draft(self, *, environment: str, actor: str, config: Mapping[str, Any],
                           change_summary: str, session: Any | None = None) -> dict[str, Any]:
        _validate_identity(environment, actor)
        now = datetime.now(timezone.utc)
        revision = {
            "version": 1, "status": "draft", "config": validate_environment_config(config),
            "created_by": actor, "created_at": now, "change_summary": self._summary(change_summary),
            "approvals": [], "promoted_at": None,
        }
        try:
            await self.collection.insert_one({
                "_id": environment, "environment": environment, "active_version": 0,
                "latest_version": 1, "created_at": now, "updated_at": now,
            }, session=session)
            await self.revisions.insert_one(self._revision(environment, 1, revision), session=session)
        except Exception as exc:
            if type(exc).__name__ == "DuplicateKeyError":
                raise MacEnvironmentConflict("Environment already exists") from exc
            raise
        return {"environment": environment, **revision}

    async def create_revision(self, *, environment: str, expected_latest_version: int,
                              actor: str, config: Mapping[str, Any], change_summary: str,
                              session: Any | None = None) -> dict[str, Any]:
        _validate_identity(environment, actor)
        now = datetime.now(timezone.utc)
        version = expected_latest_version + 1
        revision = {
            "version": version, "status": "draft", "config": validate_environment_config(config),
            "created_by": actor, "created_at": now, "change_summary": self._summary(change_summary),
            "approvals": [], "promoted_at": None,
        }
        result = await self.collection.update_one(
            {"_id": environment, "latest_version": expected_latest_version},
            {"$set": {"latest_version": version, "updated_at": now}}, session=session,
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Environment changed; refresh before creating a revision")
        await self.revisions.insert_one(self._revision(environment, version, revision), session=session)
        return {"environment": environment, **revision}

    async def update_draft(self, *, environment: str, version: int, expected_latest_version: int,
                           actor: str, config: Mapping[str, Any], change_summary: str,
                           session: Any | None = None) -> dict[str, Any]:
        _validate_identity(environment, actor)
        if version != expected_latest_version:
            raise MacEnvironmentConflict("Draft version does not match expected latest version")
        now = datetime.now(timezone.utc)
        result = await self.revisions.update_one(
            {"environment": environment, "version": version, "status": "draft", "created_by": actor},
            {"$set": {"config": validate_environment_config(config),
                      "change_summary": self._summary(change_summary),
                      "updated_by": actor, "updated_at": now}}, session=session,
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Draft is missing, immutable, or stale")
        metadata = await self.collection.update_one(
            {"_id": environment, "latest_version": expected_latest_version},
            {"$set": {"updated_at": now}}, session=session,
        )
        if metadata.matched_count != 1:
            raise MacEnvironmentConflict("Environment changed; refresh before editing")
        return await self.get(environment, session=session)

    async def submit_for_approval(self, *, environment: str, version: int,
                                  expected_latest_version: int, actor: str,
                                  session: Any | None = None) -> dict[str, Any]:
        _validate_identity(environment, actor)
        now = datetime.now(timezone.utc)
        result = await self.revisions.update_one(
            {"environment": environment, "version": version, "status": "draft", "created_by": actor},
            {"$set": {"status": "pending_approval", "submitted_at": now}}, session=session,
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Only the draft author may submit the current draft")
        metadata = await self.collection.update_one(
            {"_id": environment, "latest_version": expected_latest_version},
            {"$set": {"updated_at": now}}, session=session,
        )
        if metadata.matched_count != 1:
            raise MacEnvironmentConflict("Environment changed; refresh before submission")
        return await self.get(environment, session=session)

    async def approve(self, *, environment: str, version: int, expected_latest_version: int,
                      actor: str, session: Any | None = None) -> dict[str, Any]:
        _validate_identity(environment, actor)
        record = await self.get(environment, session=session)
        revision = next((item for item in record["versions"] if item["version"] == version), None)
        if revision is None:
            raise MacEnvironmentNotFound("Revision does not exist")
        if revision["status"] != "pending_approval":
            raise MacEnvironmentConflict("Revision is not awaiting approval")
        if revision["created_by"] == actor:
            raise MacEnvironmentError("The author cannot approve their own change")
        now = datetime.now(timezone.utc)
        result = await self.revisions.update_one(
            {"environment": environment, "version": version, "status": "pending_approval",
             "created_by": {"$ne": actor}},
            {"$set": {"status": "approved", "approved_by": actor, "approved_at": now}},
            session=session,
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Revision changed or approval precondition failed")
        metadata = await self.collection.update_one(
            {"_id": environment, "latest_version": expected_latest_version},
            {"$set": {"updated_at": now}}, session=session,
        )
        if metadata.matched_count != 1:
            raise MacEnvironmentConflict("Environment changed; refresh before approval")
        return await self.get(environment, session=session)

    async def promote(self, *, environment: str, version: int, expected_active_version: int,
                      expected_latest_version: int, actor: str,
                      session: Any | None = None) -> dict[str, Any]:
        _validate_identity(environment, actor)
        now = datetime.now(timezone.utc)
        result = await self.revisions.update_one(
            {"environment": environment, "version": version, "status": "approved"},
            {"$set": {"status": "promoted", "promoted_by": actor, "promoted_at": now}},
            session=session,
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Promotion requires an approved revision")
        metadata = await self.collection.update_one(
            {"_id": environment, "active_version": expected_active_version,
             "latest_version": expected_latest_version},
            {"$set": {"active_version": version, "updated_at": now}}, session=session,
        )
        if metadata.modified_count != 1:
            raise MacEnvironmentConflict("Promotion requires the current active and latest versions")
        return await self.get(environment, session=session)

    async def create_rollback_draft(self, *, environment: str, target_version: int,
                                    expected_latest_version: int, actor: str,
                                    change_summary: str, session: Any | None = None) -> dict[str, Any]:
        _validate_identity(environment, actor)
        record = await self.get(environment, session=session)
        if record["latest_version"] != expected_latest_version:
            raise MacEnvironmentConflict("Environment has changed; refresh before rollback")
        target = next((item for item in record["versions"] if item["version"] == target_version), None)
        if target is None or target["status"] not in {"promoted", "approved"}:
            raise MacEnvironmentError("Rollback target must be a previously approved revision")
        now = datetime.now(timezone.utc)
        version = expected_latest_version + 1
        revision = {
            "version": version, "status": "draft", "config": deepcopy(target["config"]),
            "created_by": actor, "created_at": now,
            "change_summary": f"Rollback to revision {target_version}: {self._summary(change_summary)}",
            "rollback_of": target_version, "approvals": [], "promoted_at": None,
        }
        result = await self.collection.update_one(
            {"_id": environment, "latest_version": expected_latest_version},
            {"$set": {"latest_version": version, "updated_at": now}}, session=session,
        )
        if result.modified_count != 1:
            raise MacEnvironmentConflict("Environment changed while creating rollback draft")
        await self.revisions.insert_one(self._revision(environment, version, revision), session=session)
        return {"environment": environment, **revision}
