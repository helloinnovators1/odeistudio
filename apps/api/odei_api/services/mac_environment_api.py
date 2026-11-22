"""Authenticated, audited API for MAC environment governance."""
from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from odei_api.config import get_settings
from odei_api.security.auth import Principal, get_current_principal
from odei_api.security.mac_rbac import require_mac_permission, resolve_mac_access
from odei_api.services.mac_deployments import (
    MacDeploymentConflict,
    MacDeploymentError,
    MacDeploymentNotFound,
)
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
    expected_latest_version: StrictInt | None = Field(default=None, ge=1)


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: StrictInt = Field(ge=1)
    expected_latest_version: StrictInt = Field(ge=1)


class PromotionRequest(RevisionRequest):
    expected_active_version: StrictInt = Field(ge=0)


class DeploymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: StrictInt = Field(ge=1)
    provider: StrictStr = Field(min_length=2, max_length=64)
    idempotency_key: StrictStr = Field(min_length=8, max_length=128)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_version: StrictInt = Field(ge=1)
    expected_latest_version: StrictInt = Field(ge=1)
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
                 outcome: str, metadata: dict[str, Any] | None = None, session: Any | None = None) -> None:
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
            session=session,
        )
    except Exception as exc:
        logger.error("MAC environment audit append failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail={
            "code": "AUDIT_STORE_UNAVAILABLE",
            "message": "The MAC action could not be durably audited.",
        }) from exc


async def _mutate_with_audit(request: Request, store: Any, audit: Any,
                             principal: Principal, action: str, environment_name: str,
                             method: str, **arguments: Any) -> Any:
    """Commit a MAC lifecycle mutation and its success audit event atomically."""
    database = getattr(request.app.state, "mongo_database", None)
    client = getattr(database, "client", None)
    operation = getattr(store, method)
    start_session = getattr(client, "start_session", None)
    if not callable(start_session):
        # MAC mutations change privileged deployment state. Never commit the
        # state change separately from its success audit record.
        raise HTTPException(status_code=503, detail={
            "code": "TRANSACTIONAL_AUDIT_UNAVAILABLE",
            "message": "MAC mutations require MongoDB transaction support; no change was applied.",
        })
    async with client.start_session() as session:
        async def transaction(active_session):
            result = await operation(**arguments, session=active_session)
            metadata = {"version": result.get("version")} if isinstance(result, dict) and "version" in result else {}
            await _audit(audit, principal, action, environment_name, "success", metadata, session=active_session)
            return result
        return await session.with_transaction(transaction)


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, MacDeploymentNotFound):
        return HTTPException(status_code=404, detail={"code": "MAC_DEPLOYMENT_NOT_FOUND", "message": str(exc)})
    if isinstance(exc, MacDeploymentConflict):
        return HTTPException(status_code=409, detail={"code": "MAC_DEPLOYMENT_CONFLICT", "message": str(exc)})
    if isinstance(exc, MacDeploymentError):
        return HTTPException(status_code=422, detail={"code": "MAC_DEPLOYMENT_INVALID", "message": str(exc)})
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
    except Exception as exc:
        await _audit(audit, principal, "mac.environment.read", environment, "failure")
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
            result = await _mutate_with_audit(
                request, store, audit, principal, "mac.environment.draft.create",
                environment, "create_draft", environment=environment,
                actor=_actor_id(principal), config=payload.config,
                change_summary=payload.change_summary,
            )
        else:
            result = await _mutate_with_audit(
                request, store, audit, principal, "mac.environment.draft.create",
                environment, "create_revision", environment=environment,
                expected_latest_version=payload.expected_latest_version,
                actor=_actor_id(principal), config=payload.config,
                change_summary=payload.change_summary,
            )
    except Exception as exc:
        await _audit(audit, principal, "mac.environment.draft.create", environment, "failure")
        raise _translate(exc) from exc
    return {"revision": result}


@router.put("/{environment}/drafts/{version}")
async def update_environment_draft(environment: str, version: int,
                                   payload: EnvironmentDraftRequest, request: Request,
                                   principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:environment:manage", environment)
    if payload.expected_latest_version is None:
        raise HTTPException(status_code=422, detail={"code": "EXPECTED_VERSION_REQUIRED", "message": "expected_latest_version is required."})
    try:
        result = await _mutate_with_audit(
            request, store, audit, principal, "mac.environment.draft.update",
            environment, "update_draft", environment=environment, version=version,
            expected_latest_version=payload.expected_latest_version,
            actor=_actor_id(principal), config=payload.config,
            change_summary=payload.change_summary,
        )
    except Exception as exc:
        await _audit(audit, principal, "mac.environment.draft.update", environment, "failure")
        raise _translate(exc) from exc
    return {"environment": result}


@router.post("/{environment}/submit")
async def submit_environment(environment: str, payload: RevisionRequest,
                             request: Request, principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:environment:manage", environment)
    try:
        result = await _mutate_with_audit(
            request, store, audit, principal, "mac.environment.submit",
            environment, "submit_for_approval", environment=environment,
            version=payload.version, expected_latest_version=payload.expected_latest_version,
            actor=_actor_id(principal),
        )
    except Exception as exc:
        await _audit(audit, principal, "mac.environment.submit", environment, "failure")
        raise _translate(exc) from exc
    return {"environment": result}


@router.post("/{environment}/approve")
async def approve_environment(environment: str, payload: RevisionRequest,
                              request: Request, principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:deployments:approve", environment)
    try:
        result = await _mutate_with_audit(
            request, store, audit, principal, "mac.environment.approve",
            environment, "approve", environment=environment, version=payload.version,
            expected_latest_version=payload.expected_latest_version,
            actor=_actor_id(principal),
        )
    except Exception as exc:
        await _audit(audit, principal, "mac.environment.approve", environment, "failure")
        raise _translate(exc) from exc
    return {"environment": result}


@router.post("/{environment}/promote")
async def promote_environment(environment: str, payload: PromotionRequest,
                              request: Request, principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:deployments:approve", environment)
    try:
        result = await _mutate_with_audit(
            request, store, audit, principal, "mac.environment.promote",
            environment, "promote", environment=environment, version=payload.version,
            expected_active_version=payload.expected_active_version,
            expected_latest_version=payload.expected_latest_version,
            actor=_actor_id(principal),
        )
    except Exception as exc:
        await _audit(audit, principal, "mac.environment.promote", environment, "failure")
        raise _translate(exc) from exc
    return {"environment": result}


@router.post("/{environment}/rollback-drafts", status_code=201)
async def rollback_environment(environment: str, payload: RollbackRequest,
                               request: Request, principal: Principal = principal_dependency):
    store, audit = await _context(request, principal, "mac:environment:manage", environment)
    try:
        result = await _mutate_with_audit(
            request, store, audit, principal, "mac.environment.rollback_draft",
            environment, "create_rollback_draft", environment=environment,
            target_version=payload.target_version,
            expected_latest_version=payload.expected_latest_version,
            actor=_actor_id(principal), change_summary=payload.change_summary,
        )
    except Exception as exc:
        await _audit(audit, principal, "mac.environment.rollback_draft", environment, "failure")
        raise _translate(exc) from exc
    return {"revision": result}


@router.post("/{environment}/deployments", status_code=202)
async def request_environment_deployment(
    environment: str, payload: DeploymentRequest, request: Request,
    principal: Principal = principal_dependency,
):
    _environment_store, audit = await _context(
        request, principal, "mac:deployments:request", environment
    )
    deployment_store = getattr(request.app.state, "mac_deployment_store", None)
    if deployment_store is None:
        raise HTTPException(status_code=503, detail={
            "code": "MAC_DEPLOYMENT_STORAGE_UNAVAILABLE",
            "message": "MAC deployment attempt storage is unavailable.",
        })
    try:
        attempt = await _mutate_with_audit(
            request, deployment_store, audit, principal,
            "mac.deployment.request", environment, "create_attempt",
            environment=environment, version=payload.version,
            provider=payload.provider, idempotency_key=payload.idempotency_key,
            actor=_actor_id(principal),
        )
    except Exception as exc:
        await _audit(audit, principal, "mac.deployment.request", environment, "failure")
        raise _translate(exc) from exc
    return {"deployment": attempt}


@router.get("/{environment}/deployments/{attempt_id}")
async def read_environment_deployment(
    environment: str, attempt_id: str, request: Request,
    principal: Principal = principal_dependency,
):
    _environment_store, audit = await _context(request, principal, "mac:read", environment)
    deployment_store = getattr(request.app.state, "mac_deployment_store", None)
    if deployment_store is None:
        raise HTTPException(status_code=503, detail={
            "code": "MAC_DEPLOYMENT_STORAGE_UNAVAILABLE",
            "message": "MAC deployment attempt storage is unavailable.",
        })
    try:
        attempt = await deployment_store.get(attempt_id)
        if attempt.get("environment") != environment:
            raise MacDeploymentNotFound("Deployment attempt does not exist")
    except Exception as exc:
        await _audit(audit, principal, "mac.deployment.read", environment, "failure")
        raise _translate(exc) from exc
    await _audit(audit, principal, "mac.deployment.read", environment, "success",
                 {"attempt_id": attempt_id, "state": attempt.get("state")})
    return {"deployment": attempt}
