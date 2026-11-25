"""Durable, single-use human approval records for NEXUS repository merge-back."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class RepositoryMergeApprovalConflict(RuntimeError):
    """A merge approval is expired, already used, or conflicts with another approval."""


class MongoRepositoryMergeApprovalStore:
    """Stores one immutable merge approval per execution run."""

    def __init__(self, collection: Any) -> None:
        self._approvals = collection

    async def initialize(self) -> None:
        await self._approvals.create_index(
            [("organization_id", 1), ("project_id", 1), ("run_id", 1)],
            unique=True,
        )
        await self._approvals.create_index(
            [("organization_id", 1), ("project_id", 1), ("status", 1), ("expires_at", 1)],
        )

    async def create(
        self, *, organization_id: str, project_id: str, task_id: str, run_id: str,
        actor_issuer: str, actor_subject: str, repository_id: int,
        repository_node_id: str, installation_id: int, binding_version: int,
        owner: str, name: str, default_branch: str, base_sha: str,
        commit_sha: str, tree_sha: str, branch: str, pull_request_number: int,
        pull_request_url: str, expires_in_seconds: int = 600,
    ) -> dict[str, Any]:
        if not 60 <= expires_in_seconds <= 600:
            raise ValueError("merge approval expiry must be between 60 and 600 seconds")
        for value in (base_sha, commit_sha, tree_sha):
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
                raise ValueError("merge approval commit identity is invalid")
        now = datetime.now(timezone.utc)
        approval_id = uuid4().hex
        document = {
            "_id": approval_id, "approval_id": approval_id,
            "organization_id": organization_id, "project_id": project_id,
            "task_id": task_id, "run_id": run_id,
            "created_by_issuer": actor_issuer, "created_by_subject": actor_subject,
            "repository_id": repository_id, "repository_node_id": repository_node_id,
            "installation_id": installation_id, "binding_version": binding_version,
            "owner": owner, "name": name, "default_branch": default_branch,
            "base_sha": base_sha, "commit_sha": commit_sha, "tree_sha": tree_sha,
            "branch": branch, "pull_request_number": pull_request_number,
            "pull_request_url": pull_request_url,
            "status": "pending", "version": 1,
            "created_at": now,
            "expires_at": now + timedelta(seconds=expires_in_seconds),
            "consumed_at": None, "consumed_by_issuer": None,
            "consumed_by_subject": None, "finished_at": None,
            "merge_commit_sha": None, "failure_code": None,
        }
        try:
            await self._approvals.insert_one(document)
        except DuplicateKeyError as exc:
            raise RepositoryMergeApprovalConflict(
                "A merge approval has already been created for this execution",
            ) from exc
        return document

    async def consume(
        self, *, approval_id: str, organization_id: str, project_id: str,
        task_id: str, run_id: str, actor_issuer: str, actor_subject: str,
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        return await self._approvals.find_one_and_update(
            {
                "_id": approval_id, "organization_id": organization_id,
                "project_id": project_id, "task_id": task_id, "run_id": run_id,
                "status": "pending", "expires_at": {"$gt": now},
                "created_by_issuer": actor_issuer,
                "created_by_subject": actor_subject,
            },
            {
                "$set": {
                    "status": "consuming", "consumed_at": now,
                    "consumed_by_issuer": actor_issuer,
                    "consumed_by_subject": actor_subject,
                },
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
        )

    async def finish(
        self, *, approval_id: str, organization_id: str, project_id: str,
        status: str, merge_commit_sha: str | None = None,
        failure_code: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"consumed", "failed"}:
            raise ValueError("merge approval final status is invalid")
        if status == "consumed" and (
            not isinstance(merge_commit_sha, str)
            or not re.fullmatch(r"[0-9a-f]{40}", merge_commit_sha)
        ):
            raise ValueError("merged commit SHA is invalid")
        if failure_code is not None and (
            not isinstance(failure_code, str) or not re.fullmatch(r"[A-Z0-9_]{1,64}", failure_code)
        ):
            raise ValueError("merge approval failure code is invalid")
        updated = await self._approvals.find_one_and_update(
            {
                "_id": approval_id, "organization_id": organization_id,
                "project_id": project_id, "status": "consuming",
            },
            {
                "$set": {
                    "status": status, "finished_at": datetime.now(timezone.utc),
                    "merge_commit_sha": merge_commit_sha,
                    "failure_code": failure_code,
                },
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise RepositoryMergeApprovalConflict("Merge approval is no longer consuming")
        return updated
