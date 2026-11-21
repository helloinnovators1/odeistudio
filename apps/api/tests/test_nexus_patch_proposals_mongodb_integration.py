"""Real MongoDB integration tests for persistent patch proposal decisions."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from odei_api.services.nexus_patch_proposals import MongoPatchProposalStore


@pytest.mark.asyncio
async def test_patch_proposal_store_persists_owner_decisions_with_optimistic_versions():
    uri = os.getenv("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI is not configured")

    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000)
    database_name = f"odei_patch_proposal_test_{uuid4().hex}"
    database = client[database_name]
    store = MongoPatchProposalStore(database["nexus_patch_proposals"])
    try:
        topology = await client.admin.command("hello")
        assert topology.get("setName") or topology.get("msg") == "isdbgrid"
        await store.initialize()
        created = await store.create(
            organization_id="org-integration",
            project_id="project-integration",
            owner_issuer="https://identity.example.test/",
            owner_subject="proposal-author",
            title="Integration proposal",
            files=[{
                "path": "main.py",
                "operation": "update",
                "base_sha256": "a" * 64,
                "result_sha256": "b" * 64,
                "content": "print('approved')\n",
                "unified_diff": "-print('old')\n+print('approved')\n",
            }],
        )
        assert created["status"] == "pending"
        assert created["version"] == 0
        loaded = await store.get(
            organization_id="org-integration",
            project_id="project-integration",
            proposal_id=created["proposal_id"],
        )
        assert loaded is not None
        assert loaded["files"][0]["content"] == "print('approved')\n"
        listed = await store.list_for_project(
            organization_id="org-integration",
            project_id="project-integration",
            owner_issuer="https://identity.example.test/",
            owner_subject="proposal-author",
        )
        assert len(listed) == 1

        approved = await store.decide(
            organization_id="org-integration",
            project_id="project-integration",
            proposal_id=created["proposal_id"],
            expected_version=0,
            decision="approved",
            actor_issuer="https://identity.example.test/",
            actor_subject="project-owner",
        )
        assert approved is not None
        assert approved["status"] == "approved"
        assert approved["version"] == 1
        assert await store.decide(
            organization_id="org-integration",
            project_id="project-integration",
            proposal_id=created["proposal_id"],
            expected_version=0,
            decision="rejected",
            actor_issuer="https://identity.example.test/",
            actor_subject="project-owner",
        ) is None
    finally:
        await client.drop_database(database_name)
        await client.close()
