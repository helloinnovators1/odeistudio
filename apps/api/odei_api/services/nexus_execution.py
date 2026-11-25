"""Authenticated, approval-gated NEXUS execution API."""
from __future__ import annotations

import base64
import binascii
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr
from pymongo.errors import DuplicateKeyError, PyMongoError
from starlette.concurrency import run_in_threadpool

from odei_api.config import get_settings
from odei_api.security.auth import Principal, get_current_principal, require_organization_membership
from odei_api.services.execution_diagnostics import build_execution_diagnostics
from odei_api.services.execution_runs import ExecutionRun, ExecutionRunConflict
from odei_api.services.nexus_capabilities import NexusCapabilityDenied, NexusCapabilityPolicy
from odei_api.services.project_access import require_project_access
from odei_api.services.tasks import TaskStatus, identity_owner_key
from odei_api.services.workspace_snapshots import SnapshotError, WorkspaceSnapshotIngestor

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()
principal_dependency = Depends(get_current_principal)
_MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
_MAX_BASE64_CHARS = ((_MAX_ARCHIVE_BYTES + 2) // 3) * 4


class CreateExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: StrictStr = Field(min_length=1, max_length=64)
    mode: StrictStr = Field(min_length=1, max_length=16)
    expected_task_version: int = Field(ge=0)
    workspace_upload_consent: StrictBool
    execution_consent: StrictBool
    snapshot_zip_base64: StrictStr = Field(min_length=1, max_length=_MAX_BASE64_CHARS)


async def _authorize_execution_resource(
    request: Request, organization_id: str, project_id: str, task_id: str,
    principal: Principal,
):
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(status_code=503, detail={
            "code": "EXECUTION_STORAGE_UNAVAILABLE",
            "message": "Execution storage is not configured.",
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
            "code": "EXECUTION_AUTHORIZATION_UNAVAILABLE",
            "message": "Execution authorization storage is temporarily unavailable.",
        }) from exc
    except HTTPException:
        raise
    tasks = getattr(request.app.state, "task_store", None)
    if tasks is None:
        raise HTTPException(status_code=503, detail={
            "code": "TASK_STORE_UNAVAILABLE", "message": "NEXUS task storage is not configured.",
        })
    task = await tasks.get(organization_id=organization_id, task_id=task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail={
            "code": "TASK_NOT_FOUND", "message": "Task was not found.",
        })
    is_project_owner = (
        project.get("owner_issuer") == principal.issuer
        and project.get("owner_subject") == principal.subject
    )
    if task.owner_id != identity_owner_key(principal.issuer, principal.subject) and not is_project_owner:
        raise HTTPException(status_code=404, detail={
            "code": "TASK_NOT_FOUND", "message": "Task was not found.",
        })
    return database, project, task


def _audit_event(principal: Principal, organization_id: str, run_id: str,
                 action: str, metadata: dict | None = None) -> dict:
    return {
        "organization_id": organization_id, "actor_issuer": principal.issuer,
        "actor_subject": principal.subject, "action": action,
        "target_type": "nexus_execution_run", "target_id": run_id,
        "outcome": "success", "request_id": uuid4().hex,
        "metadata": metadata or {},
    }


async def _append_decision(request: Request, principal: Principal,
                           organization_id: str, run_id: str,
                           action: str, outcome: str,
                           metadata: dict | None = None) -> None:
    audit = getattr(request.app.state, "audit_event_store", None)
    if audit is None:
        raise HTTPException(status_code=503, detail={
            "code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is unavailable.",
        })
    await audit.append(
        organization_id=organization_id, actor_issuer=principal.issuer,
        actor_subject=principal.subject, action=action,
        target_type="nexus_execution_run", target_id=run_id,
        outcome=outcome, request_id=uuid4().hex, metadata=metadata or {},
    )


def _public_run(run: ExecutionRun) -> dict:
    return {
        "run_id": run.id, "organization_id": run.organization_id,
        "project_id": run.project_id, "task_id": run.task_id,
        "profile_id": run.profile_id, "snapshot_sha256": run.snapshot_sha256,
        "status": run.status.value, "version": run.version,
        "attempts": run.attempts, "max_attempts": run.max_attempts,
        "cancel_requested": run.cancel_requested,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def _validate_archive(archive: bytes) -> tuple[str, int, int]:
    with tempfile.TemporaryDirectory(prefix="odei-snapshot-validate-") as temporary:
        root = Path(temporary)
        record = WorkspaceSnapshotIngestor(root).ingest(archive)
        return record.sha256, record.file_count, record.total_bytes


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/executions",
    tags=["execution"],
)
async def list_project_executions(
    request: Request,
    organization_id: str = PathParam(min_length=1, max_length=128),
    project_id: str = PathParam(min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=100),
    before_created_at: datetime | None = None,
    before_run_id: str | None = None,
    principal: Principal = principal_dependency,
) -> dict:
    """List durable project execution history; members see only runs they requested."""
    if before_run_id is not None and (
        len(before_run_id) > 128 or not before_run_id
        or not before_run_id[0].isalnum()
        or any(not (char.isalnum() or char in "_.:@/-") for char in before_run_id)
    ):
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_EXECUTION_CURSOR",
            "message": "The execution history cursor is invalid.",
        })
    if (before_created_at is None) != (before_run_id is None):
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_EXECUTION_CURSOR",
            "message": "Both before_created_at and before_run_id are required for pagination.",
        })
    database = getattr(request.app.state, "mongo_database", None)
    store = getattr(request.app.state, "execution_run_store", None)
    if database is None or store is None:
        raise HTTPException(status_code=503, detail={
            "code": "EXECUTION_STORAGE_UNAVAILABLE",
            "message": "Execution history storage is not configured.",
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
        is_owner = (
            project.get("owner_issuer") == principal.issuer
            and project.get("owner_subject") == principal.subject
        )
        rows, has_more = await store.list_for_project(
            organization_id=organization_id, project_id=project_id, limit=limit,
            requester_issuer=None if is_owner else principal.issuer,
            requester_subject=None if is_owner else principal.subject,
            before_created_at=before_created_at, before_run_id=before_run_id,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={
            "code": "EXECUTION_HISTORY_UNAVAILABLE",
            "message": "Execution history is temporarily unavailable.",
        }) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_EXECUTION_CURSOR",
            "message": "The execution history cursor is invalid.",
        }) from exc

    audit = getattr(request.app.state, "audit_event_store", None)
    if audit is None:
        raise HTTPException(status_code=503, detail={
            "code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is unavailable.",
        })
    try:
        await audit.append(
            organization_id=organization_id, actor_issuer=principal.issuer,
            actor_subject=principal.subject, action="nexus.execution.history.read",
            target_type="nexus_project", target_id=project_id, outcome="success",
            request_id=uuid4().hex,
            metadata={"returned_count": len(rows), "has_more": has_more,
                      "owner_scope": is_owner},
        )
    except Exception as exc:
        logger.error("NEXUS execution history audit failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail={
            "code": "AUDIT_STORE_UNAVAILABLE", "message": "Execution history could not be audited.",
        }) from exc
    next_cursor = None
    if rows and has_more:
        last = rows[-1]
        next_cursor = {
            "before_created_at": last.created_at.isoformat() if last.created_at else None,
            "before_run_id": last.id,
        }
    return {
        "runs": [_public_run(run) for run in rows],
        "has_more": has_more, "next_cursor": next_cursor,
    }


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/execution/profiles",
    tags=["execution"],
)
async def list_execution_profiles(
    request: Request,
    organization_id: str = PathParam(min_length=1, max_length=128),
    project_id: str = PathParam(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(status_code=503, detail={"code": "EXECUTION_STORAGE_UNAVAILABLE", "message": "Execution storage is not configured."})
    try:
        await require_organization_membership(database["organization_memberships"], principal=principal, organization_id=organization_id)
        await require_project_access(database["projects"], database["project_memberships"],
            organization_id=organization_id, project_id=project_id,
            identity_issuer=principal.issuer, identity_subject=principal.subject)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "EXECUTION_AUTHORIZATION_UNAVAILABLE", "message": "Execution authorization is temporarily unavailable."}) from exc
    registry = getattr(request.app.state, "execution_profile_registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail={"code": "EXECUTION_PROFILES_UNAVAILABLE", "message": "No approved execution profiles are configured."})
    return {"profiles": [{"profile_id": name} for name in registry.names]}


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/tasks/{{task_id}}/executions",
    tags=["execution"],
)
async def create_execution(
    payload: CreateExecutionRequest, request: Request,
    organization_id: str = PathParam(min_length=1, max_length=128),
    project_id: str = PathParam(min_length=1, max_length=128),
    task_id: str = PathParam(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    if organization_id != organization_id.strip() or project_id != project_id.strip() or task_id != task_id.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_RESOURCE_ID", "message": "Resource identifier is invalid."})
    try:
        NexusCapabilityPolicy.require(payload.mode, "execution.run")
    except NexusCapabilityDenied as exc:
        raise HTTPException(status_code=403, detail={"code": "NEXUS_MODE_CAPABILITY_DENIED", "message": "Switch to Agent mode to request approved execution."}) from exc
    if payload.workspace_upload_consent is not True or payload.execution_consent is not True:
        raise HTTPException(status_code=400, detail={"code": "EXECUTION_CONSENT_REQUIRED", "message": "Separate explicit workspace-upload and code-execution consent are required."})
    database, _project, task = await _authorize_execution_resource(request, organization_id, project_id, task_id, principal)
    if task.status is not TaskStatus.APPROVED:
        raise HTTPException(status_code=409, detail={"code": "TASK_APPROVAL_REQUIRED", "message": "The project owner must approve this task before execution."})
    if task.version != payload.expected_task_version:
        raise HTTPException(status_code=409, detail={"code": "TASK_VERSION_CONFLICT", "message": "The approved task changed. Reload it before execution."})
    registry = getattr(request.app.state, "execution_profile_registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail={"code": "EXECUTION_PROFILES_UNAVAILABLE", "message": "No approved execution profiles are configured."})
    try:
        registry.get(payload.profile_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"code": "EXECUTION_PROFILE_NOT_ALLOWED", "message": "The requested execution profile is not approved."}) from exc
    try:
        archive = base64.b64decode(payload.snapshot_zip_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_SNAPSHOT_ENCODING", "message": "The workspace archive encoding is invalid."}) from exc
    if not archive or len(archive) > _MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail={"code": "SNAPSHOT_SIZE_LIMIT", "message": "The workspace archive is empty or exceeds the upload limit."})
    try:
        digest, file_count, total_bytes = await run_in_threadpool(_validate_archive, archive)
    except SnapshotError as exc:
        raise HTTPException(status_code=422, detail={"code": "UNSAFE_WORKSPACE_SNAPSHOT", "message": "The workspace archive did not pass snapshot safety checks."}) from exc
    snapshots = getattr(request.app.state, "workspace_snapshot_store", None)
    runs = getattr(request.app.state, "execution_run_store", None)
    if snapshots is None or runs is None:
        raise HTTPException(status_code=503, detail={"code": "EXECUTION_STORAGE_UNAVAILABLE", "message": "Durable execution storage is not configured."})
    run_id = uuid4().hex
    snapshot = None
    try:
        snapshot = await snapshots.put(
            organization_id=organization_id, project_id=project_id, task_id=task_id,
            owner_issuer=principal.issuer, owner_subject=principal.subject,
            archive=archive, sha256=digest, file_count=file_count, total_bytes=total_bytes,
        )
        run = ExecutionRun(
            id=run_id, organization_id=organization_id, project_id=project_id,
            task_id=task_id, requester_issuer=principal.issuer,
            requester_subject=principal.subject, profile_id=payload.profile_id,
            snapshot_sha256=digest, arguments=(), snapshot_id=snapshot["snapshot_id"],
        )
        await runs.create_approved_task_run(
            run, tasks=database["tasks"], task_events=database["task_events"],
            expected_task_version=payload.expected_task_version,
            audit_event=_audit_event(principal, organization_id, run_id,
                "nexus.execution.create", {"project_id": project_id, "task_id": task_id,
                "profile_id": payload.profile_id, "mode": payload.mode,
                "snapshot_id": snapshot["snapshot_id"],
                "snapshot_file_count": file_count, "snapshot_bytes": total_bytes}),
        )
    except ExecutionRunConflict as exc:
        if snapshot is not None:
            await snapshots.delete_for_tenant(organization_id=organization_id, project_id=project_id, snapshot_id=snapshot["snapshot_id"])
        raise HTTPException(status_code=409, detail={"code": "EXECUTION_STATE_CONFLICT", "message": "The task changed or already has an active execution."}) from exc
    except DuplicateKeyError as exc:
        if snapshot is not None:
            await snapshots.delete_for_tenant(organization_id=organization_id, project_id=project_id, snapshot_id=snapshot["snapshot_id"])
        raise HTTPException(status_code=409, detail={"code": "ACTIVE_EXECUTION_EXISTS", "message": "This task already has an active execution."}) from exc
    except Exception as exc:
        if snapshot is not None:
            try:
                await snapshots.delete_for_tenant(organization_id=organization_id, project_id=project_id, snapshot_id=snapshot["snapshot_id"])
            except Exception:
                logger.exception("Failed to clean up an unreferenced workspace snapshot")
        if isinstance(exc, PyMongoError):
            raise HTTPException(status_code=503, detail={"code": "EXECUTION_STORAGE_UNAVAILABLE", "message": "Execution storage is temporarily unavailable."}) from exc
        raise
    return {
        "run_id": run_id, "status": "queued", "task_id": task_id,
        "snapshot": snapshot, "profile_id": payload.profile_id,
    }


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/tasks/{{task_id}}/executions/{{run_id}}",
    tags=["execution"],
)
async def get_execution(
    request: Request, organization_id: str = PathParam(min_length=1, max_length=128),
    project_id: str = PathParam(min_length=1, max_length=128),
    task_id: str = PathParam(min_length=1, max_length=128),
    run_id: str = PathParam(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    await _authorize_execution_resource(request, organization_id, project_id, task_id, principal)
    store = getattr(request.app.state, "execution_run_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "EXECUTION_STORAGE_UNAVAILABLE", "message": "Execution storage is not configured."})
    run = await store.get(organization_id=organization_id, run_id=run_id)
    if run is None or run.project_id != project_id or run.task_id != task_id:
        raise HTTPException(status_code=404, detail={"code": "EXECUTION_NOT_FOUND", "message": "Execution run was not found."})
    await _append_decision(request, principal, organization_id, run_id, "nexus.execution.read", "success", {"status": run.status.value})
    return _public_run(run)


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/tasks/{{task_id}}/executions/{{run_id}}/events",
    tags=["execution"],
)
async def list_execution_events(
    request: Request, organization_id: str = PathParam(min_length=1, max_length=128),
    project_id: str = PathParam(min_length=1, max_length=128),
    task_id: str = PathParam(min_length=1, max_length=128),
    run_id: str = PathParam(min_length=1, max_length=128),
    after_version: int = Query(default=-1, ge=-1), limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = principal_dependency,
) -> dict:
    await _authorize_execution_resource(request, organization_id, project_id, task_id, principal)
    store = getattr(request.app.state, "execution_run_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "EXECUTION_STORAGE_UNAVAILABLE", "message": "Execution storage is not configured."})
    run = await store.get(organization_id=organization_id, run_id=run_id)
    if run is None or run.project_id != project_id or run.task_id != task_id:
        raise HTTPException(status_code=404, detail={"code": "EXECUTION_NOT_FOUND", "message": "Execution run was not found."})
    rows, has_more = await store.list_events(organization_id=organization_id, run_id=run_id, after_version=after_version, limit=limit)
    events = [{"event_id": row["event_id"], "type": row["type"], "version": row["version"],
        "occurred_at": row["occurred_at"].isoformat(),
        **({"from_status": row["from_status"]} if "from_status" in row else {}),
        **({"to_status": row["to_status"]} if "to_status" in row else {})} for row in rows]
    next_cursor = events[-1]["version"] if events else after_version
    await _append_decision(request, principal, organization_id, run_id, "nexus.execution.events.read", "success",
        {"after_version": after_version, "limit": limit, "returned_count": len(events), "has_more": has_more})
    return {"events": events, "has_more": has_more, "next_after_version": next_cursor}


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/tasks/{{task_id}}/executions/{{run_id}}/cancel",
    tags=["execution"],
)
async def cancel_execution(
    request: Request, organization_id: str = PathParam(min_length=1, max_length=128),
    project_id: str = PathParam(min_length=1, max_length=128),
    task_id: str = PathParam(min_length=1, max_length=128),
    run_id: str = PathParam(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    database, _, _ = await _authorize_execution_resource(request, organization_id, project_id, task_id, principal)
    store = getattr(request.app.state, "execution_run_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "EXECUTION_STORAGE_UNAVAILABLE", "message": "Execution storage is not configured."})
    run = await store.get(organization_id=organization_id, run_id=run_id)
    if run is None or run.project_id != project_id or run.task_id != task_id:
        raise HTTPException(status_code=404, detail={"code": "EXECUTION_NOT_FOUND", "message": "Execution run was not found."})
    try:
        updated = await store.request_cancel(
            organization_id=organization_id, run_id=run_id,
            actor_id="authenticated-user",
            audit_event=_audit_event(principal, organization_id, run_id, "nexus.execution.cancel"),
            tasks=database["tasks"], task_events=database["task_events"],
            task_audit_event={
                "organization_id": organization_id, "actor_issuer": principal.issuer,
                "actor_subject": principal.subject, "action": "nexus.task.cancel",
                "target_type": "nexus_task", "target_id": task_id,
                "outcome": "success", "request_id": uuid4().hex,
                "metadata": {"source": "execution_cancel"},
            },
        )
    except ExecutionRunConflict as exc:
        raise HTTPException(status_code=409, detail={"code": "EXECUTION_STATE_CONFLICT", "message": "The execution run cannot be cancelled in its current state."}) from exc
    await _append_decision(request, principal, organization_id, run_id, "nexus.execution.cancel", "success", {"status": updated.status.value})
    return _public_run(updated)

@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/tasks/{{task_id}}/executions/{{run_id}}/artifacts",
    tags=["execution"],
)
async def get_execution_artifacts(
    request: Request, organization_id: str = PathParam(min_length=1, max_length=128),
    project_id: str = PathParam(min_length=1, max_length=128),
    task_id: str = PathParam(min_length=1, max_length=128),
    run_id: str = PathParam(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    await _authorize_execution_resource(request, organization_id, project_id, task_id, principal)
    runs = getattr(request.app.state, "execution_run_store", None)
    artifacts = getattr(request.app.state, "execution_artifact_store", None)
    if runs is None or artifacts is None:
        raise HTTPException(status_code=503, detail={"code": "EXECUTION_STORAGE_UNAVAILABLE", "message": "Execution storage is not configured."})
    run = await runs.get(organization_id=organization_id, run_id=run_id)
    if run is None or run.project_id != project_id or run.task_id != task_id:
        raise HTTPException(status_code=404, detail={"code": "EXECUTION_NOT_FOUND", "message": "Execution run was not found."})
    result = await artifacts.get_for_tenant(
        organization_id=organization_id, project_id=project_id,
        task_id=task_id, run_id=run_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "EXECUTION_ARTIFACTS_NOT_FOUND", "message": "Execution artifacts are not available."})
    await _append_decision(request, principal, organization_id, run_id,
        "nexus.execution.artifacts.read", "success",
        {"stdout_bytes": result["stdout_bytes"], "stderr_bytes": result["stderr_bytes"]})
    return result


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/tasks/{{task_id}}/executions/{{run_id}}/diagnostics",
    tags=["execution"],
)
async def get_execution_diagnostics(
    request: Request, organization_id: str = PathParam(min_length=1, max_length=128),
    project_id: str = PathParam(min_length=1, max_length=128),
    task_id: str = PathParam(min_length=1, max_length=128),
    run_id: str = PathParam(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    """Return bounded, deterministic diagnostics for an authorized execution result."""
    await _authorize_execution_resource(request, organization_id, project_id, task_id, principal)
    runs = getattr(request.app.state, "execution_run_store", None)
    artifacts = getattr(request.app.state, "execution_artifact_store", None)
    if runs is None or artifacts is None:
        raise HTTPException(status_code=503, detail={
            "code": "EXECUTION_STORAGE_UNAVAILABLE",
            "message": "Execution storage is not configured.",
        })
    run = await runs.get(organization_id=organization_id, run_id=run_id)
    if run is None or run.project_id != project_id or run.task_id != task_id:
        raise HTTPException(status_code=404, detail={
            "code": "EXECUTION_NOT_FOUND", "message": "Execution run was not found.",
        })
    result = await artifacts.get_for_tenant(
        organization_id=organization_id, project_id=project_id,
        task_id=task_id, run_id=run_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail={
            "code": "EXECUTION_ARTIFACTS_NOT_FOUND",
            "message": "Execution artifacts are not available.",
        })
    report = build_execution_diagnostics(result)
    await _append_decision(
        request, principal, organization_id, run_id,
        "nexus.execution.diagnostics.read", "success",
        {"category": report["category"], "evidence_count": len(report["evidence"])},
    )
    return {"run_id": run_id, **report}
