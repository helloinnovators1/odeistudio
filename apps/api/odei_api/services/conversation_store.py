"""Tenant- and owner-scoped durable NEXUS conversation storage."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pymongo import ReturnDocument

from odei_api.services.secret_redaction import redact_secrets

MAX_CONVERSATIONS_PAGE = 50
MAX_CONVERSATION_MESSAGES = 200
MAX_CONVERSATION_MESSAGE_CHARS = 16_000
MAX_CONVERSATION_TOTAL_BYTES = 1_000_000


class ConversationStoreError(ValueError):
    """Conversation data or optimistic concurrency constraint is invalid."""


class MongoConversationStore:
    """Persist conversation records with tenant, project and identity ownership filters."""

    def __init__(self, collection: Any):
        self._collection = collection

    async def initialize(self) -> None:
        await self._collection.create_index(
            [("conversation_id", 1)], unique=True
        )
        await self._collection.create_index(
            [("organization_id", 1), ("project_id", 1), ("owner_issuer", 1),
             ("owner_subject", 1), ("updated_at", -1)]
        )

    async def create(
        self, *, organization_id: str, project_id: str,
        owner_issuer: str, owner_subject: str, title: str,
    ) -> dict:
        title = redact_secrets(title.strip())
        if not title or len(title) > 120:
            raise ConversationStoreError("Conversation title must contain 1 to 120 characters")
        now = datetime.now(timezone.utc)
        document = {
            "conversation_id": uuid4().hex,
            "organization_id": organization_id,
            "project_id": project_id,
            "owner_issuer": owner_issuer,
            "owner_subject": owner_subject,
            "title": title,
            "messages": [],
            "version": 0,
            "created_at": now,
            "updated_at": now,
        }
        await self._collection.insert_one(document)
        return document

    async def list_for_owner(
        self, *, organization_id: str, project_id: str,
        owner_issuer: str, owner_subject: str, limit: int = 30,
    ) -> list[dict]:
        if not 1 <= limit <= MAX_CONVERSATIONS_PAGE:
            raise ConversationStoreError("Conversation page limit is invalid")
        cursor = self._collection.find({
            "organization_id": organization_id,
            "project_id": project_id,
            "owner_issuer": owner_issuer,
            "owner_subject": owner_subject,
        }, {"_id": 0}).sort("updated_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_for_owner(
        self, *, organization_id: str, project_id: str,
        owner_issuer: str, owner_subject: str, conversation_id: str,
    ) -> dict | None:
        return await self._collection.find_one({
            "conversation_id": conversation_id,
            "organization_id": organization_id,
            "project_id": project_id,
            "owner_issuer": owner_issuer,
            "owner_subject": owner_subject,
        }, {"_id": 0})

    async def delete_for_owner(
        self, *, organization_id: str, project_id: str,
        owner_issuer: str, owner_subject: str, conversation_id: str,
    ) -> bool:
        result = await self._collection.delete_one({
            "conversation_id": conversation_id,
            "organization_id": organization_id,
            "project_id": project_id,
            "owner_issuer": owner_issuer,
            "owner_subject": owner_subject,
        })
        return result.deleted_count == 1

    async def append(
        self, *, organization_id: str, project_id: str,
        owner_issuer: str, owner_subject: str, conversation_id: str,
        role: str, content: str, expected_version: int | None = None,
        mode: str | None = None,
    ) -> dict | None:
        if role not in {"user", "assistant"}:
            raise ConversationStoreError("Conversation message role is invalid")
        if mode is not None and mode not in {"ask", "plan", "agent", "debug"}:
            raise ConversationStoreError("Conversation message mode is invalid")
        if not isinstance(content, str) or not content.strip() or len(content) > MAX_CONVERSATION_MESSAGE_CHARS:
            raise ConversationStoreError("Conversation message must contain 1 to 16,000 characters")
        content = redact_secrets(content.strip())
        if not content:
            raise ConversationStoreError("Conversation message is empty after secret redaction")
        if expected_version is not None and expected_version < 0:
            raise ConversationStoreError("Conversation version is invalid")
        query: dict[str, Any] = {
            "conversation_id": conversation_id,
            "organization_id": organization_id,
            "project_id": project_id,
            "owner_issuer": owner_issuer,
            "owner_subject": owner_subject,
            "$expr": {"$and": [
                {"$lt": [{"$size": {"$ifNull": ["$messages", []]}}, MAX_CONVERSATION_MESSAGES]},
                {"$lte": [
                    {"$add": [
                        {"$sum": {"$map": {
                            "input": {"$ifNull": ["$messages", []]},
                            "as": "message",
                            "in": {"$strLenBytes": "$$message.content"},
                        }}},
                        len(content.encode("utf-8")),
                    ]},
                    MAX_CONVERSATION_TOTAL_BYTES,
                ]},
            ]},
        }
        if expected_version is not None:
            query["version"] = expected_version
        now = datetime.now(timezone.utc)
        message = {
            "message_id": uuid4().hex,
            "role": role,
            "content": content,
            **({"mode": mode} if mode is not None else {}),
            "created_at": now,
        }
        updated = await self._collection.find_one_and_update(
            query,
            {"$push": {"messages": message}, "$inc": {"version": 1}, "$set": {"updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return updated
