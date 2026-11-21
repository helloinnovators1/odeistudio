from datetime import datetime, timezone

import pytest

from odei_api.services.audit_store import (
    AuditEventValidationError,
    MongoAuditEventStore,
)


class FakeAuditCollection:
    def __init__(self):
        self.documents = []
        self.indexes = []
        self.sessions = []

    async def create_index(self, fields, **kwargs):
        self.indexes.append((fields, kwargs))

    async def insert_one(self, document, session=None):
        self.documents.append(document)
        self.sessions.append(session)


@pytest.mark.asyncio
async def test_audit_store_appends_tenant_scoped_event_and_redacts_metadata():
    collection = FakeAuditCollection()
    store = MongoAuditEventStore(collection)
    occurred_at = datetime(2026, 11, 20, tzinfo=timezone.utc)

    event = await store.append(
        organization_id="org-1",
        actor_issuer="https://identity.example.test/",
        actor_subject="user-1",
        action="organization.membership.read",
        target_type="organization",
        target_id="org-1",
        outcome="success",
        request_id="req-123",
        trace_id="trace-123",
        metadata={
            "role": "developer",
            "api_token": "do-not-store",
            "note": "credential=super-secret-value",
        },
        occurred_at=occurred_at,
    )

    assert collection.documents == [event]
    assert event["organization_id"] == "org-1"
    assert event["actor_subject"] == "user-1"
    assert event["occurred_at"] == occurred_at
    assert event["metadata"]["api_token"] == "[REDACTED]"
    assert "super-secret-value" not in str(event)
    assert event["schema_version"] == 1


@pytest.mark.asyncio
async def test_audit_store_rejects_invalid_identity_action_outcome_and_timestamp():
    collection = FakeAuditCollection()
    store = MongoAuditEventStore(collection)
    base = {
        "organization_id": "org-1",
        "actor_issuer": "https://identity.example.test/",
        "actor_subject": "user-1",
        "action": "organization.membership.read",
        "target_type": "organization",
        "target_id": "org-1",
        "outcome": "success",
        "request_id": "req-123",
    }
    for override in (
        {"organization_id": "../other"},
        {"actor_issuer": "http://identity.example.test/"},
        {"action": "Not An Action"},
        {"outcome": "unknown"},
        {"occurred_at": datetime(2026, 11, 20)},
    ):
        with pytest.raises(AuditEventValidationError):
            await store.append(**(base | override))
    assert collection.documents == []


@pytest.mark.asyncio
async def test_audit_store_bounds_metadata_and_rejects_non_json_values():
    collection = FakeAuditCollection()
    store = MongoAuditEventStore(collection)
    base = {
        "organization_id": "org-1",
        "actor_issuer": "https://identity.example.test/",
        "actor_subject": "user-1",
        "action": "organization.membership.read",
        "target_type": "organization",
        "target_id": "org-1",
        "outcome": "success",
        "request_id": "req-123",
    }
    with pytest.raises(AuditEventValidationError, match="too many fields"):
        await store.append(**base, metadata={str(i): i for i in range(33)})
    with pytest.raises(AuditEventValidationError, match="JSON-compatible"):
        await store.append(**base, metadata={"bad": object()})
    with pytest.raises(AuditEventValidationError, match="nesting"):
        await store.append(**base, metadata={"a": {"b": {"c": {"d": {"e": "x"}}}}})
    assert collection.documents == []


@pytest.mark.asyncio
async def test_audit_store_initializes_tenant_and_time_indexes():
    collection = FakeAuditCollection()
    await MongoAuditEventStore(collection).initialize()
    assert len(collection.indexes) == 3
    assert any(("organization_id", 1) in fields for fields, _ in collection.indexes)



@pytest.mark.asyncio
async def test_audit_store_forwards_existing_transaction_session():
    collection = FakeAuditCollection()
    store = MongoAuditEventStore(collection)
    session = object()
    await store.append(
        organization_id="org-1",
        actor_issuer="https://identity.example.test/",
        actor_subject="user-1",
        action="nexus.task.approve",
        target_type="nexus_task",
        target_id="task-1",
        outcome="success",
        request_id="req-transaction-1",
        session=session,
    )
    assert collection.sessions == [session]



@pytest.mark.asyncio
async def test_audit_store_accepts_started_lifecycle_outcome():
    collection = FakeAuditCollection()
    store = MongoAuditEventStore(collection)
    event = await store.append(
        organization_id="org-1",
        actor_issuer="https://identity.example/",
        actor_subject="user-1",
        action="nexus.chat.request",
        target_type="project",
        target_id="project-1",
        outcome="started",
        request_id="request-started",
        metadata={"message_count": 1},
    )
    assert event["outcome"] == "started"
