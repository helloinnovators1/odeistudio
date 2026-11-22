"""Persisted, concurrency-safe MAD incident lifecycle.

Only aggregate alert metadata is stored. Tenant identifiers, prompts, artifacts,
command output, hostnames and credentials are deliberately excluded.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING

_INCIDENT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_ACTIONS = {"acknowledge", "assign", "resolve", "reopen"}


class MadIncidentConflict(ValueError):
    """The incident state or version changed before the requested transition."""


class MadIncidentNotFound(LookupError):
    """The requested incident does not exist."""


class MadIncidentValidationError(ValueError):
    """An incident or transition contains invalid input."""


class MongoMadIncidentStore:
    """Persist deduplicated alert incidents with compare-and-set transitions."""

    def __init__(self, collection: Any):
        self.collection = collection

    async def initialize(self) -> None:
        await self.collection.create_index([("status", ASCENDING), ("updated_at", DESCENDING)])
        await self.collection.create_index([("severity", ASCENDING), ("updated_at", DESCENDING)])

    async def record_alerts(self, alerts: list[dict[str, Any]]) -> None:
        """Upsert active alert observations; reopen a previously resolved incident."""
        now = datetime.now(timezone.utc)
        for alert in alerts:
            incident_id = alert.get("deduplication_key")
            if not isinstance(incident_id, str) or not _INCIDENT_ID.fullmatch(incident_id):
                raise MadIncidentValidationError("Alert deduplication key is invalid")
            severity = alert.get("severity")
            if severity not in {"info", "warning", "critical"}:
                raise MadIncidentValidationError("Alert severity is invalid")
            summary = alert.get("summary")
            runbook = alert.get("runbook")
            if not isinstance(summary, str) or not 1 <= len(summary) <= 500:
                raise MadIncidentValidationError("Alert summary is invalid")
            if not isinstance(runbook, str) or not runbook.startswith("docs/runbooks/") or len(runbook) > 256:
                raise MadIncidentValidationError("Alert runbook is invalid")

            existing = await self.collection.find_one({"_id": incident_id})
            if existing is None:
                document = {
                    "_id": incident_id,
                    "incident_id": incident_id,
                    "alert_id": alert.get("id", incident_id),
                    "severity": severity,
                    "summary": summary,
                    "runbook": runbook,
                    "status": "firing",
                    "assignee": None,
                    "version": 1,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "updated_at": now,
                    "history": [{"action": "opened", "actor": "system", "at": now, "version": 1}],
                }
                try:
                    await self.collection.insert_one(document)
                except Exception as exc:
                    # A concurrent observer may have inserted the same dedup key.
                    if type(exc).__name__ != "DuplicateKeyError":
                        raise
                continue

            if existing.get("status") == "resolved":
                await self.collection.update_one(
                    {"_id": incident_id, "version": existing.get("version"), "status": "resolved"},
                    {
                        "$set": {
                            "severity": severity, "summary": summary, "runbook": runbook,
                            "status": "firing", "assignee": None,
                            "last_seen_at": now, "updated_at": now,
                        },
                        "$inc": {"version": 1},
                        "$push": {"history": {"$each": [{
                            "action": "reopened", "actor": "system", "at": now,
                            "version": int(existing.get("version", 0)) + 1,
                        }], "$slice": -200}},
                    },
                )
            else:
                await self.collection.update_one(
                    {"_id": incident_id, "status": {"$ne": "resolved"}},
                    {"$set": {
                        "severity": severity, "summary": summary, "runbook": runbook,
                        "last_seen_at": now,
                    }},
                )

    async def list_incidents(self, *, include_resolved: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise MadIncidentValidationError("Incident page size is invalid")
        query = {} if include_resolved else {"status": {"$ne": "resolved"}}
        cursor = self.collection.find(query).sort("updated_at", DESCENDING).limit(limit)
        return await cursor.to_list(length=limit)

    async def transition(
        self, *, incident_id: str, action: str, actor: str,
        expected_version: int, assignee: str | None = None,
        session: Any | None = None,
    ) -> dict[str, Any]:
        if not isinstance(incident_id, str) or not _INCIDENT_ID.fullmatch(incident_id):
            raise MadIncidentValidationError("Incident ID is invalid")
        if action not in _ACTIONS:
            raise MadIncidentValidationError("Incident action is invalid")
        if not isinstance(actor, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}", actor):
            raise MadIncidentValidationError("Incident actor is invalid")
        if not isinstance(expected_version, int) or isinstance(expected_version, bool) or expected_version < 1:
            raise MadIncidentValidationError("Expected incident version is invalid")
        if action == "assign":
            if not isinstance(assignee, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}", assignee):
                raise MadIncidentValidationError("Assignee is invalid")
        elif assignee is not None:
            raise MadIncidentValidationError("Assignee is only valid for assignment")

        current = await self.collection.find_one({"_id": incident_id}, session=session)
        if current is None:
            raise MadIncidentNotFound("Incident does not exist")
        status = current.get("status")
        next_status = status
        updates: dict[str, Any] = {}
        if action == "acknowledge" and status == "firing":
            next_status = "acknowledged"
        elif action == "assign" and status in {"firing", "acknowledged"}:
            updates["assignee"] = assignee
        elif action == "resolve" and status in {"firing", "acknowledged"}:
            next_status = "resolved"
        elif action == "reopen" and status == "resolved":
            next_status = "firing"
            updates["assignee"] = None
        else:
            raise MadIncidentConflict("Incident transition is not valid from its current state")

        now = datetime.now(timezone.utc)
        updates.update({"status": next_status, "updated_at": now})
        new_version = expected_version + 1
        result = await self.collection.update_one(
            {"_id": incident_id, "version": expected_version, "status": status},
            {
                "$set": updates,
                "$inc": {"version": 1},
                "$push": {"history": {"$each": [{
                    "action": action, "actor": actor, "at": now, "version": new_version,
                    **({"assignee": assignee} if action == "assign" else {}),
                }], "$slice": -200}},
            },
            session=session,
        )
        if result.modified_count != 1:
            raise MadIncidentConflict("Incident changed; refresh before retrying")
        updated = await self.collection.find_one({"_id": incident_id}, session=session)
        if updated is None:
            raise MadIncidentNotFound("Incident disappeared after transition")
        return updated
