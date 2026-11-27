from __future__ import annotations

import os
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient
from fastapi import HTTPException

from odei_api.services.project_lifecycle import fence_project_write


@pytest.mark.asyncio
async def test_project_write_fence_updates_active_project_in_calling_transaction():
    projects = Mock()
    projects.update_one = AsyncMock(return_value=Mock(matched_count=1))
    session = object()

    await fence_project_write(
        projects, organization_id="org-a", project_id="project-a", session=session,
    )

    projects.update_one.assert_awaited_once_with(
        {"organization_id": "org-a", "project_id": "project-a", "status": "active"},
        {"$inc": {"lifecycle_write_seq": 1}},
        session=session,
    )


@pytest.mark.asyncio
async def test_project_write_fence_rejects_missing_or_deleting_project():
    projects = Mock()
    projects.update_one = AsyncMock(return_value=Mock(matched_count=0))

    with pytest.raises(HTTPException) as raised:
        await fence_project_write(
            projects, organization_id="org-a", project_id="project-a", session=object(),
        )

    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "PROJECT_LIFECYCLE_CLOSED"


@pytest.mark.asyncio
async def test_project_write_fence_requires_transaction_session():
    projects = Mock()
    projects.update_one = AsyncMock()

    with pytest.raises(ValueError):
        await fence_project_write(
            projects, organization_id="org-a", project_id="project-a", session=None,
        )

    projects.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_mongodb_tombstone_blocks_new_writes_but_allows_existing_worker_drain():
    uri = os.getenv("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI is not configured")
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000)
    database_name = f"odei_project_lifecycle_{uuid4().hex}"
    database = client[database_name]
    organization_id, project_id = "org-lifecycle", "project-lifecycle"
    try:
        topology = await client.admin.command("hello")
        assert topology.get("setName") or topology.get("msg") == "isdbgrid"
        await database["projects"].insert_one({
            "organization_id": organization_id,
            "project_id": project_id,
            "status": "active",
        })
        async with client.start_session() as session, await session.start_transaction():
            await fence_project_write(
                database["projects"], organization_id=organization_id,
                project_id=project_id, session=session,
            )
            await database["tasks"].insert_one(
                {"_id": "before-tombstone", "organization_id": organization_id,
                 "project_id": project_id}, session=session,
            )
        async with client.start_session() as session, await session.start_transaction():
            changed = await database["projects"].update_one(
                {"organization_id": organization_id, "project_id": project_id,
                 "status": "active"},
                {"$set": {"status": "deleting"}}, session=session,
            )
            assert changed.modified_count == 1
        with pytest.raises(HTTPException) as raised:
            async with client.start_session() as session, await session.start_transaction():
                await fence_project_write(
                    database["projects"], organization_id=organization_id,
                    project_id=project_id, session=session,
                )
                await database["tasks"].insert_one(
                    {"_id": "after-tombstone", "organization_id": organization_id,
                     "project_id": project_id}, session=session,
                )
        assert raised.value.status_code == 409
        assert await database["tasks"].count_documents({"_id": "after-tombstone"}) == 0
        async with client.start_session() as session, await session.start_transaction():
            await fence_project_write(
                database["projects"], organization_id=organization_id,
                project_id=project_id, session=session, allow_deleting=True,
            )
            await database["task_events"].insert_one(
                {"_id": "drain-event", "organization_id": organization_id,
                 "project_id": project_id}, session=session,
            )
        assert await database["task_events"].count_documents({"_id": "drain-event"}) == 1
    finally:
        await client.drop_database(database_name)
        await client.close()
