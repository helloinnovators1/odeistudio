from datetime import datetime, timedelta, timezone

import pytest

from odei_api.services.mac_deployments import (
    MacDeploymentConflict,
    MacDeploymentError,
    MongoMacDeploymentStore,
)


class DuplicateKeyError(Exception):
    pass


class Attempts:
    def __init__(self):
        self.items = {}

    async def create_index(self, *_args, **_kwargs):
        return None

    async def insert_one(self, item, session=None):
        key = (item["environment"], item["idempotency_key"])
        if any((x["environment"], x["idempotency_key"]) == key for x in self.items.values()):
            raise DuplicateKeyError()
        self.items[item["_id"]] = dict(item)

    async def find_one(self, query, session=None):
        return next((dict(item) for item in self.items.values()
                     if all(item.get(k) == v for k, v in query.items())), None)

    async def find_one_and_update(self, query, update, sort=None, return_document=True):
        item = self.items.get(query["_id"])
        if item is None:
            return None
        def matches(candidate, condition):
            for key, value in condition.items():
                if key == "$or":
                    if not any(matches(candidate, branch) for branch in value):
                        return False
                elif isinstance(value, dict):
                    actual = candidate.get(key)
                    if "$lt" in value and not (actual is not None and actual < value["$lt"]):
                        return False
                    if "$lte" in value and not (actual is not None and actual <= value["$lte"]):
                        return False
                    if "$gt" in value and not (actual is not None and actual > value["$gt"]):
                        return False
                    if "$gte" in value and not (actual is not None and actual >= value["$gte"]):
                        return False
                elif candidate.get(key) != value:
                    return False
            return True
        if not matches(item, query):
            return None
        item.update(update.get("$set", {}))
        for key, value in update.get("$inc", {}).items():
            item[key] = item.get(key, 0) + value
        return dict(item)


class Environments:
    def __init__(self, status="approved"):
        self.status = status

    async def get(self, environment, session=None):
        return {"versions": [{"version": 7, "status": self.status}]}


@pytest.mark.asyncio
async def test_deployment_attempt_is_idempotent_and_only_approved_revisions_are_eligible():
    attempts = Attempts()
    store = MongoMacDeploymentStore(attempts, Environments())
    await store.initialize()
    args = {"environment": "staging", "version": 7, "provider": "aws",
            "idempotency_key": "request-12345678", "actor": "oidc-operator"}
    first = await store.create_attempt(**args)
    second = await store.create_attempt(**args)
    assert first["_id"] == second["_id"]
    assert first["state"] == "queued"
    with pytest.raises(MacDeploymentConflict):
        await store.create_attempt(**{**args, "actor": "oidc-another-operator"})
    with pytest.raises(MacDeploymentConflict):
        await store.create_attempt(**{**args, "provider": "azure"})
    with pytest.raises(MacDeploymentError):
        await MongoMacDeploymentStore(Attempts(), Environments("draft")).create_attempt(**args)


@pytest.mark.asyncio
async def test_only_one_worker_can_claim_and_finish_attempt_and_success_requires_verification():
    store = MongoMacDeploymentStore(Attempts(), Environments())
    attempt = await store.create_attempt(
        environment="production", version=7, provider="aws",
        idempotency_key="request-abcdefgh", actor="oidc-operator",
    )
    running = await store.claim(attempt_id=attempt["_id"], worker_id="worker-1")
    assert running["state"] == "running"
    with pytest.raises(MacDeploymentConflict):
        await store.claim(attempt_id=attempt["_id"], worker_id="worker-2")
    failed_verification = await store.finish(
        attempt_id=attempt["_id"], worker_id="worker-1", verified=False,
        provider_deployment_id="deploy-42", result_summary="Health check failed",
    )
    assert failed_verification["state"] == "verification_failed"
    assert failed_verification["verified"] is False
    with pytest.raises(MacDeploymentConflict):
        await store.finish(
            attempt_id=attempt["_id"], worker_id="worker-1", verified=True,
            provider_deployment_id="deploy-42", result_summary="Retry",
        )


@pytest.mark.asyncio
async def test_worker_ownership_and_bounded_result_are_enforced():
    store = MongoMacDeploymentStore(Attempts(), Environments())
    attempt = await store.create_attempt(
        environment="staging", version=7, provider="aws",
        idempotency_key="request-zyxwvuts", actor="oidc-operator",
    )
    await store.claim(attempt_id=attempt["_id"], worker_id="worker-1")
    with pytest.raises(MacDeploymentConflict):
        await store.fail(attempt_id=attempt["_id"], worker_id="worker-2", reason="no")
    with pytest.raises(MacDeploymentError):
        await store.finish(
            attempt_id=attempt["_id"], worker_id="worker-1", verified=True,
            provider_deployment_id=None, result_summary="x" * 501,
        )



@pytest.mark.asyncio
async def test_worker_lease_heartbeat_expiry_reclaim_and_fencing():
    attempts = Attempts()
    store = MongoMacDeploymentStore(attempts, Environments())
    attempt = await store.create_attempt(
        environment="staging", version=7, provider="aws",
        idempotency_key="lease-request-123", actor="oidc-operator",
    )
    first = await store.claim(
        attempt_id=attempt["_id"], worker_id="worker-1", lease_seconds=15,
    )
    assert first["attempt_count"] == 1
    assert first["lease_expires_at"] > datetime.now(timezone.utc)
    renewed = await store.heartbeat(
        attempt_id=attempt["_id"], worker_id="worker-1", lease_seconds=60,
    )
    assert renewed["lease_expires_at"] > first["lease_expires_at"]
    with pytest.raises(MacDeploymentConflict):
        await store.claim(attempt_id=attempt["_id"], worker_id="worker-2")

    # Simulate a crashed worker by expiring its persisted lease.
    attempts.items[attempt["_id"]]["lease_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    second = await store.claim(
        attempt_id=attempt["_id"], worker_id="worker-2", lease_seconds=30,
    )
    assert second["attempt_count"] == 2
    with pytest.raises(MacDeploymentConflict):
        await store.finish(
            attempt_id=attempt["_id"], worker_id="worker-1", verified=True,
            provider_deployment_id="stale-worker", result_summary="Stale completion",
        )
    completed = await store.finish(
        attempt_id=attempt["_id"], worker_id="worker-2", verified=True,
        provider_deployment_id="deployment-2", result_summary="Verified",
    )
    assert completed["state"] == "succeeded"
    assert completed["lease_expires_at"] is None


@pytest.mark.asyncio
async def test_worker_lease_and_retry_limits_reject_invalid_values():
    store = MongoMacDeploymentStore(Attempts(), Environments())
    attempt = await store.create_attempt(
        environment="staging", version=7, provider="aws",
        idempotency_key="lease-request-456", actor="oidc-operator",
    )
    with pytest.raises(MacDeploymentError):
        await store.claim(attempt_id=attempt["_id"], worker_id="worker-1", lease_seconds=True)
    with pytest.raises(MacDeploymentError):
        await store.claim(attempt_id=attempt["_id"], worker_id="worker-1", max_attempts=0)



@pytest.mark.asyncio
async def test_claim_next_reclaims_expired_lease_and_terminalizes_retry_exhaustion():
    attempts = Attempts()
    store = MongoMacDeploymentStore(attempts, Environments())
    queued = await store.create_attempt(
        environment="staging", version=7, provider="aws",
        idempotency_key="queue-recovery-123", actor="oidc-operator",
    )
    first = await store.claim(
        attempt_id=queued["_id"], worker_id="worker-crashed",
        lease_seconds=15, max_attempts=2,
    )
    assert first["attempt_count"] == 1
    attempts.items[queued["_id"]]["lease_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    recovered = await store.claim_next(
        worker_id="worker-recovered", lease_seconds=30, max_attempts=2,
    )
    assert recovered["_id"] == queued["_id"]
    assert recovered["attempt_count"] == 2
    assert recovered["worker_id"] == "worker-recovered"

    attempts.items[queued["_id"]]["lease_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    exhausted = await store.claim_next(
        worker_id="worker-last", lease_seconds=30, max_attempts=2,
    )
    assert exhausted is None
    terminal = attempts.items[queued["_id"]]
    assert terminal["state"] == "failed"
    assert terminal["verified"] is False
    assert terminal["lease_expires_at"] is None
    assert terminal["attempt_count"] == 2
