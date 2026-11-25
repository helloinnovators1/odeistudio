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
    async def delete(self, url, **kwargs):
        self.calls.append(("DELETE", url, kwargs))
        return self.responses.pop(0)
    async def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
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
async def test_worker_commit_is_based_on_pinned_head_and_creates_review_pr_without_merging(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("new workspace", encoding="utf-8")
    http = Http([
        Response(200, {"id": 77, "app_id": 42}),
        Response(201, {"token": "ephemeral-worker-token"}),
        Response(200, {
            "id": 123, "node_id": "R_kgDOabc", "full_name": "Acme/Service",
            "default_branch": "main",
            "permissions": {"contents": "write", "pull_requests": "write"},
        }),
        Response(200, {
            "ref": "refs/heads/main",
            "object": {"type": "commit", "sha": "a" * 40},
        }),
        Response(200, {"tree": {"sha": "b" * 40}}),
        Response(200, {
            "truncated": False,
            "tree": [
                {"type": "blob", "mode": "100644", "path": "README.md", "sha": "e" * 40},
                {"type": "blob", "mode": "100644", "path": "gone.txt", "sha": "f" * 40},
            ],
        }),
        Response(201, {"sha": "c" * 40}),
        Response(201, {"sha": "d" * 40}),
        Response(201, {
            "sha": "e" * 40, "tree": {"sha": "d" * 40},
            "parents": [{"sha": "a" * 40}],
        }),
        Response(201, {"ref": "refs/heads/odei/nexus/run-1"}),
        Response(201, {
            "number": 12, "html_url": "https://github.com/Acme/Service/pull/12",
            "head": {"sha": "e" * 40}, "base": {"ref": "main", "sha": "a" * 40},
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
    result = await client.create_workspace_pull_request(
        binding={
            "installation_id": 77, "owner": "Acme", "name": "Service",
            "repository_id": 123, "repository_node_id": "R_kgDOabc",
            "default_branch": "main", "binding_version": 4,
        },
        workspace=workspace, run_id="run-1", base_sha="a" * 40,
    )
    assert result["commit_sha"] == "e" * 40
    assert result["tree_sha"] == "d" * 40
    assert result["base_sha"] == "a" * 40
    assert result["pull_request_number"] == 12
    assert result["branch"] == "odei/nexus/run-1"
    tree_request = next(
        kwargs["json"] for method, url, kwargs in http.calls
        if method == "POST" and url.endswith("/git/trees")
    )
    assert all(entry["path"] != "gone.txt" for entry in tree_request["tree"])
    assert not any(method == "PUT" for method, _url, _kwargs in http.calls)
    assert "ephemeral-worker-token" not in repr(result)



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



@pytest.mark.asyncio
async def test_merge_requires_exact_repo_base_pr_head_and_sha_guarded_merge():
    http = Http([
        Response(200, {"id": 77, "app_id": 42}),
        Response(201, {"token": "ephemeral-merge-token"}),
        Response(200, {
            "id": 123, "node_id": "R_kgDOabc", "default_branch": "main",
            "permissions": {"contents": "write", "pull_requests": "write"},
        }),
        Response(200, {"ref": "refs/heads/main", "object": {"sha": "a" * 40}}),
        Response(200, {
            "number": 12, "state": "open", "merged": False, "mergeable": True,
            "html_url": "https://github.com/Acme/Service/pull/12",
            "head": {"sha": "e" * 40, "ref": "odei/nexus/run-1",
                     "repo": {"id": 123, "node_id": "R_kgDOabc"}},
            "base": {"sha": "a" * 40, "ref": "main",
                     "repo": {"id": 123, "node_id": "R_kgDOabc"}},
        }),
        Response(200, {"merged": True, "sha": "f" * 40}),
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
    run = SimpleNamespace(
        id="run-1", repository_owner="Acme", repository_name="Service",
        repository_binding_version=4, repository_id=123,
        repository_node_id="R_kgDOabc", repository_installation_id=77,
        repository_default_branch="main", repository_base_sha="a" * 40,
        worker_commit_sha="e" * 40, worker_branch="odei/nexus/run-1",
        worker_pull_request_number=12,
    )
    binding = {
        "state": "verified", "binding_version": 4, "repository_id": 123,
        "repository_node_id": "R_kgDOabc", "installation_id": 77,
        "owner": "Acme", "name": "Service", "default_branch": "main",
    }
    result = await client.merge_verified_pull_request(binding=binding, run=run)
    assert result == {"merge_commit_sha": "f" * 40}
    merge_call = http.calls[-1]
    assert merge_call[0] == "PUT"
    assert merge_call[1].endswith("/pulls/12/merge")
    assert merge_call[2]["json"] == {"sha": "e" * 40, "merge_method": "squash"}


@pytest.mark.asyncio
async def test_merge_refuses_advanced_base_without_provider_merge():
    http = Http([
        Response(200, {"id": 77, "app_id": 42}),
        Response(201, {"token": "ephemeral-merge-token"}),
        Response(200, {
            "id": 123, "node_id": "R_kgDOabc", "default_branch": "main",
            "permissions": {"contents": "write", "pull_requests": "write"},
        }),
        Response(200, {"ref": "refs/heads/main", "object": {"sha": "9" * 40}}),
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
    run = SimpleNamespace(
        id="run-1", repository_owner="Acme", repository_name="Service",
        repository_binding_version=4, repository_id=123,
        repository_node_id="R_kgDOabc", repository_installation_id=77,
        repository_default_branch="main", repository_base_sha="a" * 40,
        worker_commit_sha="e" * 40, worker_branch="odei/nexus/run-1",
        worker_pull_request_number=12,
    )
    binding = {
        "state": "verified", "binding_version": 4, "repository_id": 123,
        "repository_node_id": "R_kgDOabc", "installation_id": 77,
        "owner": "Acme", "name": "Service", "default_branch": "main",
    }
    with pytest.raises(GitHubRepositoryVerificationError):
        await client.merge_verified_pull_request(binding=binding, run=run)
    assert all(method != "PUT" for method, _url, _kwargs in http.calls)


