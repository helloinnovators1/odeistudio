"""Tenant-scoped MongoDB persistence for NEXUS tasks.

Every read and mutation includes organization_id in its query. State updates and
their audit event are written atomically into the same task document.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument

from odei_api.services.tasks import (
    InvalidTaskTransition,
    TaskRecord,
    TaskStatus,
    transition_task,
)


class MongoTaskStore:
    def __init__(self, collection: Any):
        self._collection = collection

    async def initialize(self) -> None:
        await self._collection.create_index(
            [("organization_id", 1), ("_id", 1)], unique=True
        )
        await self._collection.create_index(
            [("organization_id", 1), ("project_id", 1), ("created_at", -1)]
        )

    async def create(self, task: TaskRecord) -> TaskRecord:
        now = datetime.now(timezone.utc)
        document = {
            "_id": task.id,
            "organization_id": task.organization_id,
            "project_id": task.project_id,
            "owner_id": task.owner_id,
            "goal": task.goal,
            "status": task.status.value,
            "plan": task.plan,
            "version": task.version,
            "created_at": now,
            "updated_at": now,
            "events": [{
                "event_id": str(uuid4()),
                "type": "task.created",
                "version": task.version,
                "status": task.status.value,
                "occurred_at": now,
            }],
        }
        await self._collection.insert_one(document)
        return self._to_record(document)

    async def get(self, *, organization_id: str, task_id: str) -> TaskRecord | None:
        if not organization_id.strip() or not task_id.strip():
            raise ValueError("organization_id and task_id are required")
        document = await self._collection.find_one({
            "_id": task_id,
            "organization_id": organization_id,
        })
        return self._to_record(document) if document else None

    async def transition(
        self,
        *,
        organization_id: str,
        task_id: str,
        next_status: TaskStatus,
        expected_version: int,
        plan: str | None = None,
    ) -> TaskRecord:
        current = await self.get(organization_id=organization_id, task_id=task_id)
        if current is None:
            raise KeyError("Task not found")
        updated = transition_task(
            current, next_status, expected_version=expected_version, plan=plan
        )
        occurred_at = updated.updated_at or datetime.now(timezone.utc)
        event = {
            "event_id": str(uuid4()),
            "type": "task.status_changed",
            "from_status": current.status.value,
            "to_status": updated.status.value,
            "version": updated.version,
            "occurred_at": occurred_at,
        }
        document = await self._collection.find_one_and_update(
            {
                "_id": task_id,
                "organization_id": organization_id,
                "version": expected_version,
                "status": current.status.value,
            },
            {
                "$set": {
                    "status": updated.status.value,
                    "plan": updated.plan,
                    "updated_at": occurred_at,
                },
                "$inc": {"version": 1},
                "$push": {"events": event},
            },
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            raise InvalidTaskTransition("Task changed concurrently; reload before retrying")
        return self._to_record(document)

    @staticmethod
    def _to_record(document: dict[str, Any]) -> TaskRecord:
        return TaskRecord(
            id=document["_id"],
            organization_id=document["organization_id"],
            project_id=document["project_id"],
            owner_id=document["owner_id"],
            goal=document["goal"],
            status=TaskStatus(document["status"]),
            plan=document.get("plan"),
            version=document.get("version", 0),
            created_at=document.get("created_at"),
            updated_at=document.get("updated_at"),
        )
