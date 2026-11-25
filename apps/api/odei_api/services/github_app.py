"""Short-lived GitHub App authentication and trusted repository verification."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import jwt

from odei_api.services.secret_redaction import redact_secrets
from odei_api.services.workspace_snapshots import SnapshotError, WorkspaceSnapshotIngestor


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
    pull_requests_permission: str
    default_branch_sha: str
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


    async def _installation_token(self, *, installation_id: int, repository_name: str) -> str:
        app_token = self._app_jwt()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {app_token}",
        }
        installation_response = await self.http.get(
            f"https://api.github.com/app/installations/{installation_id}", headers=headers,
        )
        if installation_response.status_code != 200:
            raise GitHubRepositoryVerificationError("GitHub App installation could not be verified")
        installation = installation_response.json()
        if installation.get("id") != installation_id or installation.get("app_id") != self.app_id:
            raise GitHubRepositoryVerificationError("Installation does not belong to the configured GitHub App")
        token_response = await self.http.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers=headers, json={"repositories": [repository_name]},
        )
        if token_response.status_code != 201:
            raise GitHubRepositoryVerificationError("GitHub installation token could not be issued")
        token = token_response.json().get("token")
        if not isinstance(token, str) or not token:
            raise GitHubRepositoryVerificationError("GitHub returned an invalid installation token")
        return token

    @staticmethod
    def _installation_headers(token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}",
        }

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
        try:
            token = await self._installation_token(
                installation_id=installation_id, repository_name=name,
            )
            repo_response = await self.http.get(
                f"https://api.github.com/repos/{owner}/{name}",
                headers=self._installation_headers(token),
            )
            if repo_response.status_code != 200:
                raise GitHubRepositoryVerificationError("Repository is not accessible to this installation")
            repository = repo_response.json()
            permissions = repository.get("permissions") or {}
            contents = permissions.get("contents")
            pull_requests = permissions.get("pull_requests")
            if contents not in {"write", "admin"} or pull_requests not in {"write", "admin"}:
                raise GitHubRepositoryVerificationError(
                    "GitHub App installation requires contents and pull requests write permissions"
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
            ref_response = await self.http.get(
                f"https://api.github.com/repos/{owner}/{name}/git/ref/heads/{quote(default_branch, safe='')}",
                headers=self._installation_headers(token),
            )
            if ref_response.status_code != 200:
                raise GitHubRepositoryVerificationError("GitHub default branch could not be verified")
            ref_data = ref_response.json()
            ref_object = ref_data.get("object") or {}
            default_branch_sha = ref_object.get("sha")
            if (
                ref_data.get("ref") != f"refs/heads/{default_branch}"
                or ref_object.get("type") != "commit"
                or not isinstance(default_branch_sha, str)
                or not re.fullmatch(r"[0-9a-f]{40}", default_branch_sha)
            ):
                raise GitHubRepositoryVerificationError("GitHub default branch identity is incomplete")
            return VerifiedGitHubRepository(
                installation_id=installation_id, repository_id=repo_id,
                repository_node_id=node_id, owner=repo_owner, name=repo_name,
                full_name=full_name, default_branch=default_branch,
                contents_permission=contents, pull_requests_permission=pull_requests,
                default_branch_sha=default_branch_sha,
                private=bool(repository.get("private")),
            )
        except GitHubRepositoryVerificationError:
            raise
        except Exception as exc:
            raise GitHubRepositoryVerificationError("GitHub repository verification failed") from exc


    async def _create_workspace_pull_request(
        self, *, binding: dict[str, Any], workspace: str | Path,
        run_id: str, base_sha: str,
    ) -> dict[str, Any] | None:
        """Create a bounded commit and review PR from a verified full workspace snapshot."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id):
            raise GitHubRepositoryVerificationError("Execution run identifier is invalid")
        if not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", base_sha):
            raise GitHubRepositoryVerificationError("Trusted base commit is invalid")
        root = Path(workspace)
        if root.is_symlink() or not root.is_dir():
            raise GitHubRepositoryVerificationError("Worker workspace is not a trusted directory")
        installation_id = binding.get("installation_id")
        owner, name = binding.get("owner"), binding.get("name")
        repository_id, node_id = binding.get("repository_id"), binding.get("repository_node_id")
        default_branch = binding.get("default_branch")
        binding_version = binding.get("binding_version")
        if (
            isinstance(installation_id, bool) or not isinstance(installation_id, int) or installation_id < 1
            or not isinstance(owner, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", owner)
            or not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", name)
            or isinstance(repository_id, bool) or not isinstance(repository_id, int) or repository_id < 1
            or not isinstance(node_id, str) or not node_id
            or isinstance(binding_version, bool) or not isinstance(binding_version, int) or binding_version < 1
            or not isinstance(default_branch, str)
            or not re.fullmatch(r"[A-Za-z0-9._/-]{1,255}", default_branch)
            or default_branch.startswith("/") or default_branch.endswith("/")
            or ".." in default_branch.split("/")
        ):
            raise GitHubRepositoryVerificationError("Trusted repository binding metadata is invalid")
        token = await self._installation_token(
            installation_id=installation_id, repository_name=name,
        )
        headers = self._installation_headers(token)
        prefix = f"https://api.github.com/repos/{owner}/{name}"
        repo_response = await self.http.get(prefix, headers=headers)
        if repo_response.status_code != 200:
            raise GitHubRepositoryVerificationError("Bound repository is no longer accessible")
        repository = repo_response.json()
        permissions = repository.get("permissions") or {}
        if (
            repository.get("id") != repository_id
            or repository.get("node_id") != node_id
            or (repository.get("full_name") or "").casefold() != f"{owner}/{name}".casefold()
            or permissions.get("contents") not in {"write", "admin"}
            or permissions.get("pull_requests") not in {"write", "admin"}
        ):
            raise GitHubRepositoryVerificationError("Worker repository identity or write permissions changed")
        ref_response = await self.http.get(
            f"{prefix}/git/ref/heads/{quote(default_branch, safe='')}", headers=headers,
        )
        if ref_response.status_code != 200:
            raise GitHubRepositoryVerificationError("Bound default branch is unavailable")
        ref_data = ref_response.json()
        ref_object = ref_data.get("object") or {}
        if (
            ref_data.get("ref") != f"refs/heads/{default_branch}"
            or ref_object.get("type") != "commit"
            or ref_object.get("sha") != base_sha
        ):
            raise GitHubRepositoryVerificationError("Trusted repository base changed after execution was queued")
        commit_response = await self.http.get(f"{prefix}/git/commits/{base_sha}", headers=headers)
        if commit_response.status_code != 200:
            raise GitHubRepositoryVerificationError("Trusted base commit could not be read")
        base_tree_sha = (commit_response.json().get("tree") or {}).get("sha")
        if not isinstance(base_tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", base_tree_sha):
            raise GitHubRepositoryVerificationError("Trusted base tree is invalid")
        tree_response = await self.http.get(
            f"{prefix}/git/trees/{base_tree_sha}?recursive=1", headers=headers,
        )
        if tree_response.status_code != 200:
            raise GitHubRepositoryVerificationError("Trusted repository tree could not be read")
        tree_data = tree_response.json()
        if tree_data.get("truncated") is True or not isinstance(tree_data.get("tree"), list):
            raise GitHubRepositoryVerificationError("Trusted repository tree exceeds verification limits")
        base_files: dict[str, dict[str, str]] = {}
        for entry in tree_data["tree"]:
            if entry.get("type") == "tree":
                continue
            path, mode, sha = entry.get("path"), entry.get("mode"), entry.get("sha")
            if (
                entry.get("type") != "blob" or mode not in {"100644", "100755"}
                or not isinstance(path, str) or not path or path.startswith("/")
                or any(part in {"", ".", "..", ".git"} for part in path.split("/"))
                or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
            ):
                raise GitHubRepositoryVerificationError("Repository contains unsupported links or tree entries")
            base_files[path] = {"sha": sha, "mode": mode}

        workspace_files: dict[str, bytes] = {}
        total_bytes = 0
        for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            for directory in list(directories):
                child = current_path / directory
                if directory == ".git" or child.is_symlink():
                    raise GitHubRepositoryVerificationError("Worker workspace contains a link or Git metadata")
            directories.sort()
            for filename in sorted(filenames):
                path = current_path / filename
                if path.is_symlink() or not path.is_file():
                    raise GitHubRepositoryVerificationError("Worker workspace contains a link or special file")
                relative = path.relative_to(root).as_posix()
                try:
                    WorkspaceSnapshotIngestor._safe_parts(relative, is_directory=False)
                except SnapshotError as exc:
                    raise GitHubRepositoryVerificationError(
                        "Worker workspace contains a sensitive or unsafe path",
                    ) from exc
                data = path.read_bytes()
                decoded = data.decode("utf-8", errors="ignore")
                if redact_secrets(decoded) != decoded:
                    raise GitHubRepositoryVerificationError(
                        "Worker workspace contains a credential-like value and cannot be published",
                    )
                total_bytes += len(data)
                if len(data) > 64 * 1024 * 1024 or total_bytes > 100 * 1024 * 1024:
                    raise GitHubRepositoryVerificationError("Worker workspace exceeds repository commit limits")
                workspace_files[relative] = data
                if len(workspace_files) > 10_000:
                    raise GitHubRepositoryVerificationError("Worker workspace contains too many files")

        changed: list[tuple[str, bytes, str]] = []
        changed_bytes = 0
        for path, data in workspace_files.items():
            blob_header = f"blob {len(data)}\0".encode("ascii")
            blob_sha = hashlib.sha1(blob_header + data, usedforsecurity=False).hexdigest()
            existing = base_files.get(path)
            if existing is None or existing["sha"] != blob_sha:
                changed.append((path, data, existing.get("mode", "100644") if existing else "100644"))
                changed_bytes += len(data)
        deleted = sorted(set(base_files) - set(workspace_files))
        if len(changed) > 500 or changed_bytes > 10 * 1024 * 1024:
            raise GitHubRepositoryVerificationError("Repository change set exceeds bounded commit limits")
        if not changed and not deleted:
            return None

        semaphore = asyncio.Semaphore(4)

        async def create_blob(path: str, data: bytes, mode: str) -> dict[str, str]:
            async with semaphore:
                response = await self.http.post(
                    f"{prefix}/git/blobs", headers=headers,
                    json={"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"},
                )
            if response.status_code != 201:
                raise GitHubRepositoryVerificationError("GitHub rejected a worker file blob")
            sha = response.json().get("sha")
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
                raise GitHubRepositoryVerificationError("GitHub returned an invalid worker blob")
            return {"path": path, "mode": mode, "type": "blob", "sha": sha}

        changed_entries = await asyncio.gather(*(
            create_blob(path, data, mode) for path, data, mode in changed
        ))
        tree_entries: list[dict[str, Any]] = list(changed_entries)
        tree_entries.extend({
            "path": path, "mode": base_files[path]["mode"], "type": "blob", "sha": None,
        } for path in deleted)
        new_tree_response = await self.http.post(
            f"{prefix}/git/trees", headers=headers,
            json={"base_tree": base_tree_sha, "tree": tree_entries},
        )
        if new_tree_response.status_code != 201:
            raise GitHubRepositoryVerificationError("GitHub rejected the worker repository tree")
        new_tree_sha = new_tree_response.json().get("sha")
        if not isinstance(new_tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", new_tree_sha):
            raise GitHubRepositoryVerificationError("GitHub returned an invalid worker tree")
        commit_response = await self.http.post(
            f"{prefix}/git/commits", headers=headers,
            json={"message": f"NEXUS execution {run_id}", "tree": new_tree_sha, "parents": [base_sha]},
        )
        if commit_response.status_code != 201:
            raise GitHubRepositoryVerificationError("GitHub rejected the worker commit")
        commit_data = commit_response.json()
        commit_sha = commit_data.get("sha")
        commit_tree = (commit_data.get("tree") or {}).get("sha")
        parents = commit_data.get("parents") or []
        if (
            not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha)
            or commit_tree != new_tree_sha
            or len(parents) != 1 or parents[0].get("sha") != base_sha
        ):
            raise GitHubRepositoryVerificationError("Worker commit provenance does not match the trusted base")

        branch = f"odei/nexus/{run_id}"
        branch_created = False
        try:
            ref_create = await self.http.post(
                f"{prefix}/git/refs", headers=headers,
                json={"ref": f"refs/heads/{branch}", "sha": commit_sha},
            )
            if ref_create.status_code != 201:
                raise GitHubRepositoryVerificationError("GitHub rejected the isolated worker branch")
            branch_created = True
            pull_response = await self.http.post(
                f"{prefix}/pulls", headers=headers,
                json={
                    "title": f"NEXUS execution {run_id[:12]}",
                    "head": branch, "base": default_branch,
                    "body": (
                        f"Automated review proposal for NEXUS execution {run_id}.\n\n"
                        f"Trusted base: {base_sha}. Worker commit: {commit_sha}.\n\n"
                        "This pull request is not merged automatically. A project owner must review "
                        "the diff and explicitly approve merge-back through ODEI."
                    ),
                },
            )
            if pull_response.status_code != 201:
                raise GitHubRepositoryVerificationError("GitHub rejected the worker review pull request")
            pull = pull_response.json()
            head_sha = (pull.get("head") or {}).get("sha")
            base_ref = (pull.get("base") or {}).get("ref")
            published_base_sha = (pull.get("base") or {}).get("sha")
            number, url = pull.get("number"), pull.get("html_url")
            expected_url = f"https://github.com/{owner}/{name}/pull/{number}"
            if (
                head_sha != commit_sha or base_ref != default_branch or published_base_sha != base_sha
                or isinstance(number, bool) or not isinstance(number, int) or number < 1
                or not isinstance(url, str) or url.casefold() != expected_url.casefold()
            ):
                raise GitHubRepositoryVerificationError("GitHub pull request provenance is incomplete")
            return {
                "repository_id": repository_id, "repository_node_id": node_id,
                "installation_id": installation_id, "binding_version": binding_version,
                "owner": owner, "name": name, "default_branch": default_branch,
                "base_sha": base_sha, "commit_sha": commit_sha, "tree_sha": new_tree_sha,
                "branch": branch, "pull_request_number": number, "pull_request_url": url,
            }
        except Exception:
            if branch_created:
                try:
                    await self.http.delete(
                        f"{prefix}/git/refs/heads/{quote(branch, safe='')}", headers=headers,
                    )
                except Exception:
                    pass
            raise


    async def create_workspace_pull_request(
        self, *, binding: dict[str, Any], workspace: str | Path,
        run_id: str, base_sha: str,
    ) -> dict[str, Any] | None:
        """Publish a bounded worker review proposal; normalize provider errors for the worker."""
        try:
            return await self._create_workspace_pull_request(
                binding=binding, workspace=workspace, run_id=run_id, base_sha=base_sha,
            )
        except GitHubRepositoryVerificationError:
            raise
        except Exception as exc:
            raise GitHubRepositoryVerificationError(
                "Worker repository publication failed",
            ) from exc
