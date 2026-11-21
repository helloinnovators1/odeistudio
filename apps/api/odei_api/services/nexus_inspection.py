"""Authenticated NEXUS read-only inspection over user-attached excerpts."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from odei_api.config import get_settings
from odei_api.model_client import ModelConfigurationError, get_openai_client
from odei_api.security.auth import Principal, get_current_principal
from odei_api.services.agent_runtime import AgentRuntimeError, run_nexus_agent
from odei_api.services.nexus_tasks import (
    NexusChatRequest,
    _append_nexus_chat_audit,
    _authorize_project,
)
from odei_api.services.selected_excerpt_tools import (
    SelectedExcerptToolError,
    SelectedExcerptTools,
)

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()
principal_dependency = Depends(get_current_principal)


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/chat/inspect",
    tags=["nexus"],
)
async def inspect_attached_project_excerpts(
    payload: NexusChatRequest,
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    """Run bounded read-only tools against only the excerpts the user attached."""
    if organization_id != organization_id.strip() or project_id != project_id.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_RESOURCE_ID", "message": "Resource identifier is invalid."})
    if payload.cloud_model_consent is not True:
        raise HTTPException(status_code=400, detail={"code": "CLOUD_MODEL_CONSENT_REQUIRED", "message": "Explicit consent is required before sending chat or workspace data to the cloud model."})
    if payload.conversation_id is None:
        raise HTTPException(status_code=400, detail={"code": "CONVERSATION_REQUIRED", "message": "Read-only inspection requires a saved conversation."})
    if not payload.workspace_files:
        raise HTTPException(status_code=400, detail={"code": "ATTACHED_EXCERPT_REQUIRED", "message": "Attach at least one file excerpt before enabling repository inspection."})
    if not payload.messages or payload.messages[-1].get("role") != "user":
        raise HTTPException(status_code=422, detail={"code": "INVALID_CHAT_HISTORY", "message": "The final conversation message must be from the user."})
    try:
        tools = SelectedExcerptTools(payload.workspace_files)
    except SelectedExcerptToolError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_ATTACHED_EXCERPT", "message": str(exc)}) from exc

    try:
        await _authorize_project(request, organization_id, project_id, principal)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "PROJECT_STORE_UNAVAILABLE", "message": "Project authorization storage is temporarily unavailable."}) from exc

    store = getattr(request.app.state, "conversation_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "CONVERSATION_STORE_UNAVAILABLE", "message": "NEXUS conversation storage is not configured."})
    conversation_id = payload.conversation_id
    try:
        conversation = await store.get_for_owner(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=principal.issuer, owner_subject=principal.subject,
            conversation_id=conversation_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation was not found."})
        prior_messages = [
            {"role": item["role"], "content": item["content"]}
            for item in conversation["messages"][-19:]
        ]
        user_turn = await store.append(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=principal.issuer, owner_subject=principal.subject,
            conversation_id=conversation_id, role="user",
            content=payload.messages[-1]["content"],
            expected_version=conversation["version"],
        )
        if user_turn is None:
            raise HTTPException(status_code=409, detail={"code": "CONVERSATION_VERSION_CONFLICT", "message": "Conversation changed. Reload its history before inspecting attached files."})
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "CONVERSATION_STORE_UNAVAILABLE", "message": "NEXUS conversation storage is temporarily unavailable."}) from exc

    message_count = len(prior_messages) + 1
    await _append_nexus_chat_audit(
        request, principal, organization_id, project_id,
        outcome="started", message_count=message_count,
        file_count=len(payload.workspace_files),
    )
    try:
        client, model = get_openai_client()
        result = await run_in_threadpool(
            run_nexus_agent,
            client,
            model=model,
            task=payload.messages[-1]["content"],
            workspace_tools=tools,
            cloud_model_consent=True,
            prior_messages=prior_messages,
        )
    except ModelConfigurationError as exc:
        await _append_nexus_chat_audit(
            request, principal, organization_id, project_id,
            outcome="failure", message_count=message_count,
            file_count=len(payload.workspace_files),
        )
        raise HTTPException(status_code=503, detail={"code": "MODEL_NOT_CONFIGURED", "message": "The NEXUS model provider is not configured."}) from exc
    except (AgentRuntimeError, SelectedExcerptToolError, ValueError) as exc:
        await _append_nexus_chat_audit(
            request, principal, organization_id, project_id,
            outcome="failure", message_count=message_count,
            file_count=len(payload.workspace_files),
        )
        raise HTTPException(status_code=422, detail={"code": "NEXUS_INSPECTION_FAILED", "message": "NEXUS could not safely inspect the attached excerpts."}) from exc
    except Exception as exc:
        logger.warning("NEXUS read-only inspection failed: %s", type(exc).__name__)
        await _append_nexus_chat_audit(
            request, principal, organization_id, project_id,
            outcome="failure", message_count=message_count,
            file_count=len(payload.workspace_files),
        )
        raise HTTPException(status_code=502, detail={"code": "NEXUS_INSPECTION_UNAVAILABLE", "message": "NEXUS inspection is temporarily unavailable."}) from exc

    try:
        saved = await store.append(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=principal.issuer, owner_subject=principal.subject,
            conversation_id=conversation_id, role="assistant",
            content=result.answer, expected_version=user_turn["version"],
        )
        if saved is None:
            raise HTTPException(status_code=409, detail={"code": "CONVERSATION_VERSION_CONFLICT", "message": "The conversation changed while NEXUS was inspecting files. Reload history before continuing."})
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "CONVERSATION_STORE_UNAVAILABLE", "message": "NEXUS could not persist its inspection response."}) from exc

    await _append_nexus_chat_audit(
        request, principal, organization_id, project_id,
        outcome="success", message_count=message_count,
        file_count=len(payload.workspace_files), model=result.model,
        tool_calls=result.tool_calls,
    )
    return {
        "answer": result.answer,
        "model": result.model,
        "read_only": True,
        "tools_executed": result.tool_calls,
        "tool_names": list(result.tool_names),
        "conversation_persisted": True,
        "conversation_id": conversation_id,
    }
