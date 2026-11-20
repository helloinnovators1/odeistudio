"""Fail-closed OIDC/JWKS access-token verification and tenant membership checks."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from odei_api.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)
bearer_credentials_dependency = Depends(bearer_scheme)
JWKS_CACHE_TTL_SECONDS = 300
JWKS_FETCH_TIMEOUT_SECONDS = 5.0
JWKS_MAX_BYTES = 1_000_000
JWKS_MAX_KEYS = 100
JWT_ACCESS_TOKEN_TYPES = {"at+jwt", "application/at+jwt"}


@dataclass(frozen=True)
class Principal:
    """Verified identity claims; organization access is resolved separately."""

    subject: str
    issuer: str
    client_id: str = ""
    token_id: str = ""
    scopes: frozenset[str] = frozenset()


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
        if urlsplit(jwks_url).scheme != "https":
            raise ValueError("JWKS endpoint must use HTTPS")
        response = await client.get(jwks_url, timeout=JWKS_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        content = getattr(response, "content", b"")
        if isinstance(content, (bytes, bytearray)) and len(content) > JWKS_MAX_BYTES:
            raise ValueError("Identity provider JWKS document exceeds the size limit")
        document = response.json()
        if not isinstance(document, dict) or not isinstance(document.get("keys"), list):
            raise TypeError("Identity provider returned an invalid JWKS document")
        if not document["keys"] or len(document["keys"]) > JWKS_MAX_KEYS:
            raise ValueError("Identity provider JWKS key count is invalid")
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
    if urlsplit(issuer).scheme != "https" or not urlsplit(issuer).netloc:
        raise ValueError("Identity issuer must be an HTTPS origin")
    if not audience.strip():
        raise ValueError("Identity audience is required")
    header = jwt.get_unverified_header(token)
    if header.get("typ") not in JWT_ACCESS_TOKEN_TYPES:
        raise jwt.InvalidTokenError("JWT is not explicitly typed as an OAuth access token")
    if header.get("alg") != "RS256":
        raise jwt.InvalidAlgorithmError("Only RS256 access tokens are accepted")
    key_id = header.get("kid")
    if not isinstance(key_id, str) or not key_id:
        raise jwt.InvalidTokenError("Token key identifier is missing")

    candidates = [
        key for key in jwks.get("keys", [])
        if (
            isinstance(key, dict)
            and key.get("kid") == key_id
            and key.get("kty") == "RSA"
            and key.get("alg") in (None, "RS256")
            and key.get("use") in (None, "sig")
            and (
                key.get("key_ops") is None
                or (
                    isinstance(key.get("key_ops"), list)
                    and "verify" in key["key_ops"]
                )
            )
        )
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
        options={"require": ["exp", "sub", "iat", "jti", "client_id"]},
    )
    subject = claims.get("sub")
    client_id = claims.get("client_id")
    token_id = claims.get("jti")
    scope_claim = claims.get("scope", "")
    if not isinstance(subject, str) or not subject.strip():
        raise jwt.InvalidTokenError("Token subject is invalid")
    if not isinstance(client_id, str) or not client_id.strip():
        raise jwt.InvalidTokenError("Token client_id is invalid")
    if not isinstance(token_id, str) or not token_id.strip():
        raise jwt.InvalidTokenError("Token jti is invalid")
    if not isinstance(scope_claim, str):
        raise jwt.InvalidTokenError("Token scope claim must be a space-delimited string")
    scopes = frozenset(scope_claim.split())
    return Principal(
        subject=subject,
        issuer=issuer,
        client_id=client_id,
        token_id=token_id,
        scopes=scopes,
    )


async def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = bearer_credentials_dependency,
) -> Principal:
    """FastAPI dependency for routes that require a trusted ODEI Identity token."""
    settings = get_settings()
    allowed_client_ids = {
        item.strip()
        for item in (settings.auth_allowed_client_ids or "").split(",")
        if item.strip()
    }
    if (
        not settings.auth_issuer
        or not settings.auth_audience
        or not settings.auth_jwks_url
        or not allowed_client_ids
    ):
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
        principal = verify_access_token(
            credentials.credentials,
            jwks=jwks,
            issuer=settings.auth_issuer,
            audience=settings.auth_audience,
        )
        if principal.client_id not in allowed_client_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "CLIENT_NOT_ALLOWED",
                    "message": "The access token was issued to an unapproved client.",
                },
            )
        return principal
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_ACCESS_TOKEN", "message": "The access token is invalid."},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (httpx.HTTPError, ValueError, TypeError, RuntimeError) as exc:
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
