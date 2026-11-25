from __future__ import annotations

import base64
from types import SimpleNamespace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

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
async def test_github_app_verifies_installation_and_write_repository_without_persisting_token():
    http = Http([
        Response(200, {"id": 77, "app_id": 42}),
        Response(201, {"token": "short-lived-secret", "expires_at": "soon"}),
        Response(200, {
            "id": 123, "node_id": "R_kgDOabc", "full_name": "Acme/Service",
            "name": "Service", "default_branch": "main", "private": True,
            "owner": {"login": "Acme"}, "permissions": {"contents": "write"},
        }),
    ])
    client = GitHubAppInstallationClient(
        app_id=42,
        private_key_b64=SimpleNamespace(get_secret_value=lambda: base64.b64encode(
            b"-----BEGIN PRIVATE KEY-----\\nnot-a-real-key\\n-----END PRIVATE KEY-----"
        ).decode()),
        http_client=http,
    )
    # Signing validates the PEM, so use a generated test key.
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    client.private_key_b64 = SimpleNamespace(
        get_secret_value=lambda: base64.b64encode(pem).decode(),
    )
    verified = await client.verify_repository(installation_id=77, owner="acme", name="service")
    assert verified.repository_id == 123
    assert verified.full_name == "Acme/Service"
    assert verified.default_branch == "main"
    assert verified.contents_permission == "write"
    assert all("short-lived-secret" not in str(call) for call in http.calls)


@pytest.mark.asyncio
async def test_github_app_rejects_installation_from_another_app():
    http = Http([Response(200, {"id": 77, "app_id": 999})])
    client = GitHubAppInstallationClient(
        app_id=42,
        private_key_b64=SimpleNamespace(get_secret_value=lambda: "invalid"),
        http_client=http,
    )
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
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
            "owner": {"login": "acme"}, "permissions": {"contents": "read"},
        }),
    ])
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
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
