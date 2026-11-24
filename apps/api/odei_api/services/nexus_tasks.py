"""Project-authorized durable NEXUS task API.

Planning is cloud-model work requiring explicit consent. Approval records intent only;
it does not execute code, write files, or launch a command.
"""
from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from odei_api.config import get_settings
from odei_api.model_client import ModelConfigurationError, get_openai_client
from odei_api.security.auth import Principal, get_current_principal, require_organization_membership
from odei_api.services.execution_runs import ExecutionRunConflict
from odei_api.services.nexus_chat import NexusChatError, run_nexus_chat, stream_nexus_chat
from odei_api.services.planning import PlanningError, create_task_plan
from odei_api.services.project_access import require_project_access
from odei_api.services.tasks import (
    InvalidTaskTransition,
    TaskRecord,
    TaskStatus,
    identity_owner_key,
)

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()
principal_dependency = Depends(get_current_principal)


class CreateProjectTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    task: str = Field(min_length=1, max_length=8_000)
    project_context: str = Field(default="", max_length=24_000)
    cloud_model_consent: StrictBool


class NexusChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    messages: list[dict[str, StrictStr]] = Field(min_length=1, max_length=20)
    workspace_files: list[dict[str, StrictStr]] = Field(default_factory=list, max_length=5)
    cloud_model_consent: StrictBool
    conversation_id: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    mode: Literal["ask", "debug", "agent"] = "ask"


async def _append_nexus_chat_audit(
    request: Request,
    principal: Principal,
    organization_id: str,
    project_id: str,
    *,
    outcome: str,
    message_count: int,
    file_count: int,
    model: str | None = None,
    tool_calls: int = 0,
    mode: str = "ask",
) -> None:
    """Audit chat access without recording prompts, source text or model output."""
    store = getattr(request.app.state, "audit_event_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is not available."},
        )
    metadata = {"message_count": message_count, "workspace_file_count": file_count, "mode": mode}
    if model:
        metadata["model"] = model
    if tool_calls:
        metadata["tool_call_count"] = tool_calls
    try:
        await store.append(
            organization_id=organization_id,
            actor_issuer=principal.issuer,
            actor_subject=principal.subject,
            action="nexus.chat.request",
            target_type="project",
            target_id=project_id,
            outcome=outcome,
            request_id=uuid4().hex,
            metadata=metadata,
        )
    except Exception as exc:
        logger.error("NEXUS chat audit append failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Chat audit storage is temporarily unavailable."},
        ) from exc


class TaskTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)


async def _authorize_project(request: Request, organization_id: str, project_id: str, principal: Principal):
    database = getattr(request.app.state, "mongo_database", None)
    if database is None:
        raise HTTPException(status_code=503, detail={"code": "PROJECT_STORE_UNAVAILABLE", "message": "Project storage is not configured."})
    try:
        await require_organization_membership(
            database["organization_memberships"], principal=principal, organization_id=organization_id
        )
        return await require_project_access(
            database["projects"], database["project_memberships"],
            organization_id=organization_id, project_id=project_id,
            identity_issuer=principal.issuer, identity_subject=principal.subject,
        )
    except HTTPException as exc:
        if exc.status_code in (403, 404):
            audit = getattr(request.app.state, "audit_event_store", None)
            if audit is None:
                raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Authorization audit storage is not available."}) from exc
            try:
                await audit.append(
                    organization_id=organization_id, actor_issuer=principal.issuer,
                    actor_subject=principal.subject, action="nexus.project.access",
                    target_type="project", target_id=project_id, outcome="denied",
                    request_id=uuid4().hex, metadata={"reason": "project_access_denied"},
                )
            except Exception as audit_error:
                raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Authorization audit storage is temporarily unavailable."}) from audit_error
        raise


def _task_audit_event(
    principal: Principal, organization_id: str, task_id: str,
    action: str, metadata: dict | None = None, outcome: str = "success",
) -> dict:
    """Build a redacted, tenant-scoped event for the task-store transaction."""
    return {
        "organization_id": organization_id,
        "actor_issuer": principal.issuer,
        "actor_subject": principal.subject,
        "action": action,
        "target_type": "nexus_task",
        "target_id": task_id,
        "outcome": outcome,
        "request_id": uuid4().hex,
        "metadata": metadata or {},
    }



async def _append_task_audit_decision(
    request: Request, principal: Principal, organization_id: str, task_id: str,
    action: str, outcome: str, reason: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Persist read/denial decisions before returning a response."""
    store = getattr(request.app.state, "audit_event_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is not available."},
        )
    event_metadata = dict(metadata or {})
    if reason:
        event_metadata["reason"] = reason
    try:
        await store.append(**_task_audit_event(
            principal, organization_id, task_id, action,
            event_metadata, outcome=outcome,
        ))
    except Exception as exc:
        logger.error("NEXUS task decision audit append failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is temporarily unavailable."},
        ) from exc


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
                owner_id=identity_owner_key(principal.issuer, principal.subject), goal=payload.task,
            ),
            plan=plan.text,
            audit_event=_task_audit_event(
                principal, organization_id, task_id, "nexus.task.create",
                {"project_id": project_id, "model": plan.model, "status": TaskStatus.AWAITING_APPROVAL.value},
            ),
        )
    except ModelConfigurationError as exc:
        raise HTTPException(status_code=503, detail={"code": "MODEL_NOT_CONFIGURED", "message": "The NEXUS model provider is not configured."}) from exc
    except (PlanningError, ValueError) as exc:
        raise HTTPException(status_code=502, detail={"code": "NEXUS_PLANNING_FAILED", "message": "NEXUS could not produce a usable plan."}) from exc
    except RuntimeError as exc:
        logger.error("NEXUS task transaction or audit store failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Task and audit storage are temporarily unavailable."}) from exc
    except PyMongoError as exc:
        logger.warning("NEXUS planned task persistence failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "TASK_STORE_UNAVAILABLE", "message": "NEXUS task storage is temporarily unavailable."}) from exc
    return _task_response(task)


async def _load_authorized_task(
    request: Request, organization_id: str, project_id: str, task_id: str,
    principal: Principal, *, audit_action: str = "nexus.task.read",
):
    project = await _authorize_project(request, organization_id, project_id, principal)
    store = getattr(request.app.state, "task_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "TASK_STORE_UNAVAILABLE", "message": "NEXUS task storage is not configured."})
    task = await store.get(organization_id=organization_id, task_id=task_id)
    if task is None or task.project_id != project_id:
        await _append_task_audit_decision(
            request, principal, organization_id, task_id, audit_action,
            "denied", reason="task_not_found_or_project_mismatch",
        )
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Task was not found."})
    is_project_owner = project.get("owner_issuer") == principal.issuer and project.get("owner_subject") == principal.subject
    if task.owner_id != identity_owner_key(principal.issuer, principal.subject) and not is_project_owner:
        await _append_task_audit_decision(
            request, principal, organization_id, task_id, audit_action,
            "denied", reason="task_owner_required",
        )
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
    await _append_task_audit_decision(
        request, principal, organization_id, task_id, "nexus.task.read",
        "success", metadata={"status": task.status.value},
    )
    return _task_response(task)


async def _transition_project_task(
    request: Request, organization_id: str, project_id: str, task_id: str,
    payload: TaskTransitionRequest, principal: Principal, next_status: TaskStatus,
) -> dict:
    action = "nexus.task.approve" if next_status is TaskStatus.APPROVED else "nexus.task.cancel"
    try:
        project, store, _task = await _load_authorized_task(
            request, organization_id, project_id, task_id, principal, audit_action=action,
        )
        is_project_owner = project.get("owner_issuer") == principal.issuer and project.get("owner_subject") == principal.subject
        if next_status is TaskStatus.APPROVED and not is_project_owner:
            await _append_task_audit_decision(
                request, principal, organization_id, task_id, action,
                "denied", reason="project_owner_approval_required",
            )
            raise HTTPException(status_code=403, detail={"code": "PROJECT_OWNER_APPROVAL_REQUIRED", "message": "Only the project owner can approve this task."})
        cancelled_with_run = False
        if next_status is TaskStatus.CANCELLED:
            run_store = getattr(request.app.state, "execution_run_store", None)
            database = getattr(request.app.state, "mongo_database", None)
            if run_store is not None and database is not None:
                active_run = await run_store.get_active_for_task(
                    organization_id=organization_id, project_id=project_id, task_id=task_id,
                )
                if active_run is not None:
                    try:
                        cancellation = await run_store.request_cancel(
                            organization_id=organization_id, run_id=active_run.id,
                            actor_id="authenticated-user",
                            audit_event={
                                "organization_id": organization_id,
                                "actor_issuer": principal.issuer,
                                "actor_subject": principal.subject,
                                "action": "nexus.execution.cancel",
                                "target_type": "nexus_execution_run",
                                "target_id": active_run.id,
                                "outcome": "success",
                                "request_id": uuid4().hex,
                                "metadata": {"source": "task_cancel"},
                            },
                            tasks=database["tasks"], task_events=database["task_events"],
                            task_audit_event=_task_audit_event(
                                principal, organization_id, task_id, "nexus.task.cancel",
                                {"version": payload.expected_version + 1, "source": "task_cancel"},
                            ),
                        )
                        cancelled_with_run = cancellation.status.value == "cancelled"
                    except ExecutionRunConflict:
                        latest_run = await run_store.get(
                            organization_id=organization_id, run_id=active_run.id,
                        )
                        if latest_run is not None and latest_run.status.value not in {
                            "completed", "failed", "cancelled", "expired",
                        } and not latest_run.cancel_requested:
                            raise
        if cancelled_with_run:
            updated = await store.get(organization_id=organization_id, task_id=task_id)
            if updated is None or updated.status is not TaskStatus.CANCELLED:
                raise RuntimeError("Queued execution was cancelled but task state could not be confirmed")
        else:
            updated = await store.transition(
                organization_id=organization_id, task_id=task_id,
                next_status=next_status, expected_version=payload.expected_version,
                actor_id=identity_owner_key(principal.issuer, principal.subject),
                audit_event=_task_audit_event(
                    principal, organization_id, task_id,
                    "nexus.task.approve" if next_status is TaskStatus.APPROVED else "nexus.task.cancel",
                    {"version": payload.expected_version + 1},
                ),
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "Task was not found."}) from exc
    except (InvalidTaskTransition, ExecutionRunConflict) as exc:
        raise HTTPException(status_code=409, detail={"code": "TASK_VERSION_OR_STATE_CONFLICT", "message": "Task or execution state changed; reload before retrying."}) from exc
    except RuntimeError as exc:
        logger.error("NEXUS task transaction or audit store failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Task and audit storage are temporarily unavailable."}) from exc
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "TASK_STORE_UNAVAILABLE", "message": "Task storage is temporarily unavailable."}) from exc
    return _task_response(updated)


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/tasks/{{task_id}}/events",
    tags=["nexus"],
)
async def list_project_task_events(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    task_id: str = Path(min_length=1, max_length=128),
    after_version: int = Query(default=-1, ge=-1),
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = principal_dependency,
) -> dict:
    """Read ordered task lifecycle events with a reconnectable version cursor."""
    try:
        _, store, _ = await _load_authorized_task(
            request, organization_id, project_id, task_id, principal,
            audit_action="nexus.task.events.read",
        )
        rows, has_more = await store.list_events(
            organization_id=organization_id, task_id=task_id,
            after_version=after_version, limit=limit,
        )
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "TASK_STORE_UNAVAILABLE", "message": "Task event storage is temporarily unavailable."},
        ) from exc
    events = [{
        "event_id": row["event_id"],
        "type": row["type"],
        "version": row["version"],
        "from_status": row.get("from_status"),
        "to_status": row.get("to_status", row.get("status")),
        "occurred_at": row["occurred_at"].isoformat(),
    } for row in rows]
    next_cursor = events[-1]["version"] if events else after_version
    await _append_task_audit_decision(
        request, principal, organization_id, task_id, "nexus.task.events.read",
        "success", metadata={
            "after_version": after_version, "limit": limit,
            "returned_count": len(events), "has_more": has_more,
        },
    )
    return {"events": events, "has_more": has_more, "next_after_version": next_cursor}


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



@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/chat/stream",
    tags=["nexus"],
)
async def nexus_project_chat_stream(
    payload: NexusChatRequest,
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
):
    """Stream redacted model deltas over SSE and persist the completed assistant turn."""
    if organization_id != organization_id.strip() or project_id != project_id.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_RESOURCE_ID", "message": "Resource identifier is invalid."})
    if payload.mode not in {"ask", "debug"}:
        raise HTTPException(status_code=403, detail={"code": "NEXUS_MODE_FORBIDDEN", "message": "This endpoint permits only Ask or Debug mode."})
    if payload.cloud_model_consent is not True:
        raise HTTPException(status_code=400, detail={"code": "CLOUD_MODEL_CONSENT_REQUIRED", "message": "Explicit consent is required before sending chat or workspace data to the cloud model."})
    if payload.conversation_id is None:
        raise HTTPException(status_code=400, detail={"code": "CONVERSATION_REQUIRED", "message": "Streaming chat requires a saved conversation."})
    try:
        await _authorize_project(request, organization_id, project_id, principal)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "PROJECT_STORE_UNAVAILABLE", "message": "Project authorization storage is temporarily unavailable."}) from exc
    if not payload.messages or payload.messages[-1].get("role") != "user":
        raise HTTPException(status_code=422, detail={"code": "INVALID_CHAT_HISTORY", "message": "The final conversation message must be from the user."})
    conversation_store = getattr(request.app.state, "conversation_store", None)
    if conversation_store is None:
        raise HTTPException(status_code=503, detail={"code": "CONVERSATION_STORE_UNAVAILABLE", "message": "NEXUS conversation storage is not configured."})
    try:
        conversation = await conversation_store.get_for_owner(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=principal.issuer, owner_subject=principal.subject,
            conversation_id=payload.conversation_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation was not found."})
        persisted_user = await conversation_store.append(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=principal.issuer, owner_subject=principal.subject,
            conversation_id=payload.conversation_id, role="user",
            content=payload.messages[-1]["content"],
            expected_version=conversation["version"],
        )
        if persisted_user is None:
            raise HTTPException(status_code=409, detail={"code": "CONVERSATION_VERSION_CONFLICT", "message": "Conversation changed. Reload its history before sending another message."})
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "CONVERSATION_STORE_UNAVAILABLE", "message": "NEXUS conversation storage is temporarily unavailable."}) from exc

    model_messages = [
        {"role": item["role"], "content": item["content"]}
        for item in persisted_user["messages"][-19:]
    ]
    await _append_nexus_chat_audit(
        request, principal, organization_id, project_id,
        outcome="started", message_count=len(model_messages),
        file_count=len(payload.workspace_files), mode=payload.mode,
    )
    try:
        client, model = get_openai_client()
    except ModelConfigurationError as exc:
        await _append_nexus_chat_audit(
            request, principal, organization_id, project_id,
            outcome="failure", message_count=len(model_messages),
            file_count=len(payload.workspace_files), mode=payload.mode,
        )
        raise HTTPException(status_code=503, detail={"code": "MODEL_NOT_CONFIGURED", "message": "The NEXUS model provider is not configured."}) from exc

    events: queue.Queue[tuple[str, str | None]] = queue.Queue(maxsize=16)
    cancelled = threading.Event()

    def publish(kind: str, value: str | None = None) -> bool:
        while not cancelled.is_set():
            try:
                events.put((kind, value), timeout=0.25)
                return True
            except queue.Full:
                continue
        return False

    def provider_worker() -> None:
        try:
            for delta in stream_nexus_chat(
                client, model=model, messages=model_messages,
                workspace_files=payload.workspace_files, mode=payload.mode,
            ):
                if not publish("delta", delta):
                    return
            publish("complete")
        except Exception:  # noqa: BLE001 - provider SDK failures must become safe SSE errors
            publish("error", "NEXUS could not complete the streamed response.")

    def encode_event(name: str, data: dict) -> bytes:
        return (
            f"event: {name}\n"
            f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
        ).encode()

    async def event_stream():
        worker = asyncio.create_task(asyncio.to_thread(provider_worker))
        answer_parts: list[str] = []
        loop = asyncio.get_running_loop()
        last_heartbeat = loop.time()
        try:
            yield encode_event("status", {"status": "generating"})
            while True:
                try:
                    kind, value = await asyncio.to_thread(events.get, True, 0.5)
                except queue.Empty:
                    if cancelled.is_set():
                        return
                    if loop.time() - last_heartbeat >= 15:
                        last_heartbeat = loop.time()
                        yield b": keep-alive\n\n"
                    continue
                if kind == "delta" and value is not None:
                    answer_parts.append(value)
                    yield encode_event("delta", {"delta": value})
                elif kind == "error":
                    await _append_nexus_chat_audit(
                        request, principal, organization_id, project_id,
                        outcome="failure", message_count=len(model_messages),
                        file_count=len(payload.workspace_files), mode=payload.mode,
                    )
                    yield encode_event("error", {"message": value or "NEXUS streaming failed."})
                    return
                elif kind == "complete":
                    break
            await worker
            answer = "".join(answer_parts)
            try:
                saved = await conversation_store.append(
                    organization_id=organization_id, project_id=project_id,
                    owner_issuer=principal.issuer, owner_subject=principal.subject,
                    conversation_id=payload.conversation_id, role="assistant",
                    content=answer, expected_version=persisted_user["version"],
                )
                if saved is None:
                    raise RuntimeError("Conversation version changed during streamed generation")
                await _append_nexus_chat_audit(
                    request, principal, organization_id, project_id,
                    outcome="success", message_count=len(model_messages),
                    file_count=len(payload.workspace_files), mode=payload.mode, model=model,
                )
            except Exception:  # noqa: BLE001 - persist/audit failures must not leak through SSE
                try:
                    await _append_nexus_chat_audit(
                        request, principal, organization_id, project_id,
                        outcome="failure", message_count=len(model_messages),
                        file_count=len(payload.workspace_files), mode=payload.mode,
                    )
                except HTTPException:
                    logger.warning("NEXUS stream completion audit could not be written")
                yield encode_event("error", {"message": "NEXUS could not save the completed response. Reload conversation history."})
                return
            yield encode_event("done", {
                "model": model,
                "conversation_id": payload.conversation_id,
                "conversation_persisted": True,
                "read_only": True,
                "tools_executed": 0,
            })
        except asyncio.CancelledError:
            cancelled.set()
            await _append_nexus_chat_audit(
                request, principal, organization_id, project_id,
                outcome="failure", message_count=len(model_messages),
                file_count=len(payload.workspace_files), mode=payload.mode,
            )
            raise
        finally:
            cancelled.set()
            if not worker.done():
                worker.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/chat",
    tags=["nexus"],
)
async def nexus_project_chat(
    payload: NexusChatRequest,
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    """Authenticated, project-authorized, read-only NEXUS chat.

    When a conversation ID is supplied, the server reloads its owner-scoped
    history and persists the user and assistant turns. The legacy no-ID request
    remains stateless. Selected file excerpts require explicit cloud consent.
    No tools, filesystem writes or command execution are enabled.
    """
    if organization_id != organization_id.strip() or project_id != project_id.strip():
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_RESOURCE_ID", "message": "Resource identifier is invalid."},
        )
    if payload.mode not in {"ask", "debug"}:
        raise HTTPException(status_code=403, detail={"code": "NEXUS_MODE_FORBIDDEN", "message": "This endpoint permits only Ask or Debug mode."})
    if payload.cloud_model_consent is not True:
        raise HTTPException(
            status_code=400,
            detail={"code": "CLOUD_MODEL_CONSENT_REQUIRED", "message": "Explicit consent is required before sending chat or workspace data to the cloud model."},
        )
    try:
        await _authorize_project(request, organization_id, project_id, principal)
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "PROJECT_STORE_UNAVAILABLE", "message": "Project authorization storage is temporarily unavailable."},
        ) from exc

    if not payload.messages or payload.messages[-1].get("role") != "user":
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_CHAT_HISTORY", "message": "The final conversation message must be from the user."},
        )
    await _append_nexus_chat_audit(
        request, principal, organization_id, project_id,
        outcome="started", message_count=len(payload.messages),
        file_count=len(payload.workspace_files), mode=payload.mode,
    )
    model_messages = payload.messages
    persisted_user_message = None
    conversation_store = getattr(request.app.state, "conversation_store", None)
    if payload.conversation_id is not None:
        if conversation_store is None:
            raise HTTPException(status_code=503, detail={"code": "CONVERSATION_STORE_UNAVAILABLE", "message": "NEXUS conversation storage is not configured."})
        try:
            conversation = await conversation_store.get_for_owner(
                organization_id=organization_id, project_id=project_id,
                owner_issuer=principal.issuer, owner_subject=principal.subject,
                conversation_id=payload.conversation_id,
            )
            if conversation is None:
                raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation was not found."})
            persisted_user_message = await conversation_store.append(
                organization_id=organization_id, project_id=project_id,
                owner_issuer=principal.issuer, owner_subject=principal.subject,
                conversation_id=payload.conversation_id, role="user",
                content=payload.messages[-1]["content"],
                expected_version=conversation["version"],
            )
            if persisted_user_message is None:
                raise HTTPException(status_code=409, detail={"code": "CONVERSATION_VERSION_CONFLICT", "message": "Conversation changed. Reload its history before sending another message."})
            model_messages = [
                {"role": item["role"], "content": item["content"]}
                for item in persisted_user_message["messages"][-19:]
            ]
        except PyMongoError as exc:
            raise HTTPException(status_code=503, detail={"code": "CONVERSATION_STORE_UNAVAILABLE", "message": "NEXUS conversation storage is temporarily unavailable."}) from exc
    try:
        client, model = get_openai_client()
        result = await run_in_threadpool(
            run_nexus_chat,
            client,
            model=model,
            messages=model_messages,
            workspace_files=payload.workspace_files,
            mode=payload.mode,
        )
    except ModelConfigurationError as exc:
        await _append_nexus_chat_audit(
            request, principal, organization_id, project_id,
            outcome="failure", message_count=len(payload.messages),
            file_count=len(payload.workspace_files), mode=payload.mode,
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "MODEL_NOT_CONFIGURED", "message": "The NEXUS model provider is not configured."},
        ) from exc
    except NexusChatError as exc:
        await _append_nexus_chat_audit(
            request, principal, organization_id, project_id,
            outcome="failure", message_count=len(payload.messages),
            file_count=len(payload.workspace_files), mode=payload.mode,
        )
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_CHAT_REQUEST", "message": str(exc)},
        ) from exc
    except Exception as exc:
        logger.warning("NEXUS chat provider failed: %s", type(exc).__name__)
        await _append_nexus_chat_audit(
            request, principal, organization_id, project_id,
            outcome="failure", message_count=len(payload.messages),
            file_count=len(payload.workspace_files), mode=payload.mode,
        )
        raise HTTPException(
            status_code=502,
            detail={"code": "NEXUS_CHAT_UNAVAILABLE", "message": "NEXUS chat is temporarily unavailable."},
        ) from exc

    if payload.conversation_id is not None and persisted_user_message is not None:
        try:
            saved = await conversation_store.append(
                organization_id=organization_id, project_id=project_id,
                owner_issuer=principal.issuer, owner_subject=principal.subject,
                conversation_id=payload.conversation_id, role="assistant",
                content=result.answer, expected_version=persisted_user_message["version"],
            )
            if saved is None:
                raise HTTPException(status_code=409, detail={"code": "CONVERSATION_VERSION_CONFLICT", "message": "The conversation changed while NEXUS was responding. Reload history before continuing."})
        except PyMongoError as exc:
            raise HTTPException(status_code=503, detail={"code": "CONVERSATION_STORE_UNAVAILABLE", "message": "NEXUS could not persist its response."}) from exc
    await _append_nexus_chat_audit(
        request, principal, organization_id, project_id,
        outcome="success", message_count=len(model_messages),
        file_count=len(payload.workspace_files), mode=payload.mode, model=result.model,
    )
    return {
        "answer": result.answer,
        "model": result.model,
        "read_only": True,
        "tools_executed": 0,
        "conversation_persisted": payload.conversation_id is not None,
        **({"conversation_id": payload.conversation_id} if payload.conversation_id is not None else {}),
    }
