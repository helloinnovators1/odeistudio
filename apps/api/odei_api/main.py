"""FastAPI application entry point and dependency lifecycle."""
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from odei_api.config import get_settings
from odei_api.model_client import ModelConfigurationError, get_openai_client
from odei_api.mongo_client import create_mongo_client
from odei_api.security.auth import (
    Principal,
    get_current_principal,
    require_organization_membership,
)
from odei_api.services.audit_store import MongoAuditEventStore
from odei_api.services.planning import PlanningError, create_task_plan

logger = logging.getLogger(__name__)
settings = get_settings()
auth_principal_dependency = Depends(get_current_principal)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Own the optional MongoDB client for the lifetime of the API process."""
    client = None
    database_name = None
    http_client = httpx.AsyncClient(timeout=5.0)
    application.state.http_client = http_client
    application.state.jwks_cache = None
    application.state.jwks_lock = asyncio.Lock()
    try:
        if settings.mongodb_uri is not None and settings.mongodb_uri.get_secret_value():
            client, database_name = create_mongo_client(settings)
        application.state.mongo_client = client
        application.state.mongo_database = client[database_name] if client and database_name else None
        application.state.audit_event_store = None
        if application.state.mongo_database is not None:
            audit_store = MongoAuditEventStore(application.state.mongo_database["audit_events"])
            await audit_store.initialize()
            application.state.audit_event_store = audit_store
        yield
    finally:
        if client is not None:
            await client.close()
        await http_client.aclose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API foundation for ODEI Studio and ODEI NEXUS.",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
    lifespan=lifespan,
)

# Keep origins empty until the deployment's exact web origins are configured.
# Wildcard CORS with credentials is deliberately not enabled.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"service": "odei-studio-api", "status": "running"}


@app.get(f"{settings.api_prefix}/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    """Process liveness only; does not claim database/provider readiness."""
    return {"status": "alive"}


@app.get(f"{settings.api_prefix}/health/ready", tags=["health"])
async def readiness(request: Request) -> dict[str, object]:
    """Readiness includes a bounded live ping; missing Mongo is not ready."""
    client = getattr(request.app.state, "mongo_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": {"mongodb": "not_configured"}},
        )
    try:
        await client.admin.command("ping")
    except Exception as exc:
        logger.warning("MongoDB readiness check failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": {"mongodb": "unavailable"}},
        ) from exc
    return {"status": "ready", "checks": {"mongodb": "ok"}}


@app.get(f"{settings.api_prefix}/auth/me", tags=["auth"])
async def current_identity(principal: Principal = auth_principal_dependency) -> dict[str, str]:
    """Return only the verified caller identity; no client-supplied roles or tenant claims."""
    return {"subject": principal.subject, "issuer": principal.issuer}


async def _append_membership_audit(
    request: Request,
    *,
    principal: Principal,
    organization_id: str,
    outcome: str,
    reason: str | None = None,
) -> None:
    """Persist membership decisions before returning them; fail closed on audit errors."""
    store = getattr(request.app.state, "audit_event_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AUDIT_STORE_UNAVAILABLE",
                "message": "Authorization audit storage is not available.",
            },
        )
    try:
        await store.append(
            organization_id=organization_id,
            actor_issuer=principal.issuer,
            actor_subject=principal.subject,
            action="organization.membership.read",
            target_type="organization",
            target_id=organization_id,
            outcome=outcome,
            request_id=uuid4().hex,
            metadata={"reason": reason} if reason else {},
        )
    except Exception as exc:
        logger.error("Membership authorization audit append failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AUDIT_STORE_UNAVAILABLE",
                "message": "Authorization audit storage is temporarily unavailable.",
            },
        ) from exc



class NexusPlanRequest(BaseModel):
    """Bounded request for a plan; context is user-supplied and treated as untrusted."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task: str = Field(min_length=1, max_length=8_000)
    project_context: str = Field(default="", max_length=24_000)
    cloud_model_consent: StrictBool


async def _append_nexus_plan_audit(
    request: Request,
    *,
    principal: Principal,
    organization_id: str,
    plan_id: str,
    outcome: str,
    model: str | None = None,
) -> None:
    """Record plan outcomes without storing task text, repository context or plan content."""
    store = getattr(request.app.state, "audit_event_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is not available."},
        )
    metadata = {"model": model} if model else {}
    try:
        await store.append(
            organization_id=organization_id,
            actor_issuer=principal.issuer,
            actor_subject=principal.subject,
            action="nexus.plan.create",
            target_type="nexus_plan",
            target_id=plan_id,
            outcome=outcome,
            request_id=uuid4().hex,
            metadata=metadata,
        )
    except Exception as exc:
        logger.error("NEXUS plan audit append failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is temporarily unavailable."},
        ) from exc


@app.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/nexus/plan",
    tags=["nexus"],
)
async def create_nexus_plan(
    payload: NexusPlanRequest,
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    principal: Principal = auth_principal_dependency,
) -> dict[str, str]:
    """Create a plan for an active organization member after explicit cloud-model consent.

    This endpoint does not read local files, execute tools, write project files or
    authorize implementation. Repository context is caller-supplied, bounded and
    treated as untrusted input.
    """
    if organization_id != organization_id.strip():
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_ORGANIZATION_ID", "message": "Organization ID is invalid."},
        )
    if payload.cloud_model_consent is not True:
        raise HTTPException(
            status_code=400,
            detail={"code": "CLOUD_MODEL_CONSENT_REQUIRED", "message": "Explicit consent is required before sending task data to the cloud model."},
        )
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "MEMBERSHIP_STORE_UNAVAILABLE", "message": "Organization membership storage is not configured."},
        )
    try:
        await require_organization_membership(
            database["organization_memberships"],
            principal=principal,
            organization_id=organization_id,
        )
    except HTTPException as exc:
        if exc.status_code == 403:
            await _append_membership_audit(
                request,
                principal=principal,
                organization_id=organization_id,
                outcome="denied",
                reason="active_membership_required",
            )
        raise
    except PyMongoError as exc:
        logger.warning("NEXUS organization membership lookup failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "MEMBERSHIP_STORE_UNAVAILABLE", "message": "Organization membership storage is temporarily unavailable."},
        ) from exc

    plan_id = uuid4().hex
    try:
        client, model = get_openai_client()
        plan = await run_in_threadpool(
            create_task_plan,
            client,
            model=model,
            task=payload.task,
            project_context=payload.project_context,
            cloud_model_consent=True,
        )
    except ModelConfigurationError as exc:
        await _append_nexus_plan_audit(
            request, principal=principal, organization_id=organization_id,
            plan_id=plan_id, outcome="failure",
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "MODEL_NOT_CONFIGURED", "message": "The NEXUS model provider is not configured."},
        ) from exc
    except (PlanningError, ValueError) as exc:
        await _append_nexus_plan_audit(
            request, principal=principal, organization_id=organization_id,
            plan_id=plan_id, outcome="failure",
        )
        raise HTTPException(
            status_code=502,
            detail={"code": "NEXUS_PLANNING_FAILED", "message": "NEXUS could not produce a usable plan."},
        ) from exc
    except Exception as exc:
        logger.warning("NEXUS planning provider failed: %s", type(exc).__name__)
        await _append_nexus_plan_audit(
            request, principal=principal, organization_id=organization_id,
            plan_id=plan_id, outcome="failure",
        )
        raise HTTPException(
            status_code=502,
            detail={"code": "NEXUS_PROVIDER_UNAVAILABLE", "message": "The NEXUS planning provider is temporarily unavailable."},
        ) from exc

    await _append_nexus_plan_audit(
        request,
        principal=principal,
        organization_id=organization_id,
        plan_id=plan_id,
        outcome="success",
        model=plan.model,
    )
    return {"plan_id": plan_id, "organization_id": organization_id, "model": plan.model, "plan": plan.text}


@app.get(f"{settings.api_prefix}/organizations/{{organization_id}}/membership", tags=["organizations"])
async def current_organization_membership(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    principal: Principal = auth_principal_dependency,
) -> dict[str, str]:
    """Return the caller's active membership, resolved only from trusted server-side storage."""
    if organization_id != organization_id.strip():
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_ORGANIZATION_ID", "message": "Organization ID is invalid."},
        )
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MEMBERSHIP_STORE_UNAVAILABLE",
                "message": "Organization membership storage is not configured.",
            },
        )
    try:
        membership = await require_organization_membership(
            database["organization_memberships"],
            principal=principal,
            organization_id=organization_id,
        )
    except HTTPException as exc:
        if exc.status_code == 403:
            await _append_membership_audit(
                request,
                principal=principal,
                organization_id=organization_id,
                outcome="denied",
                reason="active_membership_required",
            )
        raise
    except PyMongoError as exc:
        logger.warning("Organization membership lookup failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MEMBERSHIP_STORE_UNAVAILABLE",
                "message": "Organization membership storage is temporarily unavailable.",
            },
        ) from exc

    role = membership.get("role") if isinstance(membership, dict) else None
    if not isinstance(role, str) or not role.strip():
        await _append_membership_audit(
            request,
            principal=principal,
            organization_id=organization_id,
            outcome="failure",
            reason="membership_record_invalid",
        )
        logger.error("Organization membership record has no valid role")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MEMBERSHIP_RECORD_INVALID",
                "message": "Organization membership data is not valid.",
            },
        )
    await _append_membership_audit(
        request,
        principal=principal,
        organization_id=organization_id,
        outcome="success",
    )
    return {"organization_id": organization_id, "role": role}
