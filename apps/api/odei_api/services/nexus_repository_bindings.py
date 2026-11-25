"""Project-owner-controlled, GitHub-App-verified repository bindings."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from pymongo.errors import DuplicateKeyError, PyMongoError

from odei_api.config import get_settings
from odei_api.security.auth import Principal, get_current_principal, require_organization_membership
from odei_api.services.github_app import (
    GitHubAppNotConfigured,
    GitHubRepositoryVerificationError,
)
from odei_api.services.project_access import require_project_access

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()
principal_dependency = Depends(get_current_principal)


class BindRepositoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    installation_id: StrictInt = Field(ge=1)
    owner: str = Field(min_length=1, max_length=39, pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
    repository: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    expected_version: StrictInt | None = Field(default=None, ge=1)


class RemoveRepositoryBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=1)


def _public_binding(document: dict) -> dict:
    return {
        "organization_id": document["organization_id"],
        "project_id": document["project_id"],
        "state": document["state"],
        "repository": {
            "id": document["repository_id"],
            "node_id": document["repository_node_id"],
            "owner": document["owner"],
            "name": document["name"],
            "full_name": document["full_name"],
            "default_branch": document["default_branch"],
            "private": document["private"],
        },
        "installation_id": document["installation_id"],
        "contents_permission": document["contents_permission"],
        "binding_version": document["binding_version"],
        "verified_at": document["verified_at"].isoformat(),
        "updated_at": document["updated_at"].isoformat(),
    }


async def _authorize(request: Request, organization_id: str, project_id: str, principal: Principal):
    database = getattr(request.app.state, "mongo_database", None)
    audit = getattr(request.app.state, "audit_event_store", None)
    if database is None or audit is None:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_BINDING_UNAVAILABLE"})
    try:
        await require_organization_membership(
            database["organization_memberships"], principal=principal,
            organization_id=organization_id,
        )
        project = await require_project_access(
            database["projects"], database["project_memberships"],
            organization_id=organization_id, project_id=project_id,
            identity_issuer=principal.issuer, identity_subject=principal.subject,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_AUTHORIZATION_UNAVAILABLE"}) from exc
    except HTTPException:
        raise
    return database, audit, project


async def _owner_only(request: Request, organization_id: str, project_id: str, principal: Principal):
    database, audit, project = await _authorize(request, organization_id, project_id, principal)
    if (
        project.get("owner_issuer") != principal.issuer
        or project.get("owner_subject") != principal.subject
    ):
        raise HTTPException(status_code=403, detail={
            "code": "PROJECT_OWNER_REQUIRED",
            "message": "Only the project owner may change its trusted repository binding.",
        })
    return database, audit


async def _audit(audit, principal, organization_id, project_id, action, outcome, metadata=None):
    try:
        await audit.append(
            organization_id=organization_id, actor_issuer=principal.issuer,
            actor_subject=principal.subject, action=action,
            target_type="nexus_repository_binding", target_id=project_id,
            outcome=outcome, request_id=uuid4().hex, metadata=metadata or {},
        )
    except Exception as exc:
        logger.error("Repository binding audit write failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail={
            "code": "REPOSITORY_BINDING_AUDIT_UNAVAILABLE",
            "message": "Repository binding operation could not be audited.",
        }) from exc


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/repository-binding",
    tags=["repository-binding"],
)
async def get_repository_binding(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
):
    database, audit, _project = await _authorize(request, organization_id, project_id, principal)
    try:
        binding = await database["nexus_repository_bindings"].find_one({
            "_id": f"{organization_id}:{project_id}",
            "organization_id": organization_id, "project_id": project_id,
        })
        await _audit(audit, principal, organization_id, project_id,
                     "nexus.repository_binding.read", "success",
                     {"found": binding is not None})
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_BINDING_UNAVAILABLE"}) from exc
    return {"binding": _public_binding(binding) if binding else None}


@router.put(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/repository-binding",
    tags=["repository-binding"],
)
async def bind_repository(
    payload: BindRepositoryRequest,
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
):
    database, audit = await _owner_only(request, organization_id, project_id, principal)
    github = getattr(request.app.state, "github_app_client", None)
    if github is None:
        raise HTTPException(status_code=503, detail={
            "code": "GITHUB_APP_NOT_CONFIGURED",
            "message": "Trusted repository binding is unavailable until a GitHub App is configured.",
        })
    collection = database["nexus_repository_bindings"]
    key = f"{organization_id}:{project_id}"
    await _audit(audit, principal, organization_id, project_id,
                 "nexus.repository_binding.bind", "started",
                 {"installation_id": payload.installation_id})
    try:
        existing = await collection.find_one({"_id": key})
        if existing is None and payload.expected_version is not None:
            raise HTTPException(status_code=409, detail={"code": "REPOSITORY_BINDING_VERSION_CONFLICT"})
        if existing is not None and payload.expected_version != existing.get("binding_version"):
            raise HTTPException(status_code=409, detail={"code": "REPOSITORY_BINDING_VERSION_CONFLICT"})
        verified = await github.verify_repository(
            installation_id=payload.installation_id,
            owner=payload.owner, name=payload.repository,
        )
    except GitHubAppNotConfigured as exc:
        raise HTTPException(status_code=503, detail={"code": "GITHUB_APP_NOT_CONFIGURED"}) from exc
    except GitHubRepositoryVerificationError as exc:
        await _audit(audit, principal, organization_id, project_id,
                     "nexus.repository_binding.verify", "denied",
                     {"reason": "provider_verification_failed"})
        raise HTTPException(status_code=422, detail={
            "code": "GITHUB_REPOSITORY_VERIFICATION_FAILED",
            "message": "GitHub did not verify the requested repository and write permission.",
        }) from exc
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_BINDING_UNAVAILABLE"}) from exc

    now = datetime.now(timezone.utc)
    version = (existing.get("binding_version", 0) + 1) if existing else 1
    document = {
        "_id": key, "organization_id": organization_id, "project_id": project_id,
        "state": "verified", "installation_id": verified.installation_id,
        "repository_id": verified.repository_id, "repository_node_id": verified.repository_node_id,
        "owner": verified.owner, "name": verified.name, "full_name": verified.full_name,
        "default_branch": verified.default_branch, "contents_permission": verified.contents_permission,
        "private": verified.private, "binding_version": version,
        "verified_at": now, "updated_at": now,
        "verified_by_issuer": principal.issuer, "verified_by_subject": principal.subject,
        "created_at": existing.get("created_at", now) if existing else now,
    }
    try:
        if existing is None:
            await collection.insert_one(document)
        else:
            result = await collection.replace_one({
                "_id": key, "binding_version": payload.expected_version,
            }, document, upsert=False)
            if result.modified_count != 1:
                raise HTTPException(status_code=409, detail={"code": "REPOSITORY_BINDING_VERSION_CONFLICT"})
        await _audit(audit, principal, organization_id, project_id,
                     "nexus.repository_binding.bind", "success",
                     {"repository_id": verified.repository_id, "binding_version": version})
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail={"code": "REPOSITORY_BINDING_VERSION_CONFLICT"}) from exc
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_BINDING_UNAVAILABLE"}) from exc
    return {"binding": _public_binding(document)}


@router.delete(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/repository-binding",
    tags=["repository-binding"],
)
async def remove_repository_binding(
    payload: RemoveRepositoryBindingRequest,
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
):
    database, audit = await _owner_only(request, organization_id, project_id, principal)
    await _audit(audit, principal, organization_id, project_id,
                 "nexus.repository_binding.remove", "started",
                 {"binding_version": payload.expected_version})
    try:
        result = await database["nexus_repository_bindings"].delete_one({
            "_id": f"{organization_id}:{project_id}",
            "organization_id": organization_id, "project_id": project_id,
            "binding_version": payload.expected_version,
        })
        if result.deleted_count != 1:
            raise HTTPException(status_code=409, detail={"code": "REPOSITORY_BINDING_VERSION_CONFLICT"})
        await _audit(audit, principal, organization_id, project_id,
                     "nexus.repository_binding.remove", "success",
                     {"binding_version": payload.expected_version})
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "REPOSITORY_BINDING_UNAVAILABLE"}) from exc
    return {"removed": True, "binding_version": payload.expected_version}
