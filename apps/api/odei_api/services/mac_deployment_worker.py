"""Provider-neutral MAC deployment worker orchestration.

Concrete secret-manager and provider adapters are injected at process startup.
This module never logs resolved secret values or raw provider exception text.
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Mapping
from typing import Any, Protocol

from odei_api.services.mac_deployments import (
    MacDeploymentConflict,
    MongoMacDeploymentStore,
)

_SECRET_KEY = re.compile(
    r"(?:secret|password|passwd|token|api[_-]?key|access[_-]?key|private[_-]?key|"
    r"signing[_-]?key|encryption[_-]?key|credential)",
    re.IGNORECASE,
)


class MacSecretResolver(Protocol):
    async def resolve(
        self, reference: str, *, environment: str, provider: str,
    ) -> str: ...


class MacProviderAdapter(Protocol):
    async def deploy(
        self, config: Mapping[str, Any], *, environment: str,
        idempotency_key: str,
    ) -> str: ...

    async def verify(self, deployment_id: str, *, environment: str) -> bool: ...


class MacDeploymentWorker:
    """Execute queued attempts using explicitly injected trusted adapters."""

    def __init__(
        self, *, store: MongoMacDeploymentStore, environment_store: Any,
        secret_resolver: MacSecretResolver,
        providers: Mapping[str, MacProviderAdapter], worker_id: str,
        lease_seconds: int = 120, max_attempts: int = 5,
        operation_timeout_seconds: int = 300,
    ):
        if not isinstance(worker_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}", worker_id
        ):
            raise ValueError("Worker identity is invalid")
        if isinstance(operation_timeout_seconds, bool) or not isinstance(
            operation_timeout_seconds, int
        ) or not 1 <= operation_timeout_seconds <= 1800:
            raise ValueError("Operation timeout must be between 1 and 1800 seconds")
        self.store = store
        self.environment_store = environment_store
        self.secret_resolver = secret_resolver
        self.providers = dict(providers)
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.operation_timeout_seconds = operation_timeout_seconds

    async def run_once(self) -> dict[str, Any] | None:
        attempt = await self.store.claim_next(
            worker_id=self.worker_id, lease_seconds=self.lease_seconds,
            max_attempts=self.max_attempts,
        )
        if attempt is None:
            return None
        return await self.execute_claimed(attempt)

    async def _with_heartbeat(self, operation: Awaitable[Any], *, attempt_id: str) -> Any:
        task = asyncio.create_task(operation)
        interval = max(5, self.lease_seconds // 3)
        try:
            while True:
                done, _pending = await asyncio.wait({task}, timeout=interval)
                if done:
                    return await task
                try:
                    await self.store.heartbeat(
                        attempt_id=attempt_id, worker_id=self.worker_id,
                        lease_seconds=self.lease_seconds,
                    )
                except MacDeploymentConflict:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    raise
        except asyncio.CancelledError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise

    async def _resolve_config(
        self, config: Mapping[str, Any], *, environment: str, provider: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        # A single deadline bounds the entire secret-resolution phase, not
        # merely each individual adapter call. Heartbeats keep the lease alive
        # only while the bounded operation remains within that deadline.
        deadline = asyncio.get_running_loop().time() + self.operation_timeout_seconds
        for key, value in config.items():
            if _SECRET_KEY.search(key):
                if not isinstance(value, str) or not value.startswith("secret://"):
                    raise ValueError("Sensitive configuration must use a secret reference")
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError("Secret resolution exceeded the operation deadline")
                secret = await asyncio.wait_for(
                    self._with_heartbeat(
                        self.secret_resolver.resolve(
                            value, environment=environment, provider=provider,
                        ),
                        attempt_id=attempt_id,
                    ),
                    timeout=remaining,
                )
                if not isinstance(secret, str) or not secret or len(secret) > 16_384:
                    raise ValueError("Secret manager returned an invalid value")
                resolved[key] = secret
            else:
                resolved[key] = value
        return resolved

    async def execute_claimed(self, attempt: Mapping[str, Any]) -> dict[str, Any]:
        attempt_id = str(attempt.get("_id", ""))
        environment = str(attempt.get("environment", ""))
        provider_name = str(attempt.get("provider", ""))
        revision_number = attempt.get("revision")
        if attempt.get("state") != "running" or attempt.get("worker_id") != self.worker_id:
            raise MacDeploymentConflict("Worker must own a claimed running deployment attempt")
        adapter = self.providers.get(provider_name)
        try:
            if adapter is None:
                raise ValueError("No approved provider adapter is configured")
            deployment_id = attempt.get("provider_deployment_id")
            if deployment_id is None:
                record = await self.environment_store.get(environment)
                revision = next(
                    (item for item in record.get("versions", [])
                     if item.get("version") == revision_number),
                    None,
                )
                if revision is None or revision.get("status") not in {"approved", "promoted"}:
                    raise ValueError("Approved configuration revision is no longer available")
                config = await self._resolve_config(
                    revision.get("config", {}), environment=environment,
                    provider=provider_name, attempt_id=attempt_id,
                )
                deployment_id = await asyncio.wait_for(
                    self._with_heartbeat(
                        adapter.deploy(
                            config, environment=environment,
                            idempotency_key=str(attempt.get("idempotency_key", "")),
                        ),
                        attempt_id=attempt_id,
                    ),
                    timeout=self.operation_timeout_seconds,
                )
                if not isinstance(deployment_id, str) or not 1 <= len(deployment_id) <= 200:
                    raise ValueError("Provider adapter returned an invalid deployment identifier")
                await self.store.record_provider_deployment(
                    attempt_id=attempt_id, worker_id=self.worker_id,
                    provider_deployment_id=deployment_id,
                )
            try:
                verified = await asyncio.wait_for(
                    self._with_heartbeat(
                        adapter.verify(deployment_id, environment=environment),
                        attempt_id=attempt_id,
                    ),
                    timeout=self.operation_timeout_seconds,
                )
            except asyncio.CancelledError:
                raise
            except MacDeploymentConflict:
                raise
            except Exception:  # noqa: BLE001 - provider error text may contain secrets
                verified = False
            if not isinstance(verified, bool):
                verified = False
            if not verified:
                return await self.store.finish(
                    attempt_id=attempt_id, worker_id=self.worker_id,
                    verified=False, provider_deployment_id=deployment_id,
                    result_summary="Provider health verification failed or could not be completed",
                )
            return await self.store.finish(
                attempt_id=attempt_id, worker_id=self.worker_id,
                verified=True, provider_deployment_id=deployment_id,
                result_summary="Provider health verification passed",
            )
        except asyncio.CancelledError:
            # Leave the lease to expire; another worker can safely reclaim it.
            raise
        except MacDeploymentConflict:
            # A superseded or expired worker must never overwrite the new owner.
            raise
        except Exception:  # noqa: BLE001 - never persist raw provider or secret-manager errors
            # Do not persist provider exception text: it may contain secrets or request data.
            return await self.store.fail(
                attempt_id=attempt_id, worker_id=self.worker_id,
                reason="Provider execution failed; inspect restricted worker diagnostics",
            )
