"""Authenticated, project-scoped NEXUS conversation endpoints."""
from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from pymongo.errors import PyMongoError

from odei_api.config import get_settings
from odei_api.security.auth import Principal, get_current_principal
from odei_api.services.conversation_store import ConversationStoreError
from odei_api.services.nexus_tasks import _authorize_project

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()
principal_dependency = Depends(get_current_principal)


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)


class AppendConversationMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: StrictStr
    content: StrictStr = Field(min_length=1, max_length=8_000)
    expected_version: int | None = Field(default=None, ge=0)


async def _context(request: Request, organization_id: str, project_id: str, principal: Principal):
    if organization_id != organization_id.strip() or project_id != project_id.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_RESOURCE_ID", "message": "Resource identifier is invalid."})
    try:
        await _authorize_project(request, organization_id, project_id, principal)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "PROJECT_STORE_UNAVAILABLE", "message": "Project authorization storage is temporarily unavailable."}) from exc
    store = getattr(request.app.state, "conversation_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "CONVERSATION_STORE_UNAVAILABLE", "message": "Conversation storage is not configured."})
    return store


async def _audit(request: Request, principal: Principal, organization_id: str, project_id: str, action: str, outcome: str, conversation_id: str | None = None, metadata: dict | None = None) -> None:
    store = getattr(request.app.state, "audit_event_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Audit storage is not available."})
    try:
        await store.append(
            organization_id=organization_id,
            actor_issuer=principal.issuer,
            actor_subject=principal.subject,
            action=action,
            target_type="nexus_conversation",
            target_id=conversation_id or project_id,
            outcome=outcome,
            request_id=uuid4().hex,
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.error("NEXUS conversation audit failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail={"code": "AUDIT_STORE_UNAVAILABLE", "message": "Conversation audit storage is temporarily unavailable."}) from exc


def _owner(principal: Principal) -> dict:
    return {"owner_issuer": principal.issuer, "owner_subject": principal.subject}


def _response(document: dict) -> dict:
    return {
        "conversation_id": document["conversation_id"],
        "organization_id": document["organization_id"],
        "project_id": document["project_id"],
        "title": document["title"],
        "messages": document["messages"],
        "version": document["version"],
        "created_at": document["created_at"].isoformat(),
        "updated_at": document["updated_at"].isoformat(),
    }


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/conversations",
    tags=["nexus"],
)
async def create_conversation(
    payload: CreateConversationRequest, request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    store = await _context(request, organization_id, project_id, principal)
    try:
        document = await store.create(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=principal.issuer, owner_subject=principal.subject,
            title=payload.title,
        )
    except (ConversationStoreError, PyMongoError) as exc:
        raise HTTPException(status_code=503, detail={"code": "CONVERSATION_CREATE_FAILED", "message": "NEXUS could not create the conversation."}) from exc
    await _audit(request, principal, organization_id, project_id, "nexus.conversation.create", "success", document["conversation_id"])
    return _response(document)


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/conversations",
    tags=["nexus"],
)
async def list_conversations(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    limit: int = Query(default=30, ge=1, le=50),
    principal: Principal = principal_dependency,
) -> dict:
    store = await _context(request, organization_id, project_id, principal)
    try:
        documents = await store.list_for_owner(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=principal.issuer, owner_subject=principal.subject,
            limit=limit,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "CONVERSATION_READ_FAILED", "message": "NEXUS conversation history is temporarily unavailable."}) from exc
    await _audit(request, principal, organization_id, project_id, "nexus.conversation.list", "success", metadata={"count": len(documents)})
    return {"conversations": [_response(item) for item in documents], "limit": limit}


@router.get(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/conversations/{{conversation_id}}",
    tags=["nexus"],
)
async def get_conversation(
    request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    conversation_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    store = await _context(request, organization_id, project_id, principal)
    try:
        document = await store.get_for_owner(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=principal.issuer, owner_subject=principal.subject,
            conversation_id=conversation_id,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "CONVERSATION_READ_FAILED", "message": "NEXUS conversation history is temporarily unavailable."}) from exc
    if document is None:
        await _audit(request, principal, organization_id, project_id, "nexus.conversation.read", "denied", conversation_id, {"reason": "not_found_or_not_owner"})
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation was not found."})
    await _audit(request, principal, organization_id, project_id, "nexus.conversation.read", "success", conversation_id)
    return _response(document)


@router.post(
    f"{settings.api_prefix}/organizations/{{organization_id}}/projects/{{project_id}}/nexus/conversations/{{conversation_id}}/messages",
    tags=["nexus"],
)
async def append_conversation_message(
    payload: AppendConversationMessageRequest, request: Request,
    organization_id: str = Path(min_length=1, max_length=128),
    project_id: str = Path(min_length=1, max_length=128),
    conversation_id: str = Path(min_length=1, max_length=128),
    principal: Principal = principal_dependency,
) -> dict:
    store = await _context(request, organization_id, project_id, principal)
    if payload.role != "user":
        raise HTTPException(status_code=400, detail={"code": "INVALID_MESSAGE_ROLE", "message": "Only user messages may be submitted through this endpoint."})
    try:
        document = await store.append(
            organization_id=organization_id, project_id=project_id,
            owner_issuer=principal.issuer, owner_subject=principal.subject,
            conversation_id=conversation_id, role="user", content=payload.content,
            expected_version=payload.expected_version,
        )
    except ConversationStoreError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_CONVERSATION_MESSAGE", "message": str(exc)}) from exc
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail={"code": "CONVERSATION_WRITE_FAILED", "message": "NEXUS could not save the message."}) from exc
    if document is None:
        await _audit(request, principal, organization_id, project_id, "nexus.conversation.message.append", "denied", conversation_id, {"reason": "not_found_not_owner_or_version_limit"})
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation was not found or has changed. Reload before retrying."})
    await _audit(request, principal, organization_id, project_id, "nexus.conversation.message.append", "success", conversation_id, {"role": "user", "version": document["version"]})
    return _response(document)
