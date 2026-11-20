"""Fail-closed OIDC/JWKS access-token verification and tenant membership checks."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from odei_api.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)
JWKS_CACHE_TTL_SECONDS = 300
JWKS_FETCH_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class Principal:
    """Verified identity claims; organization access is resolved separately."""

    subject: str
    issuer: str


async def load_jwks(request: Request, jwks_url: str) -> dict[str, Any]:
    """Fetch and cache a bounded JWKS document for the current API process."""
    state = request.app.state
    now = time.monotonic()
    cached = getattr(state, "jwks_cache", None)
    if cached and cached["expires_at"] > now:
        return cached["document"]

    lock = getattr(state, "jwks_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        state.jwks_lock = lock

    async with lock:
        now = time.monotonic()
        cached = getattr(state, "jwks_cache", None)
        if cached and cached["expires_at"] > now:
            return cached["document"]

        client = getattr(state, "http_client", None)
        if client is None:
            raise RuntimeError("Identity HTTP client is not initialized")
        response = await client.get(jwks_url, timeout=JWKS_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        document = response.json()
        if not isinstance(document, dict) or not isinstance(document.get("keys"), list):
            raise ValueError("Identity provider returned an invalid JWKS document")
        state.jwks_cache = {
            "document": document,
            "expires_at": now + JWKS_CACHE_TTL_SECONDS,
        }
        return document


def verify_access_token(
    token: str,
    *,
    jwks: dict[str, Any],
    issuer: str,
    audience: str,
) -> Principal:
    """Verify signature and mandatory OIDC claims; only RS256 is accepted."""
    header = jwt.get_unverified_header(token)
    if header.get("alg") != "RS256":
        raise jwt.InvalidAlgorithmError("Only RS256 access tokens are accepted")
    key_id = header.get("kid")
    if not isinstance(key_id, str) or not key_id:
        raise jwt.InvalidTokenError("Token key identifier is missing")

    candidates = [
        key for key in jwks.get("keys", [])
        if isinstance(key, dict) and key.get("kid") == key_id and key.get("kty") == "RSA"
    ]
    if len(candidates) != 1:
        raise jwt.InvalidTokenError("Signing key is unknown or ambiguous")
    signing_key = jwt.PyJWK.from_dict(candidates[0], algorithm="RS256").key
    claims = jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
        options={"require": ["exp", "sub"]},
    )
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise jwt.InvalidTokenError("Token subject is invalid")
    return Principal(subject=subject, issuer=issuer)


async def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    """FastAPI dependency for routes that require a trusted ODEI Identity token."""
    settings = get_settings()
    if not settings.auth_issuer or not settings.auth_audience or not settings.auth_jwks_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "AUTH_NOT_CONFIGURED", "message": "Trusted identity is not configured."},
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "A bearer access token is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        jwks = await load_jwks(request, settings.auth_jwks_url)
        return verify_access_token(
            credentials.credentials,
            jwks=jwks,
            issuer=settings.auth_issuer,
            audience=settings.auth_audience,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_ACCESS_TOKEN", "message": "The access token is invalid."},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "IDENTITY_PROVIDER_UNAVAILABLE", "message": "Identity verification is temporarily unavailable."},
        ) from exc


async def require_organization_membership(
    memberships: Any,
    *,
    principal: Principal,
    organization_id: str,
) -> dict[str, Any]:
    """Resolve membership from server-side storage; never trust client role claims."""
    if not organization_id.strip():
        raise ValueError("organization_id is required")
    membership = await memberships.find_one(
        {
            "organization_id": organization_id,
            "user_id": principal.subject,
            "status": "active",
        }
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ORGANIZATION_ACCESS_DENIED", "message": "Active organization membership is required."},
        )
    return membership
