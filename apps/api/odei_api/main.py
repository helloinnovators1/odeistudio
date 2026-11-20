"""FastAPI application entry point and dependency lifecycle."""
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from odei_api.config import get_settings
from odei_api.mongo_client import create_mongo_client

logger = logging.getLogger(__name__)
settings = get_settings()


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
