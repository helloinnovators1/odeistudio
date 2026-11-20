"""FastAPI application entry point and dependency lifecycle."""
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError

from odei_api.config import get_settings
from odei_api.mongo_client import create_mongo_client
from odei_api.security.auth import (
    Principal,
    get_current_principal,
    require_organization_membership,
)

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
    if settings.mongodb_uri is not None and settings.mongodb_uri.get_secret_value():
        client, database_name = create_mongo_client(settings)
    application.state.mongo_client = client
    application.state.mongo_database = client[database_name] if client and database_name else None
    try:
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
    except HTTPException:
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

    role = membership.get("role")
    if not isinstance(role, str) or not role.strip():
        logger.error("Organization membership record has no valid role")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MEMBERSHIP_RECORD_INVALID",
                "message": "Organization membership data is not valid.",
            },
        )
    return {"organization_id": organization_id, "role": role}
