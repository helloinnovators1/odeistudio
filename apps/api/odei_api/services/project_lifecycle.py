"""Transactional project lifecycle write fencing.

Every project-scoped mutation must call this inside the same MongoDB
transaction as its data writes. Updating the project document forces a write
conflict with the active -> deleting tombstone transition, closing the
check-then-write race.
"""
from __future__ import annotations

from typing import Any


class ProjectLifecycleWriteBlocked(RuntimeError):
    """The project is missing or no longer accepts new mutations."""


async def fence_project_write(
    projects: Any,
    *,
    organization_id: str,
    project_id: str,
    session: Any,
) -> None:
    if not organization_id or not project_id or session is None:
        raise ValueError("tenant, project and transaction session are required")
    result = await projects.update_one(
        {
            "organization_id": organization_id,
            "project_id": project_id,
            "status": "active",
        },
        {"$inc": {"lifecycle_write_seq": 1}},
        session=session,
    )
    if result.matched_count != 1:
        raise ProjectLifecycleWriteBlocked(
            "Project is missing or is closing; no project writes are accepted"
        )
