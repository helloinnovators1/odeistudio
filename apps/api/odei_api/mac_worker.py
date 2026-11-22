"""Deployable MAC worker process entry point.

Provider and secret-manager adapters are trusted deployment plugins selected only
by operator-controlled environment variables. The process fails closed if either
factory is absent or malformed.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import os
import re
import socket
from collections.abc import Mapping
from typing import Any

from odei_api.config import get_settings
from odei_api.mongo_client import create_mongo_client
from odei_api.services.mac_deployments import MongoMacDeploymentStore
from odei_api.services.mac_deployment_worker import MacDeploymentWorker
from odei_api.services.mac_revision_environment_store import MongoMacRevisionEnvironmentStore

logger = logging.getLogger("odei_api.mac_worker")
_FACTORY_SPEC = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")


def _load_factory(spec: str, *, setting_name: str) -> Any:
    """Load one explicitly configured trusted module:callable adapter factory."""
    if not isinstance(spec, str) or not _FACTORY_SPEC.fullmatch(spec):
        raise RuntimeError(f"{setting_name} must be a trusted module:callable reference")
    module_name, attribute = spec.split(":", 1)
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(f"{setting_name} could not be loaded") from exc
    if not callable(factory):
        raise RuntimeError(f"{setting_name} must resolve to a callable")
    return factory


async def run_worker(*, once: bool = False, poll_interval: float = 2.0) -> None:
    """Run the MAC queue consumer until interrupted or one attempt is processed."""
    if isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float)) or not (
        0.25 <= poll_interval <= 30
    ):
        raise ValueError("Poll interval must be between 0.25 and 30 seconds")
    provider_spec = os.getenv("ODEI_MAC_PROVIDER_FACTORY", "")
    resolver_spec = os.getenv("ODEI_MAC_SECRET_RESOLVER_FACTORY", "")
    provider_factory = _load_factory(
        provider_spec, setting_name="ODEI_MAC_PROVIDER_FACTORY"
    )
    resolver_factory = _load_factory(
        resolver_spec, setting_name="ODEI_MAC_SECRET_RESOLVER_FACTORY"
    )

    settings = get_settings()
    client, database_name = create_mongo_client(settings)
    try:
        database = client[database_name]
        environment_store = MongoMacRevisionEnvironmentStore(
            database["mac_environments"], database["mac_environment_revisions"]
        )
        # This also verifies that every legacy revision was migrated before the
        # worker can act on any queued deployment.
        await environment_store.initialize()
        deployment_store = MongoMacDeploymentStore(
            database["mac_deployment_attempts"], environment_store
        )
        await deployment_store.initialize()

        providers = provider_factory(settings=settings, database=database)
        resolver = resolver_factory(settings=settings, database=database)
        if not isinstance(providers, Mapping) or not providers:
            raise RuntimeError("Provider factory must return a non-empty provider mapping")
        if resolver is None or not callable(getattr(resolver, "resolve", None)):
            raise RuntimeError("Secret resolver factory returned an invalid adapter")

        worker_id = os.getenv("ODEI_MAC_WORKER_ID") or (
            f"{socket.gethostname()}-{os.getpid()}"
        )
        worker = MacDeploymentWorker(
            store=deployment_store,
            environment_store=environment_store,
            secret_resolver=resolver,
            providers=providers,
            worker_id=worker_id,
        )
        while True:
            attempt = await worker.run_once()
            if attempt is not None:
                logger.info(
                    "MAC deployment attempt %s finished with state %s",
                    str(attempt.get("_id", "unknown")),
                    str(attempt.get("state", "unknown")),
                )
                if once:
                    return
                continue
            if once:
                return
            await asyncio.sleep(poll_interval)
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the ODEI MAC deployment queue worker."
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Process at most one queued deployment attempt and exit.",
    )
    parser.add_argument(
        "--poll-interval", type=float, default=2.0,
        help="Idle queue polling interval in seconds (0.25–30).",
    )
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("ODEI_LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        asyncio.run(run_worker(once=args.once, poll_interval=args.poll_interval))
    except KeyboardInterrupt:
        logger.info("MAC worker shutdown requested")
    except Exception as exc:  # noqa: BLE001 - adapter exceptions may contain secrets
        logger.error("MAC worker stopped safely (%s)", type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
