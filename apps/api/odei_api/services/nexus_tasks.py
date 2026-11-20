"""Project-authorized durable NEXUS task API.

Planning is cloud-model work requiring explicit consent. Approval records intent only;
it does not execute code, write files, or launch a command.
"""
from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from odei_api.config import get_settings
from odei_api.model_client import ModelConfigurationError, get_openai_client
from odei_api.security.auth import Principal, get_current_principal, require_organization_membership
from odei_api.services.planning import PlanningError, create_task_plan
from odei_api.services.project_access import require_project_access
from odei_api.services.tasks import InvalidTaskTransition, TaskRecord, TaskStatus

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()
principal_dependency = Depends(get_current_principal)


class CreateProjectTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    task: str = Field(min_length=1, max_length=8_000)
    project_context: str = Field(default="", max_length=24_000)
    cloud_model_consent: StrictBool


class TaskTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)


async def _authorize_project(request: Request, organization_id: str, project_id: str, principal: Principal):
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(status_code=503, detail={"code": "PROJECT_STORE_UNAVAILABLE", "message": "Project storage is not configured."})
    await require_organization_membership(
        database["organization_memberships"], principal=principal, organization_id=organization_id
    )
    return await require_project_access(
        database["projects"], database["project_memberships"],
        organization_id=organization_id, project_id=project_id,
        identity_issuer=principal.issuer, identity_subject=principal.subject,
    )


async def _audit_task_action(request: Request, principal: Principal, organization_id: str, task_id: str, action: str, outcome: str, metadata: dict | None = None) -> None:
    store = getattr(request.app.state, "audit_event_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is not available."})
    try:
        await store.append(
            organization_id=organization_id, actor_issuer=principal.issuer,
            actor_subject=principal.subject, action=action, target_type="nexus_task",
            target_id=task_id, outcome=outcome, request_id=uuid4().hex,
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.error("NEXUS task audit append failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is temporarily unavailable."}) from exc


def _task_response(task: TaskRecord) -> dict:
    return {
        "task_id": task.id, "organization_id": task.organization_id,
        "project_id": task.project_id, "owner_id": task.owner_id,
        "goal": task.goal, "status": task.status.value, "plan": task.plan,
        "version": task.version,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/tasks",
    tags=["nexus"],
)
async def create_project_task(
    payload: CreateProjectTaskRequest, request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    """Create an approval-ready task after org/project authorization and model consent."""
    if organization_id != organization_id.strip() or project_id != project_id.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_RESOURCE_ID", "message": "Resource identifier is invalid."})
    if payload.cloud_model_consent is not True:
        raise HTTPException(status_code=400, detail={"code": "CLOUD_MODEL_CONSENT_REQUIRED", "message": "Explicit consent is required before sending task data to the cloud model."})
    try:
        await _authorize_project(request, organization_id, project_id, principal)
    except PyMongoError as exc:
        logger.warning("NEXUS project authorization lookup failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "PROJECT_STORE_UNAVAILABLE", "message": "Project authorization storage is temporarily unavailable."}) from exc
    task_store = getattr(request.app.state, "task_store", None)
    if task_store is None:
        raise HTTPException(status_code=503, detail={"code": "TASK_STORE_UNAVAILABLE", "message": "NEXUS task storage is not configured."})
    task_id = uuid4().hex
    try:
        client, model = get_openai_client()
        plan = await run_in_threadpool(
            create_task_plan, client, model=model, task=payload.task,
            project_context=payload.project_context, cloud_model_consent=True,
        )
        task = await task_store.create_planned(
            TaskRecord(
                id=task_id, organization_id=organization_id, project_id=project_id,
                owner_id=principal.subject, goal=payload.task,
            ),
            plan=plan.text,
        )
    except ModelConfigurationError as exc:
        raise HTTPException(status_code=503, detail={"code": "MODEL_NOT_CONFIGURED", "message": "The NEXUS model provider is not configured."}) from exc
    except (PlanningError, ValueError) as exc:
        raise HTTPException(status_code=502, detail={"code": "NEXUS_PLANNING_FAILED", "message": "NEXUS could not produce a usable plan."}) from exc
    except PyMongoError as exc:
        logger.warning("NEXUS planned task persistence failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "TASK_STORE_UNAVAILABLE", "message": "NEXUS task storage is temporarily unavailable."}) from exc
    await _audit_task_action(
        request, principal, organization_id, task_id, "nexus.task.create", "success",
        {"project_id": project_id, "model": plan.model, "status": task.status.value},
    )
    return _task_response(task)


async def _load_authorized_task(request: Request, organization_id: str, project_id: str, task_id: str, principal: Principal):
    project = await _authorize_project(request, organization_id, project_id, principal)
    store = getattr(request.app.state, "task_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "TASK_STORE_UNAVAILABLE", "message": "NEXUS task storage is not configured."})
    task = await store.get(organization_id=organization_id, task_id=task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Task was not found."})
    is_project_owner = project.get("owner_issuer") == principal.issuer and project.get("owner_subject") == principal.subject
    if task.owner_id != principal.subject and not is_project_owner:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Task was not found."})
    return project, store, task


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/tasks/{{task_id}}",
    tags=["nexus"],
)
async def get_project_task(
    request: Request, organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    task_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    try:
        _, _, task = await _load_authorized_task(request, organization_id, project_id, task_id, principal)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "TASK_STORE_UNAVAILABLE", "message": "Task storage is temporarily unavailable."}) from exc
    return _task_response(task)


async def _transition_project_task(
    request: Request, organization_id: str, project_id: str, task_id: str,
    payload: TaskTransitionRequest, principal: Principal, next_status: TaskStatus,
) -> dict:
    try:
        _, store, _task = await _load_authorized_task(request, organization_id, project_id, task_id, principal)
        updated = await store.transition(
            organization_id=organization_id, task_id=task_id,
            next_status=next_status, expected_version=payload.expected_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Task was not found."}) from exc
    except InvalidTaskTransition as exc:
        raise HTTPException(status_code=409, detail={"code": "TASK_VERSION_OR_STATE_CONFLICT", "message": "Task state changed or this transition is not allowed."}) from exc
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "TASK_STORE_UNAVAILABLE", "message": "Task storage is temporarily unavailable."}) from exc
    action = "nexus.task.approve" if next_status is TaskStatus.APPROVED else "nexus.task.cancel"
    await _audit_task_action(request, principal, organization_id, task_id, action, "success", {"version": updated.version})
    return _task_response(updated)


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/tasks/{{task_id}}/approve",
    tags=["nexus"],
)
async def approve_project_task(
    payload: TaskTransitionRequest, request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    task_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    """Record human approval. Execution remains a separate, not-yet-enabled operation."""
    return await _transition_project_task(request, organization_id, project_id, task_id, payload, principal, TaskStatus.APPROVED)


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/tasks/{{task_id}}/cancel",
    tags=["nexus"],
)
async def cancel_project_task(
    payload: TaskTransitionRequest, request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    task_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    """Cancel an uncompleted task with optimistic concurrency control."""
    return await _transition_project_task(request, organization_id, project_id, task_id, payload, principal, TaskStatus.CANCELLED)
