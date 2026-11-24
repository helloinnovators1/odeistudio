"""Authenticated tenant/project-scoped NEXUS parallel job API."""
from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from pymongo.errors import DuplicateKeyError, PyMongoError

from odei_api.config import get_settings
from odei_api.security.auth import Principal, get_current_principal, require_organization_membership
from odei_api.services.parallel_jobs import ParallelJobConflict
from odei_api.services.project_access import require_project_access

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()
principal_dependency = Depends(get_current_principal)


class ParallelJobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    payload: dict = Field(default_factory=dict)
    depends_on: list[StrictStr] = Field(default_factory=list, max_length=32)


class CreateParallelJobGroupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    jobs: list[ParallelJobInput] = Field(min_length=1, max_length=32)
    max_attempts: int = Field(default=3, ge=1, le=10)


async def _authorize(request: Request, organization_id, project_id, principal):
    database = getattr(request.app.state, "mongo_database", None)
    store = getattr(request.app.state, "parallel_job_store", None)
    audit = getattr(request.app.state, "audit_event_store", None)
    if database is None or store is None or audit is None:
        raise HTTPException(status_code=503, detail={
            "code": "PARALLEL_JOB_STORAGE_UNAVAILABLE",
            "message": "Parallel job storage and audit are not configured.",
        })
    try:
        await require_organization_membership(
            database["organization_memberships"], principal=principal,
            organization_id=organization_id,
        )
        project = await require_project_access(
            database["projects"], database["project_memberships"],
            organization_id=organization_id, project_id=project_id,
            identity_issuer=principal.issuer, identity_subject=principal.subject,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "PARALLEL_JOB_AUTHORIZATION_UNAVAILABLE",
            "message": "Project authorization is temporarily unavailable.",
        }) from exc
    except HTTPException:
        raise
    return store, audit, project


async def _audit(audit, principal, organization_id, project_id, action, outcome, metadata=None):
    return await audit.append(
        organization_id=organization_id, actor_issuer=principal.issuer,
        actor_subject=principal.subject, action=action,
        target_type="nexus_parallel_job_group", target_id=project_id,
        outcome=outcome, request_id=uuid4().hex, metadata=metadata or {},
    )


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/job-groups",
    tags=["nexus-jobs"],
)
async def create_parallel_job_group(
    payload: CreateParallelJobGroupRequest,
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
):
    if organization_id != organization_id.strip() or project_id != project_id.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_RESOURCE_ID"})
    store, audit, _project = await _authorize(request, organization_id, project_id, principal)
    group_id = payload.group_id or uuid4().hex
    jobs = [item.model_dump(exclude_none=True) for item in payload.jobs]
    run_store = getattr(request.app.state, "execution_run_store", None)
    if run_store is None:
        raise HTTPException(status_code=503, detail={
            "code": "NEXUS_EXECUTION_UNAVAILABLE",
            "message": "Approved NEXUS execution storage is not configured.",
        })
    try:
        for item in jobs:
            job_payload = item.get("payload", {})
            if not isinstance(job_payload, dict) or set(job_payload) != {"execution_run_id"}:
                raise HTTPException(status_code=422, detail={
                    "code": "INVALID_NEXUS_JOB_PAYLOAD",
                    "message": "Each parallel job must reference one previously approved execution run.",
                })
            execution_run_id = job_payload["execution_run_id"]
            if not isinstance(execution_run_id, str) or not execution_run_id.strip():
                raise HTTPException(status_code=422, detail={
                    "code": "INVALID_NEXUS_EXECUTION_REFERENCE",
                    "message": "Execution run reference is invalid.",
                })
            try:
                execution_run = await run_store.get(
                    organization_id=organization_id, run_id=execution_run_id,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail={
                    "code": "INVALID_NEXUS_EXECUTION_REFERENCE",
                    "message": "Execution run reference is invalid.",
                }) from exc
            if (
                execution_run is None
                or execution_run.project_id != project_id
                or execution_run.requester_issuer != principal.issuer
                or execution_run.requester_subject != principal.subject
            ):
                raise HTTPException(status_code=404, detail={
                    "code": "NEXUS_EXECUTION_NOT_FOUND",
                    "message": "An approved execution run was not found in this project for this requester.",
                })
            if execution_run.status.value not in {"queued", "leased", "running", "collecting"}:
                raise HTTPException(status_code=409, detail={
                    "code": "NEXUS_EXECUTION_NOT_ACTIVE",
                    "message": "Only active approved execution runs can be scheduled.",
                })
            job_payload["requested_by_issuer"] = principal.issuer
            job_payload["requested_by_subject"] = principal.subject
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "NEXUS_EXECUTION_UNAVAILABLE",
            "message": "NEXUS execution state could not be verified.",
        }) from exc
    await _audit(audit, principal, organization_id, project_id,
                 "nexus.parallel_jobs.create", "started",
                 {"group_id": group_id, "job_count": len(jobs)})
    try:
        created = await store.create_group(
            organization_id=organization_id, project_id=project_id,
            group_id=group_id, jobs=jobs, max_attempts=payload.max_attempts,
        )
    except (ValueError, DuplicateKeyError, ParallelJobConflict) as exc:
        await _audit(audit, principal, organization_id, project_id,
                     "nexus.parallel_jobs.create", "denied",
                     {"group_id": group_id, "error_type": type(exc).__name__})
        raise HTTPException(status_code=409 if isinstance(exc, DuplicateKeyError) else 422,
                            detail={"code": "PARALLEL_JOB_GROUP_INVALID",
                                    "message": "The job group could not be created safely."}) from exc
    except PyMongoError as exc:
        logger.error("Parallel job group persistence failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "PARALLEL_JOB_STORAGE_UNAVAILABLE"}) from exc
    await _audit(audit, principal, organization_id, project_id,
                 "nexus.parallel_jobs.create", "success",
                 {"group_id": group_id, "job_count": len(created)})
    return {
        "group_id": group_id,
        "jobs": [{"job_id": job.id, "status": job.status, "version": job.version}
                 for job in created],
    }


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/jobs/{{job_id}}",
    tags=["nexus-jobs"],
)
async def get_parallel_job(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    job_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
):
    store, audit, _project = await _authorize(request, organization_id, project_id, principal)
    try:
        job = await store.get(organization_id=organization_id, project_id=project_id, job_id=job_id)
        await _audit(audit, principal, organization_id, project_id,
                     "nexus.parallel_jobs.read", "success", {"job_id": job_id, "found": job is not None})
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "PARALLEL_JOB_STORAGE_UNAVAILABLE"}) from exc
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "PARALLEL_JOB_NOT_FOUND"})
    return {
        "job_id": job.id, "group_id": job.group_id, "status": job.status,
        "version": job.version, "attempt": job.attempt, "max_attempts": job.max_attempts,
        "has_checkpoint": job.checkpoint is not None, "checkpoint_sha256": job.checkpoint_sha256,
    }


@router.delete(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/job-groups/{{group_id}}",
    tags=["nexus-jobs"],
)
async def cancel_parallel_job_group(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    group_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
):
    store, audit, _project = await _authorize(request, organization_id, project_id, principal)
    await _audit(audit, principal, organization_id, project_id,
                 "nexus.parallel_jobs.cancel", "started", {"group_id": group_id})
    try:
        cancelled = await store.cancel_group(
            organization_id=organization_id, project_id=project_id, group_id=group_id,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "PARALLEL_JOB_STORAGE_UNAVAILABLE"}) from exc
    await _audit(audit, principal, organization_id, project_id,
                 "nexus.parallel_jobs.cancel", "success",
                 {"group_id": group_id, "cancelled_count": cancelled})
    return {"group_id": group_id, "cancelled_count": cancelled}
