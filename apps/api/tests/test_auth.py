import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import SecretStr

from odei_api.config import Settings
from odei_api.security.auth import (
    Principal,
    get_current_principal,
    require_organization_membership,
    verify_access_token,
)


def make_signing_material():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "key-1", "use": "sig", "alg": "RS256"})
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "user-123",
        "iss": "https://identity.example.test/",
        "aud": "odei-studio-api",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "key-1"})
    return private_key, {"keys": [public_jwk]}, token, payload


def test_verify_access_token_accepts_valid_issuer_audience_and_signature():
    _, jwks, token, _ = make_signing_material()
    principal = verify_access_token(
        token,
        jwks=jwks,
        issuer="https://identity.example.test/",
        audience="odei-studio-api",
    )
    assert principal == Principal(
        subject="user-123",
        issuer="https://identity.example.test/",
    )


@pytest.mark.parametrize(
    ("issuer", "audience"),
    [
        ("https://attacker.example/", "odei-studio-api"),
        ("https://identity.example.test/", "another-api"),
    ],
)
def test_verify_access_token_rejects_wrong_issuer_or_audience(issuer, audience):
    _, jwks, token, _ = make_signing_material()
    with pytest.raises(jwt.PyJWTError):
        verify_access_token(token, jwks=jwks, issuer=issuer, audience=audience)


def test_verify_access_token_rejects_expired_token():
    private_key, jwks, _, payload = make_signing_material()
    payload["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "key-1"})
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_access_token(
            token,
            jwks=jwks,
            issuer="https://identity.example.test/",
            audience="odei-studio-api",
        )


def test_verify_access_token_rejects_unknown_kid():
    private_key, jwks, _, payload = make_signing_material()
    token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "other-key"})
    with pytest.raises(jwt.InvalidTokenError):
        verify_access_token(
            token,
            jwks=jwks,
            issuer="https://identity.example.test/",
            audience="odei-studio-api",
        )


def test_verify_access_token_rejects_non_rs256_algorithm():
    _, jwks, _, payload = make_signing_material()
    token = jwt.encode(payload, "not-a-real-key", algorithm="HS256", headers={"kid": "key-1"})
    with pytest.raises(jwt.InvalidAlgorithmError):
        verify_access_token(
            token,
            jwks=jwks,
            issuer="https://identity.example.test/",
            audience="odei-studio-api",
        )


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class FakeHttpClient:
    def __init__(self, body):
        self.body = body
        self.requested_url = None

    async def get(self, url, timeout):
        self.requested_url = url
        return FakeResponse(self.body)


@pytest.mark.asyncio
async def test_current_principal_loads_jwks_and_verifies_bearer(monkeypatch):
    _, jwks, token, _ = make_signing_material()
    settings = Settings(
        auth_issuer="https://identity.example.test/",
        auth_audience="odei-studio-api",
        auth_jwks_url="https://identity.example.test/.well-known/jwks.json",
    )
    monkeypatch.setattr("odei_api.security.auth.get_settings", lambda: settings)
    http_client = FakeHttpClient(jwks)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                http_client=http_client,
                jwks_cache=None,
                jwks_lock=asyncio.Lock(),
            )
        )
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    principal = await get_current_principal(request, credentials)
    assert principal.subject == "user-123"
    assert http_client.requested_url == settings.auth_jwks_url


@pytest.mark.asyncio
async def test_current_principal_fails_closed_when_oidc_is_not_configured(monkeypatch):
    monkeypatch.setattr(
        "odei_api.security.auth.get_settings",
        lambda: Settings(auth_issuer=None, auth_audience=None, auth_jwks_url=None),
    )
    with pytest.raises(HTTPException) as error:
        await get_current_principal(SimpleNamespace(), None)
    assert error.value.status_code == 503
    assert error.value.detail["code"] == "AUTH_NOT_CONFIGURED"


class FakeMembershipCollection:
    def __init__(self, membership):
        self.membership = membership
        self.query = None

    async def find_one(self, query):
        self.query = query
        return self.membership


@pytest.mark.asyncio
async def test_membership_lookup_uses_verified_subject_and_tenant():
    membership = {"organization_id": "org-1", "user_id": "user-123", "role": "developer"}
    collection = FakeMembershipCollection(membership)
    result = await require_organization_membership(
        collection,
        principal=Principal(subject="user-123", issuer="https://identity.example.test/"),
        organization_id="org-1",
    )
    assert result == membership
    assert collection.query == {
        "organization_id": "org-1",
        "user_id": "user-123",
        "status": "active",
    }


@pytest.mark.asyncio
async def test_membership_lookup_denies_inactive_or_missing_membership():
    collection = FakeMembershipCollection(None)
    with pytest.raises(HTTPException) as error:
        await require_organization_membership(
            collection,
            principal=Principal(subject="user-123", issuer="https://identity.example.test/"),
            organization_id="org-other",
        )
    assert error.value.status_code == 403
