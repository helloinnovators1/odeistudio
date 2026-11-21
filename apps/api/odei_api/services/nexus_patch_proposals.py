"""Tenant-scoped persistent NEXUS patch proposals and owner decisions.

Proposals are review records only. This API does not write local workspace files.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from odei_api.config import get_settings
from odei_api.security.auth import Principal, get_current_principal
from odei_api.services.nexus_tasks import _authorize_project
from odei_api.services.patch_proposals import (
    MAX_DIFF_BYTES,
    MAX_FILE_BYTES,
    MAX_PATCH_FILES,
    MAX_TOTAL_BYTES,
    PatchProposalError,
    build_patch_proposal,
)
from odei_api.services.secret_redaction import redact_secrets

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()
principal_dependency = Depends(get_current_principal)


class PatchProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: StrictStr = Field(min_length=1, max_length=160)
    base_files: dict[StrictStr, StrictStr] = Field(max_length=MAX_PATCH_FILES)
    changes: dict[StrictStr, StrictStr | None] = Field(min_length=1, max_length=MAX_PATCH_FILES)
    expected_base_hashes: dict[StrictStr, StrictStr | None] = Field(max_length=MAX_PATCH_FILES)
    cloud_model_consent: StrictBool

    @model_validator(mode="after")
    def validate_budgets(self):
        if not self.cloud_model_consent:
            raise ValueError("Explicit cloud-model consent is required")
        if set(self.expected_base_hashes) != set(self.changes):
            raise ValueError("Every changed path requires exactly one expected base hash")
        if not set(self.base_files).issubset(self.changes):
            raise ValueError("Base snapshots may contain only changed paths")
        if not self.changes:
            raise ValueError("A proposal must contain at least one file change")
        base_bytes = sum(len(value.encode("utf-8")) for value in self.base_files.values())
        change_bytes = sum(
            len(value.encode("utf-8")) for value in self.changes.values() if value is not None
        )
        if any(len(value.encode("utf-8")) > MAX_FILE_BYTES for value in self.base_files.values()):
            raise ValueError("A base file exceeds the 1 MB limit")
        if any(
            value is not None and len(value.encode("utf-8")) > MAX_FILE_BYTES
            for value in self.changes.values()
        ):
            raise ValueError("A replacement file exceeds the 1 MB limit")
        if base_bytes > MAX_TOTAL_BYTES or change_bytes > MAX_TOTAL_BYTES:
            raise ValueError("Patch proposal exceeds the 5 MB aggregate content budget")
        return self


class PatchDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)


class MongoPatchProposalStore:
    """Persist bounded patch previews and owner decisions in MongoDB."""

    def __init__(self, collection: Any) -> None:
        self.collection = collection

    async def initialize(self) -> None:
        await self.collection.create_index("proposal_id", unique=True)
        await self.collection.create_index([
            ("organization_id", 1), ("project_id", 1), ("owner_issuer", 1),
            ("owner_subject", 1), ("updated_at", -1),
        ])
        await self.collection.create_index([
            ("organization_id", 1), ("project_id", 1), ("status", 1), ("updated_at", -1),
        ])

    async def create(
        self, *, organization_id: str, project_id: str,
        owner_issuer: str, owner_subject: str, title: str,
        files: list[dict[str, Any]], proposal_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        document = {
            "proposal_id": proposal_id or uuid4().hex,
            "organization_id": organization_id,
            "project_id": project_id,
            "owner_issuer": owner_issuer,
            "owner_subject": owner_subject,
            "title": redact_secrets(title)[:160],
            "files": files,
            "status": "pending",
            "version": 0,
            "created_at": now,
            "updated_at": now,
            "decided_by_issuer": None,
            "decided_by_subject": None,
            "decided_at": None,
        }
        await self.collection.insert_one(document)
        return document

    async def list_for_project(
        self, *, organization_id: str, project_id: str,
        owner_issuer: str | None = None, owner_subject: str | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {
            "organization_id": organization_id, "project_id": project_id,
        }
        if owner_issuer is not None and owner_subject is not None:
            query["owner_issuer"] = owner_issuer
            query["owner_subject"] = owner_subject
        cursor = self.collection.find(query).sort("updated_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get(self, *, organization_id: str, project_id: str, proposal_id: str) -> dict[str, Any] | None:
        return await self.collection.find_one({
            "organization_id": organization_id,
            "project_id": project_id,
            "proposal_id": proposal_id,
        })

    async def decide(
        self, *, organization_id: str, project_id: str, proposal_id: str,
        expected_version: int, decision: str,
        actor_issuer: str, actor_subject: str,
    ) -> dict[str, Any] | None:
        if decision not in {"approved", "rejected"}:
            raise ValueError("Unsupported proposal decision")
        now = datetime.now(timezone.utc)
        return await self.collection.find_one_and_update(
            {
                "organization_id": organization_id,
                "project_id": project_id,
                "proposal_id": proposal_id,
                "status": "pending",
                "version": expected_version,
            },
            {
                "$set": {
                    "status": decision,
                    "decided_by_issuer": actor_issuer,
                    "decided_by_subject": actor_subject,
                    "decided_at": now,
                    "updated_at": now,
                },
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
        )


def _is_project_owner(project: dict[str, Any], principal: Principal) -> bool:
    return (
        project.get("owner_issuer") == principal.issuer
        and project.get("owner_subject") == principal.subject
    )


def _proposal_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": item["proposal_id"],
        "title": item["title"],
        "status": item["status"],
        "version": item["version"],
        "file_count": len(item["files"]),
        "created_at": item["created_at"].isoformat(),
        "updated_at": item["updated_at"].isoformat(),
    }


async def _audit_proposal(
    request: Request, principal: Principal, organization_id: str,
    proposal_id: str, action: str, outcome: str,
    *, project_id: str, file_count: int = 0, version: int | None = None,
    proposal_count: int = 0, decision: str | None = None,
) -> None:
    audit = getattr(request.app.state, "audit_event_store", None)
    if audit is None:
        raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is not configured."})
    metadata: dict[str, Any] = {"project_id": project_id, "file_count": file_count}
    if version is not None:
        metadata["version"] = version
    if proposal_count:
        metadata["proposal_count"] = proposal_count
    if decision is not None:
        metadata["decision"] = decision
    try:
        await audit.append(
            organization_id=organization_id,
            actor_issuer=principal.issuer,
            actor_subject=principal.subject,
            action=action,
            target_type="nexus_patch_proposal",
            target_id=proposal_id,
            outcome=outcome,
            request_id=uuid4().hex,
            metadata=metadata,
        )
    except Exception as exc:
        logger.error("NEXUS patch proposal audit append failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Patch proposal audit storage is temporarily unavailable."}) from exc


async def _project_and_store(request: Request, organization_id: str, project_id: str, principal: Principal):
    try:
        project = await _authorize_project(request, organization_id, project_id, principal)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "PROJECT_STORE_UNAVAILABLE", "message": "Project authorization storage is temporarily unavailable."}) from exc
    store = getattr(request.app.state, "patch_proposal_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "PATCH_PROPOSAL_STORE_UNAVAILABLE", "message": "Patch proposal storage is not configured."})
    return project, store


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/patch-proposals",
    status_code=status.HTTP_201_CREATED,
    tags=["nexus"],
)
async def create_patch_proposal(
    payload: PatchProposalRequest,
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    """Persist a validated diff preview; never apply it to local files."""
    if organization_id != organization_id.strip() or project_id != project_id.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_RESOURCE_ID", "message": "Resource identifier is invalid."})
    _, store = await _project_and_store(request, organization_id, project_id, principal)
    try:
        for path, expected_hash in payload.expected_base_hashes.items():
            if expected_hash is None and "/" in path:
                raise PatchProposalError("New files are limited to workspace-root paths until nested directory creation is supported")
        redacted_changes = {
            path: redact_secrets(content) if content is not None else None
            for path, content in payload.changes.items()
        }
        proposal = build_patch_proposal(
            payload.base_files, redacted_changes, payload.expected_base_hashes,
        )
    except PatchProposalError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_PATCH_PROPOSAL", "message": str(exc)}) from exc
    if proposal.total_diff_bytes > MAX_DIFF_BYTES:
        raise HTTPException(status_code=422, detail={"code": "PATCH_DIFF_TOO_LARGE", "message": "Patch diff exceeds the 8 MB limit."})
    files = [
        {
            "path": item.path,
            "operation": item.operation,
            "base_sha256": item.base_sha256,
            "result_sha256": item.result_sha256,
            "content": item.content,
            "unified_diff": redact_secrets(item.unified_diff),
        }
        for item in proposal.files
    ]
    proposal_id = uuid4().hex
    await _audit_proposal(
        request, principal, organization_id, proposal_id,
        "nexus.patch_proposal.create", "started",
        project_id=project_id, file_count=len(files),
    )
    try:
        created = await store.create(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=principal.issuer, owner_subject=principal.subject,
            title=payload.title, files=files, proposal_id=proposal_id,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "PATCH_PROPOSAL_STORE_UNAVAILABLE", "message": "Patch proposal storage is temporarily unavailable."}) from exc
    await _audit_proposal(
        request, principal, organization_id, created["proposal_id"],
        "nexus.patch_proposal.create", "success",
        project_id=project_id, file_count=len(files), version=0,
    )
    return {
        "proposal_id": created["proposal_id"],
        "title": created["title"],
        "status": created["status"],
        "version": created["version"],
        "files": created["files"],
        "total_content_bytes": proposal.total_content_bytes,
        "total_diff_bytes": proposal.total_diff_bytes,
        "application_enabled": False,
    }


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/patch-proposals",
    tags=["nexus"],
)
async def list_patch_proposals(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    project, store = await _project_and_store(request, organization_id, project_id, principal)
    owner_filter = {} if _is_project_owner(project, principal) else {
        "owner_issuer": principal.issuer, "owner_subject": principal.subject,
    }
    try:
        items = await store.list_for_project(
            organization_id=organization_id, project_id=project_id, **owner_filter,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "PATCH_PROPOSAL_STORE_UNAVAILABLE", "message": "Patch proposal storage is temporarily unavailable."}) from exc
    return {"proposals": [_proposal_summary(item) for item in items], "limit": 30}


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/patch-proposals/{{proposal_id}}",
    tags=["nexus"],
)
async def get_patch_proposal(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    proposal_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    project, store = await _project_and_store(request, organization_id, project_id, principal)
    try:
        item = await store.get(organization_id=organization_id, project_id=project_id, proposal_id=proposal_id)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "PATCH_PROPOSAL_STORE_UNAVAILABLE", "message": "Patch proposal storage is temporarily unavailable."}) from exc
    if item is None or (
        not _is_project_owner(project, principal)
        and (item["owner_issuer"] != principal.issuer or item["owner_subject"] != principal.subject)
    ):
        raise HTTPException(status_code=404, detail={"code": "PATCH_PROPOSAL_NOT_FOUND", "message": "Patch proposal was not found."})
    await _audit_proposal(
        request, principal, organization_id, proposal_id,
        "nexus.patch_proposal.read", "success",
        project_id=project_id, file_count=len(item["files"]),
        version=item["version"],
    )
    return {
        **_proposal_summary(item),
        "files": item["files"],
        "application_enabled": False,
    }


async def _decide_patch_proposal(
    decision: str, payload: PatchDecisionRequest, request: Request,
    organization_id: str, project_id: str, proposal_id: str, principal: Principal,
) -> dict:
    project, store = await _project_and_store(request, organization_id, project_id, principal)
    if not _is_project_owner(project, principal):
        raise HTTPException(status_code=403, detail={"code": "PROJECT_OWNER_REQUIRED", "message": "Only the project owner can approve or reject patch proposals."})
    await _audit_proposal(
        request, principal, organization_id, proposal_id,
        "nexus.patch_proposal.decision", "started",
        project_id=project_id, version=payload.expected_version,
        decision=decision,
    )
    try:
        updated = await store.decide(
            organization_id=organization_id, project_id=project_id,
            proposal_id=proposal_id, expected_version=payload.expected_version,
            decision=decision, actor_issuer=principal.issuer,
            actor_subject=principal.subject,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "PATCH_PROPOSAL_STORE_UNAVAILABLE", "message": "Patch proposal storage is temporarily unavailable."}) from exc
    if updated is None:
        raise HTTPException(status_code=409, detail={"code": "PATCH_PROPOSAL_VERSION_CONFLICT", "message": "Proposal was already decided or its version changed."})
    await _audit_proposal(
        request, principal, organization_id, proposal_id,
        "nexus.patch_proposal.decision", "success",
        project_id=project_id, file_count=len(updated["files"]),
        version=updated["version"], decision=decision,
    )
    return {
        **_proposal_summary(updated),
        "decision_recorded": True,
        "application_enabled": False,
    }


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/patch-proposals/{{proposal_id}}/approve",
    tags=["nexus"],
)
async def approve_patch_proposal(
    payload: PatchDecisionRequest, request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    proposal_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    return await _decide_patch_proposal("approved", payload, request, organization_id, project_id, proposal_id, principal)


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/patch-proposals/{{proposal_id}}/reject",
    tags=["nexus"],
)
async def reject_patch_proposal(
    payload: PatchDecisionRequest, request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    proposal_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    return await _decide_patch_proposal("rejected", payload, request, organization_id, project_id, proposal_id, principal)
