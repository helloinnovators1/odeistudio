"""Transactional project lifecycle write fencing.

Every project-scoped mutation must call this inside the same MongoDB
transaction as its data writes. Updating the project document forces a write
conflict with the active -> deleting tombstone transition, closing the
check-then-write race.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class ProjectLifecycleWriteBlocked(HTTPException):
    """The project is missing or no longer accepts new mutations."""

    def __init__(self) -> None:
        super().__init__(status_code=409, detail={
            "code": "PROJECT_LIFECYCLE_CLOSED",
            "message": "The project is missing or is closing; no project writes are accepted.",
        })


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
        raise ProjectLifecycleWriteBlocked()
