"""Real replica-set verification for atomic MAD incident/audit transitions."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from odei_api.main import (
    _record_mad_alerts_with_audit,
    _transition_mad_incident_with_audit,
)
from odei_api.security.auth import Principal
from odei_api.services.audit_store import MongoAuditEventStore
from odei_api.services.mad_incidents import MongoMadIncidentStore


class FailingAuditStore:
    async def append(self, **_event):
        raise RuntimeError("simulated audit write failure")


@pytest.mark.asyncio
async def test_mad_incident_transition_and_success_audit_are_atomic():
    uri = os.getenv("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI is not configured")
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000)
    database_name = "madtx_" + uuid4().hex
    database = client[database_name]
    incidents = MongoMadIncidentStore(database["mad_incidents"])
    audit = MongoAuditEventStore(database["audit_events"])
    incident_id = "mad-atomic-" + uuid4().hex[:12]
    principal = Principal(
        subject="mad-operator",
        issuer="https://identity.example.test/",
        scopes=frozenset({"mad:incident:manage"}),
    )
    try:
        topology = await client.admin.command("hello")
        assert topology.get("setName") or topology.get("msg") == "isdbgrid"
        await incidents.initialize()
        await audit.initialize()
        await incidents.record_alerts([{
            "id": "mad.integration.atomicity",
            "deduplication_key": incident_id,
            "severity": "warning",
            "summary": "Integration incident for atomic audit verification.",
            "runbook": "docs/runbooks/MAD_EXECUTION_WORKERS.md",
        }])

        with pytest.raises(RuntimeError, match="simulated audit write failure"):
            await _transition_mad_incident_with_audit(
                mongo_client=client,
                incident_store=incidents,
                audit_store=FailingAuditStore(),
                incident_id=incident_id,
                action="acknowledge",
                assignee=None,
                expected_version=1,
                principal=principal,
            )
        unchanged = await database["mad_incidents"].find_one({"_id": incident_id})
        assert unchanged["status"] == "firing"
        assert unchanged["version"] == 1
        assert await database["audit_events"].count_documents(
            {"target_id": incident_id}
        ) == 0

        changed = await _transition_mad_incident_with_audit(
            mongo_client=client,
            incident_store=incidents,
            audit_store=audit,
            incident_id=incident_id,
            action="acknowledge",
            assignee=None,
            expected_version=1,
            principal=principal,
        )
        assert changed["status"] == "acknowledged"
        assert changed["version"] == 2
        event = await database["audit_events"].find_one({"target_id": incident_id})
        assert event is not None
        assert event["action"] == "mad.incident.acknowledge"
        assert event["outcome"] == "success"
        assert event["metadata"] == {"version": 2, "status": "acknowledged"}
    finally:
        await client.drop_database(database_name)
        await client.close()


@pytest.mark.asyncio
async def test_mad_alert_observations_and_success_audit_are_atomic():
    uri = os.getenv("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("MONGODB_TEST_URI is not configured")
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=5_000)
    database_name = "madalerttx_" + uuid4().hex
    database = client[database_name]
    incidents = MongoMadIncidentStore(database["mad_incidents"])
    audit = MongoAuditEventStore(database["audit_events"])
    incident_id = "mad-alert-atomic-" + uuid4().hex[:12]
    principal = Principal(
        subject="mad-operator",
        issuer="https://identity.example.test/",
        scopes=frozenset({"mad:read"}),
    )
    alert = {
        "id": "mad.integration.alert-atomicity",
        "deduplication_key": incident_id,
        "severity": "critical",
        "summary": "Integration alert for atomic observation verification.",
        "runbook": "docs/runbooks/MAD_EXECUTION_WORKERS.md",
    }
    try:
        topology = await client.admin.command("hello")
        assert topology.get("setName") or topology.get("msg") == "isdbgrid"
        await incidents.initialize()
        await audit.initialize()

        with pytest.raises(RuntimeError, match="simulated audit write failure"):
            await _record_mad_alerts_with_audit(
                mongo_client=client,
                incident_store=incidents,
                audit_store=FailingAuditStore(),
                alerts=[alert],
                principal=principal,
            )
        assert await database["mad_incidents"].count_documents({"_id": incident_id}) == 0
        assert await database["audit_events"].count_documents({"target_id": "execution"}) == 0

        await _record_mad_alerts_with_audit(
            mongo_client=client,
            incident_store=incidents,
            audit_store=audit,
            alerts=[alert],
            principal=principal,
        )
        incident = await database["mad_incidents"].find_one({"_id": incident_id})
        assert incident is not None
        assert incident["status"] == "firing"
        event = await database["audit_events"].find_one({
            "target_id": "execution",
            "action": "mad.metrics.read",
        })
        assert event is not None
        assert event["outcome"] == "success"
        assert event["metadata"] == {
            "required_scope": "mad:read",
            "alert_count": 1,
        }
    finally:
        await client.drop_database(database_name)
        await client.close()
