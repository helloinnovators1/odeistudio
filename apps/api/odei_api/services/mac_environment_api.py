"""Authenticated, audited API for MAC environment governance."""
from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from odei_api.config import get_settings
from odei_api.security.auth import Principal, get_current_principal
from odei_api.security.mac_rbac import require_mac_permission, resolve_mac_access
from odei_api.services.mac_environments import (
    MacEnvironmentConflict,
    MacEnvironmentError,
    MacEnvironmentNotFound,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/mac/environments", tags=["mac"])
principal_dependency = Depends(get_current_principal)


def _actor_id(principal: Principal) -> str:
    """Bind lifecycle authorship to the complete verified issuer/subject pair."""
    identity = f"{principal.issuer}\0{principal.subject}".encode()
    return "oidc-" + hashlib.sha256(identity).hexdigest()


class EnvironmentDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: dict[str, Any]
    change_summary: StrictStr = Field(min_length=1, max_length=500)
    expected_latest_version: int | None = Field(default=None, ge=1)


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    expected_latest_version: int = Field(ge=1)


class PromotionRequest(RevisionRequest):
    expected_active_version: int = Field(ge=0)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_version: int = Field(ge=1)
    expected_latest_version: int = Field(ge=1)
    change_summary: StrictStr = Field(min_length=1, max_length=500)


async def _context(request: Request, principal: Principal, permission: str, environment: str):
    settings = get_settings()
    if not settings.mac_platform_operators_json.strip():
        raise HTTPException(status_code=503, detail={
            "code": "MAC_OPERATOR_REGISTRY_NOT_CONFIGURED",
            "message": "Platform operator assignments are not configured.",
        })
    try:
        access = resolve_mac_access(
            settings.mac_platform_operators_json,
            issuer=principal.issuer,
            subject=principal.subject,
        )
        require_mac_permission(access, permission)
    except HTTPException as exc:
        if exc.status_code == 403:
            audit = getattr(request.app.state, "audit_event_store", None)
            if audit is None:
                raise HTTPException(status_code=503, detail={
                    "code": "AUDIT_STORE_UNAVAILABLE",
                    "message": "Authorization decisions cannot be durably audited.",
                }) from exc
            await _audit(audit, principal, "mac.environment.authorization", environment, "denied",
                         {"required_permission": permission})
        raise
    except ValueError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "MAC_OPERATOR_REGISTRY_INVALID",
            "message": "Platform operator assignments are unavailable.",
        }) from exc
    database = getattr(request.app.state, "mongo_database", None)
    audit = getattr(request.app.state, "audit_event_store", None)
    if database is None or audit is None:
        raise HTTPException(status_code=503, detail={
            "code": "MAC_STORAGE_UNAVAILABLE",
            "message": "MAC environment and audit storage are unavailable.",
        })
    store = getattr(request.app.state, "mac_environment_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={
            "code": "MAC_STORAGE_UNAVAILABLE",
            "message": "MAC environment storage is unavailable.",
        })
    return store, audit


async def _audit(audit, principal: Principal, action: str, environment: str,
                 outcome: str, metadata: dict[str, Any] | None = None) -> None:
    try:
        await audit.append(
            organization_id="platform",
            actor_issuer=principal.issuer,
            actor_subject=principal.subject,
            action=action,
            target_type="mac_environment",
            target_id=environment,
            outcome=outcome,
            request_id=uuid4().hex,
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.error("MAC environment audit append failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail={
            "code": "AUDIT_STORE_UNAVAILABLE",
            "message": "The MAC action could not be durably audited.",
        }) from exc


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, MacEnvironmentNotFound):
        return HTTPException(status_code=404, detail={"code": "MAC_ENVIRONMENT_NOT_FOUND", "message": str(exc)})
    if isinstance(exc, MacEnvironmentConflict):
        return HTTPException(status_code=409, detail={"code": "MAC_ENVIRONMENT_CONFLICT", "message": str(exc)})
    if isinstance(exc, MacEnvironmentError):
        return HTTPException(status_code=422, detail={"code": "MAC_ENVIRONMENT_INVALID", "message": str(exc)})
    logger.error("Unexpected MAC environment operation failure (%s)", type(exc).__name__)
    return HTTPException(status_code=503, detail={"code": "MAC_ENVIRONMENT_UNAVAILABLE", "message": "MAC environment operation is unavailable."})


@router.get("/{environment}")
async def read_environment(environment: str, request: Request,
                           principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:read", environment)
    try:
        record = await store.get(environment)
    except (MacEnvironmentError, MacEnvironmentNotFound, MacEnvironmentConflict) as exc:
        await _audit(audit, principal, "mac.environment.read", environment, "denied")
        raise _translate(exc) from exc
    await _audit(audit, principal, "mac.environment.read", environment, "success",
                 {"latest_version": record["latest_version"], "active_version": record["active_version"]})
    return {"environment": record}


@router.post("/{environment}/drafts", status_code=201)
async def create_environment_draft(environment: str, payload: EnvironmentDraftRequest,
                                   request: Request, principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:environment:manage", environment)
    try:
        if payload.expected_latest_version is None:
            result = await store.create_draft(
                environment=environment, actor=_actor_id(principal),
                config=payload.config, change_summary=payload.change_summary,
            )
        else:
            result = await store.create_revision(
                environment=environment,
                expected_latest_version=payload.expected_latest_version,
                actor=_actor_id(principal), config=payload.config,
                change_summary=payload.change_summary,
            )
    except Exception as exc:
        await _audit(audit, principal, "mac.environment.draft.create", environment, "failure")
        if isinstance(exc, (MacEnvironmentError, MacEnvironmentNotFound, MacEnvironmentConflict)):
            raise _translate(exc) from exc
        raise
    await _audit(audit, principal, "mac.environment.draft.create", environment, "success",
                 {"version": result["version"]})
    return {"revision": result}


@router.put("/{environment}/drafts/{version}")
async def update_environment_draft(environment: str, version: int,
                                   payload: EnvironmentDraftRequest, request: Request,
                                   principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:environment:manage", environment)
    if payload.expected_latest_version is None:
        raise HTTPException(status_code=422, detail={"code": "EXPECTED_VERSION_REQUIRED", "message": "expected_latest_version is required."})
    try:
        result = await store.update_draft(
            environment=environment, version=version,
            expected_latest_version=payload.expected_latest_version,
            actor=_actor_id(principal), config=payload.config,
            change_summary=payload.change_summary,
        )
    except (MacEnvironmentError, MacEnvironmentNotFound, MacEnvironmentConflict) as exc:
        await _audit(audit, principal, "mac.environment.draft.update", environment, "failure")
        raise _translate(exc) from exc
    await _audit(audit, principal, "mac.environment.draft.update", environment, "success", {"version": version})
    return {"environment": result}


@router.post("/{environment}/submit")
async def submit_environment(environment: str, payload: RevisionRequest,
                             request: Request, principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:environment:manage", environment)
    try:
        result = await store.submit_for_approval(
            environment=environment, version=payload.version,
            expected_latest_version=payload.expected_latest_version, actor=_actor_id(principal),
        )
    except (MacEnvironmentError, MacEnvironmentNotFound, MacEnvironmentConflict) as exc:
        await _audit(audit, principal, "mac.environment.submit", environment, "failure")
        raise _translate(exc) from exc
    await _audit(audit, principal, "mac.environment.submit", environment, "success", {"version": payload.version})
    return {"environment": result}


@router.post("/{environment}/approve")
async def approve_environment(environment: str, payload: RevisionRequest,
                              request: Request, principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:deployments:approve", environment)
    try:
        result = await store.approve(
            environment=environment, version=payload.version,
            expected_latest_version=payload.expected_latest_version, actor=_actor_id(principal),
        )
    except (MacEnvironmentError, MacEnvironmentNotFound, MacEnvironmentConflict) as exc:
        await _audit(audit, principal, "mac.environment.approve", environment, "failure")
        raise _translate(exc) from exc
    await _audit(audit, principal, "mac.environment.approve", environment, "success", {"version": payload.version})
    return {"environment": result}


@router.post("/{environment}/promote")
async def promote_environment(environment: str, payload: PromotionRequest,
                              request: Request, principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:deployments:approve", environment)
    try:
        result = await store.promote(
            environment=environment, version=payload.version,
            expected_active_version=payload.expected_active_version,
            expected_latest_version=payload.expected_latest_version, actor=_actor_id(principal),
        )
    except (MacEnvironmentError, MacEnvironmentNotFound, MacEnvironmentConflict) as exc:
        await _audit(audit, principal, "mac.environment.promote", environment, "failure")
        raise _translate(exc) from exc
    await _audit(audit, principal, "mac.environment.promote", environment, "success", {"version": payload.version})
    return {"environment": result}


@router.post("/{environment}/rollback-drafts", status_code=201)
async def rollback_environment(environment: str, payload: RollbackRequest,
                               request: Request, principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:environment:manage", environment)
    try:
        result = await store.create_rollback_draft(
            environment=environment, target_version=payload.target_version,
            expected_latest_version=payload.expected_latest_version,
            actor=_actor_id(principal), change_summary=payload.change_summary,
        )
    except (MacEnvironmentError, MacEnvironmentNotFound, MacEnvironmentConflict) as exc:
        await _audit(audit, principal, "mac.environment.rollback_draft", environment, "failure")
        raise _translate(exc) from exc
    await _audit(audit, principal, "mac.environment.rollback_draft", environment, "success",
                 {"version": result["version"], "rollback_of": payload.target_version})
    return {"revision": result}
