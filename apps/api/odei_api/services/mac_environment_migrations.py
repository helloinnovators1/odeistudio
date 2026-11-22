"""Safe, repeatable backfill of legacy embedded MAC revisions.

This migration intentionally copies and verifies history without deleting the
legacy embedded array. The application cutover to revision-collection reads and
writes is a separate deployment step; this module never silently changes it.
"""
from __future__ import annotations

from typing import Any

from bson.json_util import CANONICAL_JSON_OPTIONS, dumps

from pymongo import ASCENDING


class MacRevisionMigrationConflict(RuntimeError):
    """A target revision exists but differs from its legacy source."""


def _canonical(value: Any) -> str:
    """Compare BSON-compatible values independent of mapping key order."""
    return dumps(value, json_options=CANONICAL_JSON_OPTIONS, sort_keys=True, separators=(",", ":"))


async def initialize_mac_revision_collection(collection: Any) -> None:
    """Create the unique immutable revision identity and history lookup indexes."""
    await collection.create_index(
        [("environment", ASCENDING), ("version", ASCENDING)],
        unique=True,
        name="mac_environment_version_unique",
    )
    await collection.create_index(
        [("environment", ASCENDING), ("created_at", ASCENDING)],
        name="mac_environment_revision_history",
    )


async def backfill_mac_environment_revisions(
    environments: Any,
    revisions: Any,
    *,
    session: Any,
    dry_run: bool = False,
) -> dict[str, int]:
    """Copy every embedded revision in one caller-owned Mongo transaction.

    Deterministic IDs and exact content comparison make retries idempotent.
    Existing divergent records fail closed; no source or target is overwritten.
    """
    copied = 0
    already_present = 0
    cursor = environments.find({}, session=session)
    async for environment in cursor:
        environment_name = environment.get("environment") or environment.get("_id")
        if environment_name not in {"development", "staging", "production"}:
            raise MacRevisionMigrationConflict("Legacy environment identity is invalid")
        versions = environment.get("versions", [])
        if not isinstance(versions, list):
            raise MacRevisionMigrationConflict("Legacy revision history is malformed")
        seen: set[int] = set()
        for revision in versions:
            version = revision.get("version") if isinstance(revision, dict) else None
            if isinstance(version, bool) or not isinstance(version, int) or version < 1 or version in seen:
                raise MacRevisionMigrationConflict("Legacy revision sequence is invalid")
            seen.add(version)
            if "_id" in revision or "environment" in revision:
                raise MacRevisionMigrationConflict(
                    "Legacy revision contains reserved identity fields"
                )
            document = {
                **revision,
                "_id": f"{environment_name}:{version}",
                "environment": environment_name,
            }
            existing = await revisions.find_one(
                {"_id": document["_id"]}, session=session
            )
            if existing is not None:
                if _canonical(existing) != _canonical(document):
                    raise MacRevisionMigrationConflict(
                        f"Revision {environment_name}:{version} differs from legacy history"
                    )
                already_present += 1
                continue
            if not dry_run:
                await revisions.insert_one(document, session=session)
            copied += 1
        latest = environment.get("latest_version", 0)
        if isinstance(latest, bool) or not isinstance(latest, int) or latest < 0:
            raise MacRevisionMigrationConflict("Legacy latest-version pointer is invalid")
        if seen != set(range(1, latest + 1)):
            raise MacRevisionMigrationConflict(
                f"Environment {environment_name} revision sequence is incomplete"
            )
    return {"copied": copied, "already_present": already_present}
