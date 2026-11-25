from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from odei_api.services.github_app import (
    GitHubAppInstallationClient,
    GitHubRepositoryVerificationError,
)


class Response:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
    def json(self):
        return self.body


class Http:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)
    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_github_app_uses_ephemeral_installation_token_only_for_provider_request():
    http = Http([
        Response(200, {"id": 77, "app_id": 42}),
        Response(201, {"token": "short-lived-secret", "expires_at": "soon"}),
        Response(200, {
            "id": 123, "node_id": "R_kgDOabc", "full_name": "Acme/Service",
            "name": "Service", "default_branch": "main", "private": True,
            "owner": {"login": "Acme"}, "permissions": {"contents": "write", "pull_requests": "write"},
        }),
        Response(200, {
            "ref": "refs/heads/main",
            "object": {"type": "commit", "sha": "a" * 40},
        }),
    ])
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    client = GitHubAppInstallationClient(
        app_id=42,
        private_key_b64=SimpleNamespace(
            get_secret_value=lambda: base64.b64encode(pem).decode(),
        ),
        http_client=http,
    )
    verified = await client.verify_repository(installation_id=77, owner="acme", name="service")
    assert verified.repository_id == 123
    assert verified.full_name == "Acme/Service"
    assert verified.default_branch == "main"
    assert verified.default_branch_sha == "a" * 40
    assert verified.contents_permission == "write"
    assert http.calls[-1][2]["headers"]["Authorization"] == "Bearer short-lived-secret"
    assert all("short-lived-secret" not in url for _method, url, _kwargs in http.calls)
    assert all(
        "short-lived-secret" not in str(kwargs.get("json"))
        for _method, _url, kwargs in http.calls
    )
    assert "short-lived-secret" not in repr(verified)

@pytest.mark.asyncio
async def test_github_app_rejects_installation_from_another_app():
    http = Http([Response(200, {"id": 77, "app_id": 999})])
    client = GitHubAppInstallationClient(
        app_id=42,
        private_key_b64=SimpleNamespace(get_secret_value=lambda: "invalid"),
        http_client=http,
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    client.private_key_b64 = SimpleNamespace(get_secret_value=lambda: base64.b64encode(pem).decode())
    with pytest.raises(GitHubRepositoryVerificationError):
        await client.verify_repository(installation_id=77, owner="acme", name="service")


@pytest.mark.asyncio
async def test_github_app_rejects_repository_without_contents_write_permission():
    http = Http([
        Response(200, {"id": 77, "app_id": 42}),
        Response(201, {"token": "ephemeral"}),
        Response(200, {
            "id": 123, "node_id": "R_kgDOabc", "full_name": "acme/service",
            "name": "service", "default_branch": "main",
            "owner": {"login": "acme"}, "permissions": {"contents": "read", "pull_requests": "write"},
        }),
    ])
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    client = GitHubAppInstallationClient(
        app_id=42,
        private_key_b64=SimpleNamespace(get_secret_value=lambda: base64.b64encode(pem).decode()),
        http_client=http,
    )
    with pytest.raises(GitHubRepositoryVerificationError):
        await client.verify_repository(installation_id=77, owner="acme", name="service")
