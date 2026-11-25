"""Short-lived GitHub App authentication and trusted repository verification."""
from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from typing import Any

import jwt


class GitHubAppNotConfigured(RuntimeError):
    """The GitHub App credentials required for trusted binding are unavailable."""


class GitHubRepositoryVerificationError(RuntimeError):
    """GitHub could not verify repository identity and installation access."""


@dataclass(frozen=True)
class VerifiedGitHubRepository:
    installation_id: int
    repository_id: int
    repository_node_id: str
    owner: str
    name: str
    full_name: str
    default_branch: str
    contents_permission: str
    private: bool


class GitHubAppInstallationClient:
    """Exchange a signed App JWT for an ephemeral installation token; never persist it."""

    def __init__(self, *, app_id: int | None, private_key_b64: Any, http_client: Any):
        self.app_id = app_id
        self.private_key_b64 = private_key_b64
        self.http = http_client

    def _app_jwt(self) -> str:
        if self.app_id is None or self.private_key_b64 is None:
            raise GitHubAppNotConfigured("GitHub App verification is not configured")
        try:
            pem = base64.b64decode(
                self.private_key_b64.get_secret_value(), validate=True,
            ).decode("ascii")
            now = int(time.time())
            return jwt.encode(
                {"iat": now - 30, "exp": now + 540, "iss": str(self.app_id)},
                pem, algorithm="RS256",
            )
        except Exception as exc:
            raise GitHubAppNotConfigured("GitHub App signing configuration is invalid") from exc

    async def verify_repository(
        self, *, installation_id: int, owner: str, name: str,
    ) -> VerifiedGitHubRepository:
        if (
            isinstance(installation_id, bool) or not isinstance(installation_id, int)
            or installation_id < 1
            or not isinstance(owner, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", owner)
            or not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name)
            or name in {".", ".."}
        ):
            raise GitHubRepositoryVerificationError("Repository coordinates are invalid")
        app_token = self._app_jwt()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {app_token}",
        }
        try:
            installation_response = await self.http.get(
                f"https://api.github.com/app/installations/{installation_id}",
                headers=headers,
            )
            if installation_response.status_code != 200:
                raise GitHubRepositoryVerificationError("GitHub App installation could not be verified")
            installation = installation_response.json()
            if installation.get("id") != installation_id or installation.get("app_id") != self.app_id:
                raise GitHubRepositoryVerificationError("Installation does not belong to the configured GitHub App")

            token_response = await self.http.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers=headers, json={"repositories": [name]},
            )
            if token_response.status_code != 201:
                raise GitHubRepositoryVerificationError("GitHub installation token could not be issued")
            token_data = token_response.json()
            token = token_data.get("token")
            if not isinstance(token, str) or not token:
                raise GitHubRepositoryVerificationError("GitHub returned an invalid installation token")

            repo_response = await self.http.get(
                f"https://api.github.com/repos/{owner}/{name}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "Authorization": f"Bearer {token}",
                },
            )
            if repo_response.status_code != 200:
                raise GitHubRepositoryVerificationError("Repository is not accessible to this installation")
            repository = repo_response.json()
            permissions = repository.get("permissions") or {}
            contents = permissions.get("contents")
            if contents not in {"write", "admin"}:
                raise GitHubRepositoryVerificationError(
                    "GitHub App installation requires repository contents write permission"
                )
            repo_id = repository.get("id")
            node_id = repository.get("node_id")
            full_name = repository.get("full_name")
            default_branch = repository.get("default_branch")
            repo_owner = (repository.get("owner") or {}).get("login")
            repo_name = repository.get("name")
            if (
                isinstance(repo_id, bool) or not isinstance(repo_id, int) or repo_id < 1
                or not isinstance(node_id, str) or not node_id
                or not isinstance(full_name, str) or full_name.casefold() != f"{owner}/{name}".casefold()
                or not isinstance(default_branch, str) or not default_branch
                or not isinstance(repo_owner, str) or not isinstance(repo_name, str)
            ):
                raise GitHubRepositoryVerificationError("GitHub repository identity response is incomplete")
            return VerifiedGitHubRepository(
                installation_id=installation_id, repository_id=repo_id,
                repository_node_id=node_id, owner=repo_owner, name=repo_name,
                full_name=full_name, default_branch=default_branch,
                contents_permission=contents, private=bool(repository.get("private")),
            )
        except GitHubRepositoryVerificationError:
            raise
        except Exception as exc:
            raise GitHubRepositoryVerificationError("GitHub repository verification failed") from exc
