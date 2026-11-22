"""Operator-controlled MAC revision-history migration command.

Run from apps/api with the deployment's MONGODB_URI and MONGODB_DATABASE.
The default invocation is a read-only dry run; pass --apply to write.
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from odei_api.config import get_settings
from odei_api.mongo_client import create_mongo_client
from odei_api.services.mac_environment_migrations import (
    backfill_mac_environment_revisions,
    initialize_mac_revision_collection,
)

logger = logging.getLogger("odei_api.mac_revision_migration")


async def migrate(*, apply: bool) -> dict[str, int]:
    """Run one consistent transaction over all legacy environment revisions."""
    client, database_name = create_mongo_client(get_settings())
    try:
        database = client[database_name]
        environments = database["mac_environments"]
        revisions = database["mac_environment_revisions"]
        await initialize_mac_revision_collection(revisions)
        async with client.start_session() as session:
            async def transaction(active_session):
                return await backfill_mac_environment_revisions(
                    environments,
                    revisions,
                    session=active_session,
                    dry_run=not apply,
                )

            return await session.with_transaction(transaction)
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill immutable MAC environment revision history."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write missing revision documents. Without this flag, perform a read-only dry run.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = asyncio.run(migrate(apply=args.apply))
    except Exception as exc:  # noqa: BLE001 - avoid leaking database connection details
        logger.error("MAC revision migration failed (%s)", type(exc).__name__)
        raise SystemExit(1) from None
    mode = "APPLIED" if args.apply else "DRY RUN (no revision documents written)"
    logger.info(
        "%s: %s revisions to copy; %s already present.",
        mode,
        result["copied"],
        result["already_present"],
    )


if __name__ == "__main__":
    main()
