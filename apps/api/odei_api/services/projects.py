"""Tenant-scoped project lifecycle and owner-managed membership API.

Policy: any active organization member may create a project; its creator becomes
the project owner. Only that owner may manage project memberships. Members must
already have active membership in the same organization.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError, PyMongoError

from odei_api.config import get_settings
from odei_api.security.auth import Principal, get_current_principal, require_organization_membership
from odei_api.services.project_lifecycle import fence_project_write

router = APIRouter()
settings = get_settings()
principal_dependency = Depends(get_current_principal)


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ProjectMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    identity_issuer: str = Field(min_length=9, max_length=512)
    identity_subject: str = Field(min_length=1, max_length=256)


def _database(request: Request):
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(status_code=503, detail={
            "code": "PROJECT_STORE_UNAVAILABLE",
            "message": "Project storage is not configured.",
        })
    return database


async def _audit(request: Request, principal: Principal, organization_id: str,
                 action: str, target_type: str, target_id: str, outcome: str,
                 metadata: dict | None = None, session=None) -> None:
    store = getattr(request.app.state, "audit_event_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={
            "code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is not available.",
        })
    try:
        await store.append(
            organization_id=organization_id,
            actor_issuer=principal.issuer,
            actor_subject=principal.subject,
            action=action,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            request_id=uuid4().hex,
            metadata=metadata or {},
            session=session,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail={
            "code": "AUDIT_STORE_UNAVAILABLE",
            "message": "Project and audit storage are temporarily unavailable.",
        }) from exc


async def _require_org_member(request: Request, database, principal: Principal, organization_id: str):
    try:
        return await require_organization_membership(
            database["organization_memberships"],
            principal=principal,
            organization_id=organization_id,
        )
    except HTTPException as exc:
        if exc.status_code == 403:
            await _audit(
                request, principal, organization_id, "project.organization_access",
                "organization", organization_id, "denied",
                {"reason": "active_membership_required"},
            )
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "MEMBERSHIP_STORE_UNAVAILABLE",
            "message": "Organization membership storage is temporarily unavailable.",
        }) from exc


async def _fence_organization_membership(
    memberships,
    *,
    organization_id: str,
    identity_issuer: str,
    identity_subject: str,
    session,
) -> None:
    """Serialize project admission against concurrent organization-member revocation."""
    result = await memberships.update_one(
        {
            "organization_id": organization_id,
            "identity_issuer": identity_issuer,
            "identity_subject": identity_subject,
            "status": "active",
        },
        {"$inc": {"project_admission_write_seq": 1}},
        session=session,
    )
    if result.matched_count != 1:
        raise HTTPException(status_code=403, detail={
            "code": "ORGANIZATION_ACCESS_DENIED",
            "message": "Active organization membership is required.",
        })


async def _require_owner(request: Request, database, organization_id: str,
                        project_id: str, principal: Principal):
    try:
        project = await database["projects"].find_one({
            "organization_id": organization_id,
            "project_id": project_id,
            "status": "active",
        })
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "PROJECT_STORE_UNAVAILABLE",
            "message": "Project authorization is temporarily unavailable.",
        }) from exc
    if project is None:
        await _audit(
            request, principal, organization_id, "project.membership.manage",
            "project", project_id, "denied", {"reason": "project_not_found"},
        )
        raise HTTPException(status_code=404, detail={
            "code": "PROJECT_NOT_FOUND", "message": "Project was not found.",
        })
    if (project.get("owner_issuer") != principal.issuer
            or project.get("owner_subject") != principal.subject):
        await _audit(
            request, principal, organization_id, "project.membership.manage",
            "project", project_id, "denied", {"reason": "project_owner_required"},
        )
        raise HTTPException(status_code=403, detail={
            "code": "PROJECT_OWNER_REQUIRED",
            "message": "Only the project owner may manage project memberships.",
        })
    return project


def _project_response(project: dict) -> dict:
    return {
        "project_id": project["project_id"],
        "organization_id": project["organization_id"],
        "name": project["name"],
        "description": project.get("description", ""),
        "status": project["status"],
        "owner": {
            "issuer": project["owner_issuer"],
            "subject": project["owner_subject"],
        },
        "created_at": project["created_at"].isoformat(),
        "updated_at": project["updated_at"].isoformat(),
    }


@router.get(f"{settings.api_prefix}/organizations", tags=["organizations"])
async def list_organizations(
    request: Request,
    principal: Principal = principal_dependency,
) -> dict:
    """List only organizations with an active server-side membership for this identity."""
    database = _database(request)
    try:
        cursor = database["organization_memberships"].find({
            "identity_issuer": principal.issuer,
            "identity_subject": principal.subject,
            "status": "active",
        }, {"_id": 0, "organization_id": 1, "role": 1}).sort("organization_id", 1).limit(100)
        rows = await cursor.to_list(length=100)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "MEMBERSHIP_STORE_UNAVAILABLE",
            "message": "Organization discovery is temporarily unavailable.",
        }) from exc

    organizations = []
    seen: set[str] = set()
    for row in rows:
        organization_id = row.get("organization_id")
        role = row.get("role")
        if (
            not isinstance(organization_id, str) or not organization_id.strip()
            or organization_id != organization_id.strip() or len(organization_id) > 128
            or not isinstance(role, str) or not role.strip()
            or organization_id in seen
        ):
            raise HTTPException(status_code=503, detail={
                "code": "MEMBERSHIP_RECORD_INVALID",
                "message": "Organization membership data is not valid.",
            })
        seen.add(organization_id)
        await _audit(
            request, principal, organization_id, "organization.list",
            "organization", organization_id, "success", {"role": role},
        )
        organizations.append({"organization_id": organization_id, "role": role})
    return {"organizations": organizations, "limit": 100}


@router.post(f"{settings.api_prefix}/organizations/{{organization_id}}/projects",
             status_code=201, tags=["projects"])
async def create_project(
    payload: CreateProjectRequest, request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    if organization_id != organization_id.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_ORGANIZATION_ID"})
    database = _database(request)
    await _require_org_member(request, database, principal, organization_id)
    now = datetime.now(timezone.utc)
    project = {
        "project_id": uuid4().hex,
        "organization_id": organization_id,
        "name": payload.name,
        "description": payload.description,
        "status": "active",
        "owner_issuer": principal.issuer,
        "owner_subject": principal.subject,
        "created_at": now,
        "updated_at": now,
    }
    client = getattr(request.app.state, "mongo_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail={"code": "PROJECT_STORE_UNAVAILABLE"})
    try:
        async with client.start_session() as session, await session.start_transaction():
            await _fence_organization_membership(
                database["organization_memberships"],
                organization_id=organization_id,
                identity_issuer=principal.issuer,
                identity_subject=principal.subject,
                session=session,
            )
            await database["projects"].insert_one(project, session=session)
            await _audit(
                request, principal, organization_id, "project.create",
                "project", project["project_id"], "success",
                {"name": payload.name}, session,
            )
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "PROJECT_STORE_UNAVAILABLE",
            "message": "Project creation could not be committed.",
        }) from exc
    return _project_response(project)


@router.get(f"{settings.api_prefix}/organizations/{{organization_id}}/projects",
            tags=["projects"])
async def list_projects(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    database = _database(request)
    await _require_org_member(request, database, principal, organization_id)
    try:
        member_project_ids = await _active_project_ids(database, organization_id, principal)
        query = {
            "organization_id": organization_id,
            "status": "active",
            "$or": [
                {"owner_issuer": principal.issuer, "owner_subject": principal.subject},
                {"project_id": {"$in": member_project_ids}},
            ],
        }
        cursor = database["projects"].find(query).sort("created_at", -1).limit(100)
        rows = await cursor.to_list(length=100)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "PROJECT_STORE_UNAVAILABLE",
            "message": "Project listing is temporarily unavailable.",
        }) from exc
    await _audit(
        request, principal, organization_id, "project.list",
        "organization", organization_id, "success", {"returned_count": len(rows)},
    )
    return {"projects": [_project_response(row) for row in rows], "limit": 100}


async def _active_project_ids(database, organization_id: str, principal: Principal) -> list[str]:
    cursor = database["project_memberships"].find({
        "organization_id": organization_id,
        "identity_issuer": principal.issuer,
        "identity_subject": principal.subject,
        "status": "active",
    }, {"project_id": 1, "_id": 0}).limit(500)
    rows = await cursor.to_list(length=500)
    return [row["project_id"] for row in rows if isinstance(row.get("project_id"), str)]




@router.get(f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/members",
            tags=["projects"])
async def list_project_members(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    database = _database(request)
    await _require_org_member(request, database, principal, organization_id)
    await _require_owner(request, database, organization_id, project_id, principal)
    try:
        cursor = database["project_memberships"].find({
            "organization_id": organization_id,
            "project_id": project_id,
            "status": "active",
        }, {"_id": 0, "identity_issuer": 1, "identity_subject": 1, "created_at": 1})
        rows = await cursor.sort("created_at", 1).limit(100).to_list(length=100)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "PROJECT_STORE_UNAVAILABLE",
            "message": "Project membership listing is temporarily unavailable.",
        }) from exc
    await _audit(
        request, principal, organization_id, "project.member.list",
        "project", project_id, "success", {"returned_count": len(rows)},
    )
    return {
        "members": [{
            "identity_issuer": row["identity_issuer"],
            "identity_subject": row["identity_subject"],
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        } for row in rows],
        "limit": 100,
    }

@router.put(f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/members",
            status_code=200, tags=["projects"])
async def add_project_member(
    payload: ProjectMemberRequest, request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    parsed = urlsplit(payload.identity_issuer)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_MEMBER_IDENTITY"})
    if payload.identity_subject != payload.identity_subject.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_MEMBER_IDENTITY"})
    database = _database(request)
    await _require_org_member(request, database, principal, organization_id)
    await _require_owner(request, database, organization_id, project_id, principal)
    if payload.identity_issuer == principal.issuer and payload.identity_subject == principal.subject:
        raise HTTPException(status_code=409, detail={
            "code": "PROJECT_OWNER_IS_IMPLICIT_MEMBER",
            "message": "The project owner already has access and is not stored as a project member.",
        })
    try:
        target = await database["organization_memberships"].find_one({
            "organization_id": organization_id,
            "identity_issuer": payload.identity_issuer,
            "identity_subject": payload.identity_subject,
            "status": "active",
        })
        if target is None:
            raise HTTPException(status_code=404, detail={
                "code": "ORGANIZATION_MEMBER_NOT_FOUND",
                "message": "The target must be an active member of this organization.",
            })
        client = request.app.state.mongo_client
        now = datetime.now(timezone.utc)
        member = {
            "organization_id": organization_id, "project_id": project_id,
            "identity_issuer": payload.identity_issuer,
            "identity_subject": payload.identity_subject,
            "status": "active", "updated_at": now,
        }
        async with client.start_session() as session, await session.start_transaction():
            await _fence_organization_membership(
                database["organization_memberships"],
                organization_id=organization_id,
                identity_issuer=principal.issuer,
                identity_subject=principal.subject,
                session=session,
            )
            await _fence_organization_membership(
                database["organization_memberships"],
                organization_id=organization_id,
                identity_issuer=payload.identity_issuer,
                identity_subject=payload.identity_subject,
                session=session,
            )
            await fence_project_write(
                database["projects"], organization_id=organization_id,
                project_id=project_id, session=session,
            )
            existing = await database["project_memberships"].find_one({
                "organization_id": organization_id, "project_id": project_id,
                "identity_issuer": payload.identity_issuer,
                "identity_subject": payload.identity_subject,
            }, session=session)
            if existing and existing.get("status") == "active":
                raise HTTPException(status_code=409, detail={
                    "code": "PROJECT_MEMBER_ALREADY_ACTIVE",
                    "message": "The identity is already an active project member.",
                })
            if existing:
                await database["project_memberships"].update_one(
                    {"_id": existing["_id"]},
                    {"$set": member}, session=session,
                )
            else:
                member["created_at"] = now
                await database["project_memberships"].insert_one(member, session=session)
            await _audit(
                request, principal, organization_id, "project.member.add",
                "project", project_id, "success",
                {"member_issuer": payload.identity_issuer,
                 "member_subject": payload.identity_subject}, session,
            )
    except HTTPException:
        raise
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "PROJECT_MEMBER_CONFLICT",
            "message": "Project membership changed concurrently; retry the request.",
        }) from exc
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "PROJECT_STORE_UNAVAILABLE",
            "message": "Project membership could not be committed.",
        }) from exc
    return {"project_id": project_id, "status": "active"}


@router.delete(f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/members",
               tags=["projects"])
async def remove_project_member(
    payload: ProjectMemberRequest, request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    parsed = urlsplit(payload.identity_issuer)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_MEMBER_IDENTITY"})
    database = _database(request)
    await _require_org_member(request, database, principal, organization_id)
    await _require_owner(request, database, organization_id, project_id, principal)
    if (payload.identity_issuer == principal.issuer
            and payload.identity_subject == principal.subject):
        raise HTTPException(status_code=409, detail={
            "code": "PROJECT_OWNER_CANNOT_BE_REMOVED",
            "message": "Transfer project ownership before removing the owner.",
        })
    client = request.app.state.mongo_client
    try:
        async with client.start_session() as session, await session.start_transaction():
            await fence_project_write(
                database["projects"], organization_id=organization_id,
                project_id=project_id, session=session,
            )
            result = await database["project_memberships"].update_one({
                "organization_id": organization_id, "project_id": project_id,
                "identity_issuer": payload.identity_issuer,
                "identity_subject": payload.identity_subject, "status": "active",
            }, {"$set": {"status": "inactive", "updated_at": datetime.now(timezone.utc)}},
                session=session)
            if result.matched_count != 1:
                raise HTTPException(status_code=404, detail={
                    "code": "PROJECT_MEMBER_NOT_FOUND",
                    "message": "Active project membership was not found.",
                })
            await _audit(
                request, principal, organization_id, "project.member.remove",
                "project", project_id, "success",
                {"member_issuer": payload.identity_issuer,
                 "member_subject": payload.identity_subject}, session,
            )
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "PROJECT_STORE_UNAVAILABLE",
            "message": "Project membership could not be committed.",
        }) from exc
    return {"project_id": project_id, "status": "inactive"}
