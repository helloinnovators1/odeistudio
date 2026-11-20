"""Append-only, tenant-scoped audit event writer.

This service intentionally exposes insert-only behavior. Database credentials must
also deny update/delete on the audit collection for tamper resistance.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from odei_api.services.secret_redaction import redact_secrets

_ACTION = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_SENSITIVE_KEY = re.compile(
    r"(?:secret|password|passwd|token|api[_-]?key|authorization|cookie|credential)",
    re.IGNORECASE,
)
_ALLOWED_OUTCOMES = frozenset({"success", "denied", "failure"})
_MAX_METADATA_KEYS = 32
_MAX_METADATA_DEPTH = 4
_MAX_STRING_LENGTH = 2048


class AuditEventValidationError(ValueError):
    """Raised when an audit event cannot be safely and consistently recorded."""


def _required_identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise AuditEventValidationError(f"{field} is invalid")
    return value


def _safe_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_METADATA_DEPTH:
        raise AuditEventValidationError("metadata nesting is too deep")
    if isinstance(value, Mapping):
        if len(value) > _MAX_METADATA_KEYS:
            raise AuditEventValidationError("metadata contains too many fields")
        safe: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 80:
                raise AuditEventValidationError("metadata keys must be short strings")
            safe[key] = "[REDACTED]" if _SENSITIVE_KEY.search(key) else _safe_metadata(
                item, depth=depth + 1
            )
        return safe
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_METADATA_KEYS:
            raise AuditEventValidationError("metadata list is too large")
        return [_safe_metadata(item, depth=depth + 1) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            raise AuditEventValidationError("metadata string is too long")
        return redact_secrets(value)
    raise AuditEventValidationError("metadata must contain JSON-compatible values")


class MongoAuditEventStore:
    """Write tenant-scoped audit events; intentionally has no update/delete API."""

    def __init__(self, collection: Any):
        self._collection = collection

    async def initialize(self) -> None:
        await self._collection.create_index(
            [("organization_id", 1), ("occurred_at", -1)]
        )
        await self._collection.create_index(
            [("event_id", 1)], unique=True
        )
        await self._collection.create_index(
            [("organization_id", 1), ("actor_issuer", 1), ("actor_subject", 1),
             ("occurred_at", -1)]
        )

    async def append(
        self,
        *,
        organization_id: str,
        actor_issuer: str,
        actor_subject: str,
        action: str,
        target_type: str,
        target_id: str,
        outcome: str,
        request_id: str,
        trace_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        organization_id = _required_identifier(organization_id, "organization_id")
        actor_subject = _required_identifier(actor_subject, "actor_subject")
        target_type = _required_identifier(target_type, "target_type")
        target_id = _required_identifier(target_id, "target_id")
        request_id = _required_identifier(request_id, "request_id")
        if not isinstance(actor_issuer, str) or not actor_issuer.startswith("https://"):
            raise AuditEventValidationError("actor_issuer must be an HTTPS issuer")
        if len(actor_issuer) > 512:
            raise AuditEventValidationError("actor_issuer is too long")
        if not isinstance(action, str) or not _ACTION.fullmatch(action):
            raise AuditEventValidationError("action is invalid")
        if outcome not in _ALLOWED_OUTCOMES:
            raise AuditEventValidationError("outcome is invalid")
        if trace_id is not None:
            trace_id = _required_identifier(trace_id, "trace_id")
        if metadata is not None and not isinstance(metadata, Mapping):
            raise AuditEventValidationError("metadata must be an object")
        timestamp = occurred_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise AuditEventValidationError("occurred_at must be timezone-aware")
        document = {
            "event_id": str(uuid4()),
            "schema_version": 1,
            "organization_id": organization_id,
            "actor_issuer": actor_issuer,
            "actor_subject": actor_subject,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "outcome": outcome,
            "request_id": request_id,
            "trace_id": trace_id,
            "occurred_at": timestamp.astimezone(timezone.utc),
            "metadata": _safe_metadata(metadata or {}),
        }
        await self._collection.insert_one(document)
        return document
