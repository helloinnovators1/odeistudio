"""Tenant-scoped MongoDB task and append-only event persistence.

Task state and its corresponding event are committed in one MongoDB transaction.
The deployment must use a replica set or sharded cluster that supports transactions.
"""
from __future__ import annotations

from collections.abc import Mapping
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
    def __init__(self, collection: Any, events_collection: Any, client: Any, audit_store: Any | None = None):
        self._collection = collection
        self._events = events_collection
        self._client = client
        self._audit_store = audit_store

    async def _append_audit_in_transaction(
        self, audit_event: Mapping[str, Any] | None, session: Any
    ) -> None:
        if audit_event is None:
            return
        if self._audit_store is None:
            raise RuntimeError("Audit store is required for transactional task actions")
        await self._audit_store.append(**dict(audit_event), session=session)

    async def initialize(self) -> None:
        await self._collection.create_index(
            [("organization_id", 1), ("_id", 1)], unique=True
        )
        await self._collection.create_index(
            [("organization_id", 1), ("project_id", 1), ("created_at", -1)]
        )
        await self._events.create_index(
            [("organization_id", 1), ("task_id", 1), ("version", 1)], unique=True
        )
        await self._events.create_index(
            [("organization_id", 1), ("project_id", 1), ("occurred_at", -1)]
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
        }
        event = {
            "event_id": str(uuid4()),
            "organization_id": task.organization_id,
            "project_id": task.project_id,
            "task_id": task.id,
            "actor_id": task.owner_id,
            "type": "task.created",
            "version": task.version,
            "status": task.status.value,
            "occurred_at": now,
        }
        async with self._client.start_session() as session, await session.start_transaction():
            await self._collection.insert_one(document, session=session)
            await self._events.insert_one(event, session=session)
            await self._append_audit_in_transaction(audit_event, session)
        return self._to_record(document)

    async def create_planned(
        self, task: TaskRecord, *, plan: str,
        audit_event: Mapping[str, Any] | None = None,
    ) -> TaskRecord:
        """Atomically persist an approval-ready task and ordered lifecycle events."""
        if task.status is not TaskStatus.CREATED or task.version != 0:
            raise ValueError("A planned task must start in the created state at version zero")
        if not isinstance(plan, str) or not plan.strip():
            raise ValueError("A non-empty plan is required")
        planned = task
        event_rows = [{
            "event_id": str(uuid4()), "organization_id": task.organization_id,
            "project_id": task.project_id, "task_id": task.id,
            "actor_id": task.owner_id, "type": "task.created", "version": 0,
            "status": TaskStatus.CREATED.value, "occurred_at": datetime.now(timezone.utc),
        }]
        for next_status in (
            TaskStatus.CONTEXT_GATHERING, TaskStatus.PLANNING, TaskStatus.AWAITING_APPROVAL,
        ):
            updated = transition_task(
                planned, next_status, expected_version=planned.version,
                plan=plan if next_status is TaskStatus.AWAITING_APPROVAL else None,
            )
            event_rows.append({
                "event_id": str(uuid4()), "organization_id": task.organization_id,
                "project_id": task.project_id, "task_id": task.id,
                "actor_id": task.owner_id,
                "type": "task.approval.requested" if next_status is TaskStatus.AWAITING_APPROVAL
                else "task.status_changed",
                "from_status": planned.status.value, "to_status": updated.status.value,
                "version": updated.version,
                "occurred_at": updated.updated_at or datetime.now(timezone.utc),
            })
            planned = updated
        document = {
            "_id": planned.id, "organization_id": planned.organization_id,
            "project_id": planned.project_id, "owner_id": planned.owner_id,
            "goal": planned.goal, "status": planned.status.value, "plan": planned.plan,
            "version": planned.version, "created_at": planned.created_at,
            "updated_at": planned.updated_at,
        }
        async with self._client.start_session() as session, await session.start_transaction():
            await self._collection.insert_one(document, session=session)
            for event in event_rows:
                await self._events.insert_one(event, session=session)
            await self._append_audit_in_transaction(audit_event, session)
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
        actor_id: str | None = None,
        audit_event: Mapping[str, Any] | None = None,
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
            "organization_id": organization_id,
            "project_id": current.project_id,
            "task_id": task_id,
            "actor_id": actor_id or current.owner_id,
            "type": "task.status_changed",
            "from_status": current.status.value,
            "to_status": updated.status.value,
            "version": updated.version,
            "occurred_at": occurred_at,
        }
        async with self._client.start_session() as session, await session.start_transaction():
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
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )
            if document is None:
                raise InvalidTaskTransition(
                    "Task changed concurrently; reload before retrying"
                )
            await self._events.insert_one(event, session=session)
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
