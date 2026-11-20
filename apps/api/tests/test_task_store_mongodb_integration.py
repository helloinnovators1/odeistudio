"""Real MongoDB replica-set transaction tests.

Set MONGODB_TEST_URI to a disposable replica-set URI to enable these tests.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from odei_api.services.audit_store import MongoAuditEventStore
from odei_api.services.task_store import MongoTaskStore
from odei_api.services.tasks import TaskRecord, TaskStatus


@pytest.mark.asyncio
async def test_task_lifecycle_and_audit_share_real_mongodb_transaction():
    uri = os.getenv("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI is not configured")

    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000)
    database_name = f"odei_transaction_test_{uuid4().hex}"
    database = client[database_name]
    audit_store = MongoAuditEventStore(database["audit_events"])
    task_store = MongoTaskStore(
        database["tasks"],
        database["task_events"],
        client,
        audit_store=audit_store,
    )
    task_id = f"task-{uuid4().hex}"
    base_audit_event = {
        "organization_id": "org-integration",
        "actor_issuer": "https://identity.example.test/",
        "actor_subject": "integration-user",
        "target_type": "nexus_task",
        "target_id": task_id,
        "outcome": "success",
        "request_id": f"req-{uuid4().hex}",
    }

    try:
        topology = await client.admin.command("hello")
        assert topology.get("setName") or topology.get("msg") == "isdbgrid"

        await audit_store.initialize()
        await task_store.initialize()
        task = TaskRecord(
            id=task_id,
            organization_id="org-integration",
            project_id="project-integration",
            owner_id="integration-user",
            goal="Verify atomic task and audit persistence",
        )
        created = await task_store.create_planned(
            task,
            plan="Create, approve, verify rollback",
            audit_event=base_audit_event | {
                "action": "nexus.task.create",
                "metadata": {"source": "replica-set-integration"},
            },
        )
        assert created.status is TaskStatus.AWAITING_APPROVAL
        assert await database["tasks"].count_documents({"_id": task_id}) == 1
        assert await database["task_events"].count_documents({"task_id": task_id}) == 4
        assert await database["audit_events"].count_documents({
            "target_id": task_id, "action": "nexus.task.create",
        }) == 1

        class FailingAuditStore:
            async def append(self, **_kwargs):
                raise RuntimeError("simulated audit write failure")

        task_store._audit_store = FailingAuditStore()
        with pytest.raises(RuntimeError, match="simulated audit write failure"):
            await task_store.transition(
                organization_id="org-integration",
                task_id=task_id,
                next_status=TaskStatus.APPROVED,
                expected_version=3,
                actor_id="integration-user",
                audit_event=base_audit_event | {
                    "action": "nexus.task.approve",
                    "request_id": f"req-{uuid4().hex}",
                    "metadata": {"version": 4},
                },
            )

        unchanged = await task_store.get(
            organization_id="org-integration", task_id=task_id
        )
        assert unchanged is not None
        assert unchanged.status is TaskStatus.AWAITING_APPROVAL
        assert unchanged.version == 3
        assert await database["task_events"].count_documents({"task_id": task_id}) == 4
        assert await database["audit_events"].count_documents({"target_id": task_id}) == 1

        task_store._audit_store = audit_store
        approved = await task_store.transition(
            organization_id="org-integration",
            task_id=task_id,
            next_status=TaskStatus.APPROVED,
            expected_version=3,
            actor_id="integration-user",
            audit_event=base_audit_event | {
                "action": "nexus.task.approve",
                "request_id": f"req-{uuid4().hex}",
                "metadata": {"version": 4},
            },
        )
        assert approved.status is TaskStatus.APPROVED
        assert approved.version == 4
        assert await database["task_events"].count_documents({"task_id": task_id}) == 5
        assert await database["audit_events"].count_documents({"target_id": task_id}) == 2
    finally:
        await client.drop_database(database_name)
        await client.close()
