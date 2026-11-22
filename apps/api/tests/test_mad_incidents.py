import asyncio
from copy import deepcopy

import pytest

from odei_api.services.mad_incidents import (
    MadIncidentConflict,
    MadIncidentNotFound,
    MongoMadIncidentStore,
)


class UpdateResult:
    def __init__(self, modified_count):
        self.modified_count = modified_count


class Cursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, *_args):
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    async def to_list(self, length):
        return deepcopy(self.documents[:length])


class IncidentCollection:
    def __init__(self):
        self.documents = {}
        self.indexes = []

    async def create_index(self, keys, **options):
        self.indexes.append((keys, options))

    async def find_one(self, query):
        return deepcopy(self.documents.get(query["_id"]))

    async def insert_one(self, document):
        if document["_id"] in self.documents:
            from pymongo.errors import DuplicateKeyError
            raise DuplicateKeyError("duplicate")
        self.documents[document["_id"]] = deepcopy(document)

    async def update_one(self, query, update):
        current = self.documents.get(query["_id"])
        if current is None:
            return UpdateResult(0)
        for key, expected in query.items():
            actual = current.get(key)
            if isinstance(expected, dict) and "$ne" in expected:
                if actual == expected["$ne"]:
                    return UpdateResult(0)
            elif actual != expected:
                return UpdateResult(0)
        current.update(deepcopy(update.get("$set", {})))
        for key, amount in update.get("$inc", {}).items():
            current[key] = current.get(key, 0) + amount
        for key, value in update.get("$push", {}).items():
            if isinstance(value, dict) and "$each" in value:
                current.setdefault(key, []).extend(deepcopy(value["$each"]))
                if "$slice" in value:
                    current[key] = current[key][value["$slice"]:]
            else:
                current.setdefault(key, []).append(deepcopy(value))
        return UpdateResult(1)

    def find(self, query):
        values = list(self.documents.values())
        if query.get("status") == {"$ne": "resolved"}:
            values = [item for item in values if item["status"] != "resolved"]
        return Cursor(sorted(values, key=lambda item: item["updated_at"], reverse=True))


@pytest.mark.asyncio
async def test_incident_store_persists_deduplicated_alert_and_lifecycle():
    collection = IncidentCollection()
    store = MongoMadIncidentStore(collection)
    await store.initialize()
    alert = {
        "id": "mad.execution.queue_backlog",
        "deduplication_key": "execution-queue-backlog",
        "severity": "warning",
        "summary": "Queue is older than baseline.",
        "runbook": "docs/runbooks/MAD_EXECUTION_WORKERS.md",
    }
    await store.record_alerts([alert, alert])
    assert len(collection.documents) == 1
    incident = await store.transition(
        incident_id="execution-queue-backlog", action="acknowledge",
        actor="operator-1", expected_version=1,
    )
    assert incident["status"] == "acknowledged"
    assert incident["version"] == 2
    assigned = await store.transition(
        incident_id="execution-queue-backlog", action="assign",
        actor="operator-1", expected_version=2, assignee="oncall-team",
    )
    assert assigned["assignee"] == "oncall-team"
    resolved = await store.transition(
        incident_id="execution-queue-backlog", action="resolve",
        actor="operator-1", expected_version=3,
    )
    assert resolved["status"] == "resolved"
    assert (await store.list_incidents()) == []
    reopened = await store.transition(
        incident_id="execution-queue-backlog", action="reopen",
        actor="operator-1", expected_version=4,
    )
    assert reopened["status"] == "firing"
    assert len(reopened["history"]) == 5


@pytest.mark.asyncio
async def test_incident_store_reopens_resolved_alert_when_it_fires_again():
    collection = IncidentCollection()
    store = MongoMadIncidentStore(collection)
    await store.record_alerts([{
        "id": "mad.execution.failure_burst",
        "deduplication_key": "execution-failure-burst",
        "severity": "warning",
        "summary": "Failure burst.",
        "runbook": "docs/runbooks/MAD_EXECUTION_WORKERS.md",
    }])
    await store.transition(
        incident_id="execution-failure-burst", action="resolve",
        actor="operator-1", expected_version=1,
    )
    await store.record_alerts([{
        "id": "mad.execution.failure_burst",
        "deduplication_key": "execution-failure-burst",
        "severity": "critical",
        "summary": "Failure burst returned.",
        "runbook": "docs/runbooks/MAD_EXECUTION_WORKERS.md",
    }])
    incident = await store.collection.find_one({"_id": "execution-failure-burst"})
    assert incident["status"] == "firing"
    assert incident["severity"] == "critical"
    assert incident["version"] == 3
    assert incident["history"][-1]["action"] == "reopened"


@pytest.mark.asyncio
async def test_incident_store_rejects_stale_versions_invalid_transitions_and_unknown_ids():
    collection = IncidentCollection()
    store = MongoMadIncidentStore(collection)
    await store.record_alerts([{
        "id": "mad.execution.worker_pool_unavailable",
        "deduplication_key": "execution-worker-pool-unavailable",
        "severity": "critical",
        "summary": "No fresh workers.",
        "runbook": "docs/runbooks/MAD_EXECUTION_WORKERS.md",
    }])
    with pytest.raises(MadIncidentConflict):
        await store.transition(
            incident_id="execution-worker-pool-unavailable", action="resolve",
            actor="operator-1", expected_version=2,
        )
    with pytest.raises(MadIncidentConflict):
        await store.transition(
            incident_id="execution-worker-pool-unavailable", action="reopen",
            actor="operator-1", expected_version=1,
        )
    with pytest.raises(MadIncidentNotFound):
        await store.transition(
            incident_id="missing-incident", action="resolve",
            actor="operator-1", expected_version=1,
        )


class AuditStore:
    def __init__(self):
        self.events = []

    async def append(self, **event):
        self.events.append(event)


def test_mad_incident_routes_enforce_scopes_and_audit_transitions():
    from fastapi.testclient import TestClient

    from odei_api.main import app
    from odei_api.security.auth import Principal, get_current_principal

    collection = IncidentCollection()
    incident_store = MongoMadIncidentStore(collection)
    audit = AuditStore()
    previous_incidents = getattr(app.state, "mad_incident_store", None)
    previous_audit = getattr(app.state, "audit_event_store", None)
    app.state.mad_incident_store = incident_store
    app.state.audit_event_store = audit
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="operator-1", issuer="https://identity.example.test/",
        scopes=frozenset({"mad:read"}),
    )
    try:
        denied = TestClient(app).post(
            "/api/v1/mad/incidents/example-incident/transitions",
            json={"action": "resolve", "expected_version": 1},
        )
        assert denied.status_code == 403
        assert audit.events[-1]["outcome"] == "denied"

        asyncio.run(incident_store.record_alerts([{
            "id": "mad.execution.queue_backlog",
            "deduplication_key": "example-incident",
            "severity": "warning",
            "summary": "Queue is delayed.",
            "runbook": "docs/runbooks/MAD_EXECUTION_WORKERS.md",
        }]))
        app.dependency_overrides[get_current_principal] = lambda: Principal(
            subject="operator-1", issuer="https://identity.example.test/",
            scopes=frozenset({"mad:incident:manage", "mad:read"}),
        )
        client = TestClient(app)
        listed = client.get("/api/v1/mad/incidents")
        assert listed.status_code == 200
        assert listed.json()["incidents"][0]["status"] == "firing"
        changed = client.post(
            "/api/v1/mad/incidents/example-incident/transitions",
            json={"action": "acknowledge", "expected_version": 1},
        )
        assert changed.status_code == 200
        assert changed.json()["incident"]["status"] == "acknowledged"
        assert audit.events[-1]["action"] == "mad.incident.acknowledge"
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.state.mad_incident_store = previous_incidents
        app.state.audit_event_store = previous_audit
