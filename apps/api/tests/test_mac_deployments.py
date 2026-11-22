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

    async def find_one_and_update(self, query, update, return_document=True):
        item = self.items.get(query["_id"])
        if item is None or any(item.get(k) != v for k, v in query.items()):
            return None
        item.update(update["$set"])
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
    args = dict(environment="staging", version=7, provider="aws",
                idempotency_key="request-12345678", actor="oidc-operator")
    first = await store.create_attempt(**args)
    second = await store.create_attempt(**args)
    assert first["_id"] == second["_id"]
    assert first["state"] == "queued"
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
