"""Fail-closed project authorization using server-owned project records."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException


async def require_project_access(
    projects: Any,
    project_memberships: Any,
    *,
    organization_id: str,
    project_id: str,
    identity_issuer: str,
    identity_subject: str,
) -> dict[str, Any]:
    """Return an active project only for its owner or an active project member."""
    if not organization_id.strip() or not project_id.strip():
        raise ValueError("organization_id and project_id are required")
    project = await projects.find_one({
        "organization_id": organization_id,
        "project_id": project_id,
        "status": "active",
    })
    if project is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "Project was not found."},
        )
    is_owner = (
        project.get("owner_issuer") == identity_issuer
        and project.get("owner_subject") == identity_subject
    )
    if is_owner:
        return project
    membership = await project_memberships.find_one({
        "organization_id": organization_id,
        "project_id": project_id,
        "identity_issuer": identity_issuer,
        "identity_subject": identity_subject,
        "status": "active",
    })
    if membership is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": "Project was not found."},
        )
    return project
