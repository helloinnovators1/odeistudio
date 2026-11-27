"""Real MongoDB tests for durable NEXUS conversations."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from odei_api.services.conversation_store import MongoConversationStore


@pytest.mark.asyncio
async def test_conversation_store_enforces_owner_scope_versions_and_limits_on_mongodb():
    uri = os.getenv("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI is not configured")

    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000)
    database_name = f"odei_conversation_test_{uuid4().hex}"
    database = client[database_name]
    store = MongoConversationStore(
        database["nexus_conversations"], client, database["projects"],
    )
    try:
        topology = await client.admin.command("hello")
        assert topology.get("setName") or topology.get("msg") == "isdbgrid"
        await database["projects"].insert_one({
            "organization_id": "org-integration",
            "project_id": "project-integration",
            "status": "active",
        })
        await store.initialize()
        created = await store.create(
            organization_id="org-integration",
            project_id="project-integration",
            owner_issuer="https://identity.example.test/",
            owner_subject="integration-user",
            title="Persistent conversation",
        )
        scope = {
            "organization_id": "org-integration",
            "project_id": "project-integration",
            "owner_issuer": "https://identity.example.test/",
            "owner_subject": "integration-user",
            "conversation_id": created["conversation_id"],
        }
        user_turn = await store.append(
            **scope, role="user", content="Inspect the approved project.",
            expected_version=0,
        )
        assert user_turn is not None
        assert user_turn["version"] == 1
        assert await store.append(
            **scope, role="assistant", content="I can inspect the selected project.",
            expected_version=0,
        ) is None
        assistant_turn = await store.append(
            **scope, role="assistant", content="I can inspect the selected project.",
            expected_version=1,
        )
        assert assistant_turn is not None
        assert assistant_turn["version"] == 2
        assert len(assistant_turn["messages"]) == 2

        assert await store.get_for_owner(
            **(scope | {"owner_subject": "different-user"})
        ) is None
        listed = await store.list_for_owner(
            organization_id="org-integration",
            project_id="project-integration",
            owner_issuer="https://identity.example.test/",
            owner_subject="integration-user",
        )
        assert len(listed) == 1
        assert listed[0]["version"] == 2
        assert await store.delete_for_owner(**scope) is True
        assert await store.get_for_owner(**scope) is None
    finally:
        await client.drop_database(database_name)
        await client.close()
