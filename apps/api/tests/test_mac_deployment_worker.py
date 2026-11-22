import pytest

from odei_api.services.mac_deployment_worker import MacDeploymentWorker


class FakeStore:
    def __init__(self, attempt):
        self.attempt = attempt
        self.finished = None
        self.failed = None
        self.claimed = None

    async def claim_next(self, **kwargs):
        self.claimed = kwargs
        return self.attempt

    async def finish(self, **kwargs):
        self.finished = kwargs
        return {"state": "succeeded" if kwargs["verified"] else "verification_failed", **kwargs}

    async def fail(self, **kwargs):
        self.failed = kwargs
        return {"state": "failed", **kwargs}


class FakeEnvironmentStore:
    async def get(self, environment):
        return {"versions": [{
            "version": 3, "status": "approved",
            "config": {"region": "eu-west-1", "database_password": "secret://vault/staging/db"},
        }]}


class FakeSecrets:
    def __init__(self):
        self.calls = []

    async def resolve(self, reference, *, environment, provider):
        self.calls.append((reference, environment, provider))
        return "sensitive-runtime-value"


class FakeProvider:
    def __init__(self, verified=True):
        self.verified = verified
        self.deployed = None
        self.verified_id = None

    async def deploy(self, config, *, environment, idempotency_key):
        self.deployed = (dict(config), environment, idempotency_key)
        return "provider-deployment-123"

    async def verify(self, deployment_id, *, environment):
        self.verified_id = (deployment_id, environment)
        return self.verified


def attempt(provider="aws"):
    return {
        "_id": "a" * 32, "environment": "staging", "revision": 3,
        "provider": provider, "idempotency_key": "stable-request-123",
    }


@pytest.mark.asyncio
async def test_worker_resolves_secrets_only_in_memory_and_verifies_provider_result():
    store = FakeStore(attempt())
    secrets = FakeSecrets()
    provider = FakeProvider()
    worker = MacDeploymentWorker(
        store=store, environment_store=FakeEnvironmentStore(),
        secret_resolver=secrets, providers={"aws": provider}, worker_id="worker-1",
    )
    result = await worker.run_once()
    assert result["state"] == "succeeded"
    assert store.claimed["worker_id"] == "worker-1"
    assert provider.deployed[0]["database_password"] == "sensitive-runtime-value"
    assert provider.deployed[0]["region"] == "eu-west-1"
    assert secrets.calls == [("secret://vault/staging/db", "staging", "aws")]
    assert store.finished["provider_deployment_id"] == "provider-deployment-123"
    assert "sensitive-runtime-value" not in repr(store.finished)
    assert provider.verified_id == ("provider-deployment-123", "staging")


@pytest.mark.asyncio
async def test_worker_records_verification_failure_without_marking_success():
    store = FakeStore(attempt())
    worker = MacDeploymentWorker(
        store=store, environment_store=FakeEnvironmentStore(),
        secret_resolver=FakeSecrets(), providers={"aws": FakeProvider(False)},
        worker_id="worker-2",
    )
    result = await worker.run_once()
    assert result["state"] == "verification_failed"
    assert store.finished["verified"] is False


@pytest.mark.asyncio
async def test_worker_fails_closed_for_missing_provider_without_leaking_exception_text():
    store = FakeStore(attempt("unknown-cloud"))
    worker = MacDeploymentWorker(
        store=store, environment_store=FakeEnvironmentStore(),
        secret_resolver=FakeSecrets(), providers={}, worker_id="worker-3",
    )
    result = await worker.run_once()
    assert result["state"] == "failed"
    assert store.failed["reason"] == (
        "Provider execution failed; inspect restricted worker diagnostics"
    )


@pytest.mark.asyncio
async def test_worker_returns_none_when_no_deployment_is_queued():
    store = FakeStore(None)
    worker = MacDeploymentWorker(
        store=store, environment_store=FakeEnvironmentStore(),
        secret_resolver=FakeSecrets(), providers={}, worker_id="worker-4",
    )
    assert await worker.run_once() is None
