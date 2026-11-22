from datetime import datetime, timedelta, timezone

import pytest

from odei_api.services.mad_telemetry import (
    MongoWorkerHeartbeatStore,
    collect_mad_execution_metrics,
)


class HeartbeatCollection:
    def __init__(self):
        self.document = None
        self.indexes = []

    async def create_index(self, keys, **options):
        self.indexes.append((keys, options))

    async def update_one(self, query, update, *, upsert):
        assert upsert is True
        self.document = {
            **(self.document or {}),
            **update["$setOnInsert"],
            **update["$set"],
        }


@pytest.mark.asyncio
async def test_worker_heartbeat_is_bounded_and_never_stores_host_details():
    collection = HeartbeatCollection()
    store = MongoWorkerHeartbeatStore(collection)
    await store.initialize()
    timestamp = await store.heartbeat(
        worker_id="worker-01", status="busy", active_run_id="a" * 32,
    )
    assert timestamp.tzinfo is timezone.utc
    assert collection.document["worker_id"] == "worker-01"
    assert collection.document["status"] == "busy"
    assert collection.document["active_run_id"] == "a" * 32
    assert "hostname" not in collection.document
    assert "environment" not in collection.document
    assert collection.document["protocol_version"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_id,status,run_id", [
    ("../host", "idle", None),
    ("worker", "healthy", None),
    ("worker", "busy", "../tenant"),
])
async def test_worker_heartbeat_rejects_untrusted_identifiers_and_states(worker_id, status, run_id):
    store = MongoWorkerHeartbeatStore(HeartbeatCollection())
    with pytest.raises(ValueError):
        await store.heartbeat(worker_id=worker_id, status=status, active_run_id=run_id)


class MetricsCollection:
    def __init__(self, documents):
        self.documents = documents

    async def count_documents(self, query):
        def matches(document):
            for key, expected in query.items():
                actual = document.get(key)
                if isinstance(expected, dict):
                    if "$gte" in expected and (actual is None or actual < expected["$gte"]):
                        return False
                    if "$in" in expected and actual not in expected["$in"]:
                        return False
                elif actual != expected:
                    return False
            return True
        return sum(matches(document) for document in self.documents)

    async def find_one(self, query, *, sort):
        matches = [
            document for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]
        if not matches:
            return None
        field, direction = sort[0]
        return sorted(matches, key=lambda document: document.get(field), reverse=direction < 0)[0]


class MetricsDatabase:
    def __init__(self, runs, workers):
        self.collections = {
            "execution_runs": MetricsCollection(runs),
            "execution_worker_heartbeats": MetricsCollection(workers),
        }

    def __getitem__(self, name):
        return self.collections[name]


@pytest.mark.asyncio
async def test_mad_metrics_are_aggregated_and_do_not_expose_tenant_or_artifact_data():
    now = datetime.now(timezone.utc)
    database = MetricsDatabase(
        runs=[
            {"status": "queued", "created_at": now - timedelta(minutes=20), "organization_id": "secret-org"},
            {"status": "running", "organization_id": "secret-org"},
            {"status": "completed", "updated_at": now - timedelta(hours=1), "stdout": "private output"},
            {"status": "failed", "updated_at": now - timedelta(days=2)},
        ],
        workers=[
            {"status": "idle", "last_seen_at": now, "worker_id": "worker-1"},
            {"status": "busy", "last_seen_at": now - timedelta(minutes=10), "worker_id": "worker-2"},
        ],
    )
    metrics = await collect_mad_execution_metrics(database)
    assert metrics["workers"] == {"state": "degraded", "known": 2, "fresh": 1, "stale": 1, "stopping": 0}
    assert metrics["queue"]["queued"] == 1
    assert metrics["queue"]["active"] == 1
    assert metrics["queue"]["oldest_queued_at"] == (now - timedelta(minutes=20)).isoformat()
    assert metrics["executions_24h"] == {"completed": 1, "failed": 0, "cancelled": 0}
    serialized = repr(metrics)
    assert "secret-org" not in serialized
    assert "private output" not in serialized
    assert "worker-1" not in serialized


def test_mad_metrics_endpoint_requires_configured_operations_credential(monkeypatch):
    from fastapi.testclient import TestClient

    from odei_api.main import app, settings

    previous_database = getattr(app.state, "mongo_database", None)
    monkeypatch.setattr(settings, "mad_metrics_token", None)
    app.state.mongo_database = MetricsDatabase([], [])
    try:
        response = TestClient(app).get("/api/v1/internal/mad/execution-metrics")
    finally:
        app.state.mongo_database = previous_database
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MAD_METRICS_NOT_CONFIGURED"


def test_mad_metrics_endpoint_rejects_invalid_token_and_returns_safe_metrics(monkeypatch):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from odei_api.main import app, settings

    previous_database = getattr(app.state, "mongo_database", None)
    monkeypatch.setattr(settings, "mad_metrics_token", SecretStr("operations-secret-value-with-32-chars-minimum"))
    app.state.mongo_database = MetricsDatabase([], [])
    try:
        client = TestClient(app)
        denied = client.get(
            "/api/v1/internal/mad/execution-metrics",
            headers={"X-ODEI-MAD-Token": "wrong"},
        )
        allowed = client.get(
            "/api/v1/internal/mad/execution-metrics",
            headers={"X-ODEI-MAD-Token": "operations-secret-value-with-32-chars-minimum"},
        )
    finally:
        app.state.mongo_database = previous_database
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["workers"]["state"] == "unknown"
    assert allowed.json()["alerts"] == []
    assert "tenant" not in allowed.text.lower()


def test_mad_metrics_token_configuration_requires_32_ascii_characters():
    from pydantic import SecretStr, ValidationError

    from odei_api.config import Settings

    with pytest.raises(ValidationError):
        Settings(mad_metrics_token=SecretStr("too-short"))
    with pytest.raises(ValidationError):
        Settings(mad_metrics_token=SecretStr("non-ascii-" + "é" * 30))
    assert Settings(mad_metrics_token=SecretStr("x" * 32)).mad_metrics_token is not None


@pytest.mark.asyncio
async def test_mad_metrics_normalize_naive_mongodb_timestamps_to_utc():
    naive_timestamp = datetime(2026, 1, 2, 3, 4, 5)
    metrics = await collect_mad_execution_metrics(MetricsDatabase(
        runs=[{"status": "queued", "created_at": naive_timestamp}],
        workers=[],
    ))
    assert metrics["queue"]["oldest_queued_at"] == "2026-01-02T03:04:05+00:00"


@pytest.mark.asyncio
async def test_mad_metrics_degrade_when_workers_are_stopping_even_if_another_is_fresh():
    now = datetime.now(timezone.utc)
    metrics = await collect_mad_execution_metrics(MetricsDatabase(
        runs=[{"status": "running"}],
        workers=[
            {"status": "idle", "last_seen_at": now, "worker_id": "worker-live"},
            {"status": "stopping", "last_seen_at": now, "worker_id": "worker-stopping"},
        ],
    ))
    assert metrics["workers"] == {
        "state": "degraded", "known": 2, "fresh": 1, "stale": 0, "stopping": 1,
    }


@pytest.mark.asyncio
async def test_mad_queue_degrades_when_active_runs_have_no_fresh_workers():
    now = datetime.now(timezone.utc)
    metrics = await collect_mad_execution_metrics(MetricsDatabase(
        runs=[{"status": "running"}],
        workers=[{"status": "stopping", "last_seen_at": now, "worker_id": "worker-stopping"}],
    ))
    assert metrics["workers"]["state"] == "degraded"
    assert metrics["queue"] == {"state": "degraded", "queued": 0, "active": 1, "oldest_queued_at": None}


def test_mad_alerts_detect_unavailable_workers_and_aged_queue_without_sensitive_data():
    from odei_api.services.mad_telemetry import evaluate_mad_alerts
    metrics = {
        "observed_at": "2026-11-22T12:00:00+00:00",
        "workers": {"state": "degraded", "known": 1, "fresh": 0, "stale": 1, "stopping": 0},
        "queue": {"state": "degraded", "queued": 2, "active": 1,
                  "oldest_queued_at": "2026-11-22T11:30:00+00:00"},
        "executions_24h": {"completed": 0, "failed": 0, "cancelled": 0},
        "private_tenant": "must-not-be-copied",
    }
    alerts = evaluate_mad_alerts(metrics)
    assert [alert["id"] for alert in alerts] == [
        "mad.execution.worker_pool_unavailable", "mad.execution.queue_backlog",
    ]
    assert alerts[0]["severity"] == "critical"
    assert alerts[1]["age_seconds"] == 1800
    assert all(alert["status"] == "firing" for alert in alerts)
    assert "must-not-be-copied" not in repr(alerts)


def test_mad_alerts_detect_failure_burst_and_worker_degradation():
    from odei_api.services.mad_telemetry import evaluate_mad_alerts
    alerts = evaluate_mad_alerts({
        "observed_at": "2026-11-22T12:00:00+00:00",
        "workers": {"state": "degraded", "fresh": 1},
        "queue": {"queued": 0, "active": 0, "oldest_queued_at": None},
        "executions_24h": {"failed": 5},
    })
    assert {alert["id"] for alert in alerts} == {
        "mad.execution.worker_pool_degraded", "mad.execution.failure_burst",
    }


def test_mad_alerts_do_not_fire_for_healthy_platform_or_malformed_queue_time():
    from odei_api.services.mad_telemetry import evaluate_mad_alerts
    healthy = {
        "observed_at": "2026-11-22T12:00:00+00:00",
        "workers": {"state": "healthy", "fresh": 2},
        "queue": {"queued": 0, "active": 0, "oldest_queued_at": None},
        "executions_24h": {"failed": 0},
    }
    assert evaluate_mad_alerts(healthy) == []
    malformed = {**healthy, "queue": {
        "queued": 1, "active": 0, "oldest_queued_at": "not-a-time",
    }}
    assert evaluate_mad_alerts(malformed) == []
