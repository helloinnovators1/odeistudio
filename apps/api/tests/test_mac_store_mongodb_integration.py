"""Real MongoDB replica-set tests for MAC mutation/audit atomicity."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pymongo import AsyncMongoClient

from odei_api.security.auth import Principal
from odei_api.services.audit_store import MongoAuditEventStore
from odei_api.services.mac_environment_api import _mutate_with_audit
from odei_api.services.mac_environments import MongoMacEnvironmentStore


@pytest.mark.asyncio
async def test_mac_mutation_and_success_audit_commit_or_rollback_together():
    uri = os.getenv("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI is not configured")

    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000)
    database_name = f"odei_mac_transaction_test_{uuid4().hex}"
    database = client[database_name]
    store = MongoMacEnvironmentStore(database["mac_environments"])
    audit = MongoAuditEventStore(database["audit_events"])
    request = SimpleNamespace(app=SimpleNamespace(
        state=SimpleNamespace(mongo_database=database)
    ))
    principal = Principal(
        subject="mac-integration-operator",
        issuer="https://identity.example.test/",
    )

    class FailingAuditStore:
        async def append(self, **_kwargs):
            raise RuntimeError("simulated MAC audit failure")

    try:
        topology = await client.admin.command("hello")
        assert topology.get("setName") or topology.get("msg") == "isdbgrid"
        await store.initialize()
        await audit.initialize()

        with pytest.raises(HTTPException) as failure:
            await _mutate_with_audit(
                request, store, FailingAuditStore(), principal,
                "mac.environment.draft.create", "staging", "create_draft",
                environment="staging", actor="oidc-mac-integration",
                config={"replicas": 2}, change_summary="Atomic failure test",
            )
        assert failure.value.status_code == 503
        assert await database["mac_environments"].count_documents({}) == 0
        assert await database["audit_events"].count_documents({}) == 0

        revision = await _mutate_with_audit(
            request, store, audit, principal,
            "mac.environment.draft.create", "staging", "create_draft",
            environment="staging", actor="oidc-mac-integration",
            config={"replicas": 2}, change_summary="Atomic success test",
        )
        assert revision["version"] == 1
        assert await database["mac_environments"].count_documents({"_id": "staging"}) == 1
        assert await database["audit_events"].count_documents({
            "target_type": "mac_environment",
            "target_id": "staging",
            "action": "mac.environment.draft.create",
            "outcome": "success",
        }) == 1
    finally:
        await client.drop_database(database_name)
        await client.close()



@pytest.mark.asyncio
async def test_mac_deployment_attempt_idempotency_claim_and_verification_on_mongodb():
    uri = os.getenv("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI is not configured")

    from odei_api.services.mac_deployments import MongoMacDeploymentStore

    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000)
    database_name = f"odei_mac_deployment_test_{uuid4().hex}"
    database = client[database_name]
    environments = MongoMacEnvironmentStore(database["mac_environments"])
    deployments = MongoMacDeploymentStore(
        database["mac_deployment_attempts"], environments
    )
    try:
        topology = await client.admin.command("hello")
        assert topology.get("setName") or topology.get("msg") == "isdbgrid"
        await environments.initialize()
        await deployments.initialize()
        await environments.create_draft(
            environment="staging", actor="oidc-author",
            config={"replicas": 2}, change_summary="Deployment integration setup",
        )
        await environments.submit_for_approval(
            environment="staging", version=1, expected_latest_version=1,
            actor="oidc-author",
        )
        await environments.approve(
            environment="staging", version=1, expected_latest_version=1,
            actor="oidc-reviewer",
        )

        request = {
            "environment": "staging", "version": 1, "provider": "aws",
            "idempotency_key": "integration-request-123456",
            "actor": "oidc-deployer",
        }
        first = await deployments.create_attempt(**request)
        repeated = await deployments.create_attempt(**request)
        assert repeated["_id"] == first["_id"]
        assert await database["mac_deployment_attempts"].count_documents({}) == 1

        running = await deployments.claim(
            attempt_id=first["_id"], worker_id="integration-worker",
        )
        assert running["state"] == "running"
        await deployments.record_provider_deployment(
            attempt_id=first["_id"], worker_id="integration-worker",
            provider_deployment_id="provider-deploy-1",
        )
        succeeded = await deployments.finish(
            attempt_id=first["_id"], worker_id="integration-worker",
            verified=True, provider_deployment_id="provider-deploy-1",
            result_summary="Provider health verification passed",
        )
        assert succeeded["state"] == "succeeded"
        assert succeeded["verified"] is True
    finally:
        await client.drop_database(database_name)
        await client.close()



@pytest.mark.asyncio
async def test_mac_deployment_lease_reclaim_fences_stale_worker_on_mongodb():
    uri = os.getenv("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI is not configured")

    from datetime import datetime, timedelta, timezone

    from odei_api.services.mac_deployments import (
        MacDeploymentConflict,
        MongoMacDeploymentStore,
    )

    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000)
    database_name = f"odei_mac_lease_test_{uuid4().hex}"
    database = client[database_name]
    environments = MongoMacEnvironmentStore(database["mac_environments"])
    deployments = MongoMacDeploymentStore(
        database["mac_deployment_attempts"], environments
    )
    try:
        topology = await client.admin.command("hello")
        assert topology.get("setName") or topology.get("msg") == "isdbgrid"
        await environments.initialize()
        await deployments.initialize()
        await environments.create_draft(
            environment="staging", actor="oidc-author",
            config={"replicas": 2}, change_summary="Lease integration setup",
        )
        await environments.submit_for_approval(
            environment="staging", version=1, expected_latest_version=1,
            actor="oidc-author",
        )
        await environments.approve(
            environment="staging", version=1, expected_latest_version=1,
            actor="oidc-reviewer",
        )
        attempt = await deployments.create_attempt(
            environment="staging", version=1, provider="aws",
            idempotency_key="lease-integration-12345", actor="oidc-deployer",
        )
        first = await deployments.claim_next(
            worker_id="worker-before-crash",
        )
        assert first["attempt_count"] == 1
        await database["mac_deployment_attempts"].update_one(
            {"_id": attempt["_id"]},
            {"$set": {"lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
        )
        second = await deployments.claim_next(
            worker_id="worker-after-crash",
        )
        assert second["attempt_count"] == 2
        await deployments.record_provider_deployment(
            attempt_id=attempt["_id"], worker_id="worker-after-crash",
            provider_deployment_id="provider-deploy-recovered",
        )
        with pytest.raises(MacDeploymentConflict):
            await deployments.finish(
                attempt_id=attempt["_id"], worker_id="worker-before-crash",
                verified=True, provider_deployment_id="stale-provider-id",
                result_summary="Stale worker must be fenced",
            )
        completed = await deployments.finish(
            attempt_id=attempt["_id"], worker_id="worker-after-crash",
            verified=True, provider_deployment_id="provider-deploy-recovered",
            result_summary="Recovered worker verified deployment",
        )
        assert completed["state"] == "succeeded"
    finally:
        await client.drop_database(database_name)
        await client.close()
