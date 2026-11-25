"""Fail-closed, scope-bound registry for governed NEXUS tool execution."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from odei_api.services.nexus_capabilities import NexusCapabilityDenied, NexusCapabilityPolicy
from odei_api.services.secret_redaction import redact_secrets

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_ARGUMENT_BYTES = 16_384
_MAX_RESULT_CHARS = 16_000


class GovernedToolError(RuntimeError):
    """A tool is unknown, unauthorized, unapproved, or failed safely."""


class GovernedToolInputError(GovernedToolError):
    """Model-supplied tool arguments do not satisfy the registered schema."""


class GovernedToolAuditError(GovernedToolError):
    """A durable tool audit event could not be written."""


@dataclass(frozen=True)
class ToolApproval:
    """Short-lived approval bound to one actor, resource, tool and argument digest."""

    organization_id: str
    project_id: str
    actor_issuer: str
    actor_subject: str
    tool_name: str
    arguments_sha256: str
    expires_at: float
    approval_id: str


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    capability: str
    schema: Mapping[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    description: str = "Governed ODEI tool."
    approval_required: bool = True


def _validate_schema(schema: Mapping[str, Any]) -> None:
    """Accept only strict object schemas supported by the governed dispatcher."""
    properties = schema.get("properties")
    required = schema.get("required")
    if (
        schema.get("type") != "object"
        or not isinstance(properties, Mapping)
        or not isinstance(required, list)
        or set(required) != set(properties)
        or schema.get("additionalProperties") is not False
    ):
        raise ValueError("tool schema must be a strict object schema")
    allowed_types = {"string", "integer", "number", "boolean", "object", "array", "null"}
    for specification in properties.values():
        if not isinstance(specification, Mapping) or specification.get("type") not in allowed_types:
            raise ValueError("tool property schema is unsupported")


def _validate_arguments(schema: Mapping[str, Any], arguments: dict[str, Any]) -> None:
    """Validate the strict JSON-schema subset used by Responses function tools."""
    _validate_schema(schema)
    properties = schema.get("properties")
    required = schema.get("required")
    if set(arguments) - set(properties):
        raise GovernedToolInputError("tool arguments contain unsupported fields")
    if set(required) - set(arguments):
        raise GovernedToolInputError("tool arguments are missing required fields")

    for key, value in arguments.items():
        specification = properties.get(key)
        if not isinstance(specification, Mapping):
            raise GovernedToolError("tool argument schema is invalid")
        expected = specification.get("type")
        valid = (
            (expected == "string" and isinstance(value, str))
            or (expected == "integer" and isinstance(value, int) and not isinstance(value, bool))
            or (expected == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
            or (expected == "boolean" and isinstance(value, bool))
            or (expected == "object" and isinstance(value, dict))
            or (expected == "array" and isinstance(value, list))
            or (expected == "null" and value is None)
        )
        if not valid:
            raise GovernedToolInputError("tool argument has an invalid type")
        if expected == "string":
            if len(value) < specification.get("minLength", 0):
                raise GovernedToolInputError("tool argument is shorter than allowed")
            if len(value) > specification.get("maxLength", _MAX_ARGUMENT_BYTES):
                raise GovernedToolInputError("tool argument is longer than allowed")
        if "enum" in specification and value not in specification["enum"]:
            raise GovernedToolInputError("tool argument is not an allowed value")
        if expected in {"integer", "number"}:
            if "minimum" in specification and value < specification["minimum"]:
                raise GovernedToolInputError("tool argument is below the allowed minimum")
            if "maximum" in specification and value > specification["maximum"]:
                raise GovernedToolInputError("tool argument exceeds the allowed maximum")
        if expected == "array":
            if len(value) < specification.get("minItems", 0):
                raise GovernedToolInputError("tool argument contains too few items")
            if len(value) > specification.get("maxItems", _MAX_ARGUMENT_BYTES):
                raise GovernedToolInputError("tool argument contains too many items")


class GovernedToolRegistry:
    """Allow-listed tool dispatcher; model arguments never select scope or authority.

    Approval issuance is owned by the trusted API/UI. This registry only consumes
    opaque approval records supplied by that trusted layer and makes each one-use.
    Audit delivery is fail-closed before and after every side-effecting handler.
    """

    def __init__(
        self,
        *,
        mode: str,
        organization_id: str,
        project_id: str,
        actor_issuer: str,
        actor_subject: str,
        approval_consumer: Callable[[ToolApproval], bool] | None = None,
        audit_sink: Callable[[dict[str, Any]], None],
    ) -> None:
        if mode not in {"ask", "plan", "agent", "debug"}:
            raise ValueError("mode is invalid")
        for value in (organization_id, project_id, actor_subject):
            if not isinstance(value, str) or not value.strip() or len(value) > 512:
                raise ValueError("tool execution scope is invalid")
        if not isinstance(actor_issuer, str) or not actor_issuer.startswith("https://"):
            raise ValueError("actor issuer must be HTTPS")
        if not callable(audit_sink):
            raise TypeError("a durable audit sink is required")
        self._mode = mode
        self._organization_id = organization_id
        self._project_id = project_id
        self._actor_issuer = actor_issuer
        self._actor_subject = actor_subject
        self._approval_consumer = approval_consumer
        self._audit = audit_sink
        self._tools: dict[str, ToolDefinition] = {}
        self._consumed: set[str] = set()
        self._lock = threading.Lock()

    def register(self, definition: ToolDefinition) -> None:
        if not isinstance(definition, ToolDefinition) or not _NAME.fullmatch(definition.name):
            raise ValueError("tool definition is invalid")
        if definition.name in self._tools or not callable(definition.handler):
            raise ValueError("tool name is duplicated or handler is invalid")
        if not isinstance(definition.schema, Mapping):
            raise TypeError("tool schema must be an object")
        _validate_schema(definition.schema)
        if not isinstance(definition.description, str) or not definition.description.strip() or len(definition.description) > 1_000:
            raise ValueError("tool description is invalid")
        try:
            NexusCapabilityPolicy.require(self._mode, definition.capability)
        except NexusCapabilityDenied as exc:
            raise GovernedToolError("tool capability is not granted in this mode") from exc
        self._tools[definition.name] = definition

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": item.name,
                "description": item.description,
                "strict": True,
                "parameters": dict(item.schema),
            }
            for item in self._tools.values()
        ]

    @staticmethod
    def _digest(arguments: dict[str, Any]) -> str:
        try:
            encoded = json.dumps(
                arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise GovernedToolError("tool arguments are not canonical JSON") from exc
        if len(encoded) > _MAX_ARGUMENT_BYTES:
            raise GovernedToolError("tool arguments exceed the size limit")
        return hashlib.sha256(encoded).hexdigest()

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        approval: ToolApproval | None = None,
    ) -> str:
        definition = self._tools.get(name)
        if definition is None:
            raise GovernedToolError("tool is not registered")
        if not isinstance(arguments, dict):
            raise GovernedToolError("tool arguments must be an object")
        _validate_arguments(definition.schema, arguments)
        digest = self._digest(arguments)
        if definition.approval_required:
            if approval is None or self._approval_consumer is None:
                raise GovernedToolError("explicit user approval is required")
            expected = (
                self._organization_id, self._project_id, self._actor_issuer,
                self._actor_subject, name, digest,
            )
            actual = (
                approval.organization_id, approval.project_id, approval.actor_issuer,
                approval.actor_subject, approval.tool_name, approval.arguments_sha256,
            )
            if actual != expected or approval.expires_at <= time.time() or not approval.approval_id:
                raise GovernedToolError("approval does not match this action or has expired")
            with self._lock:
                if approval.approval_id in self._consumed:
                    raise GovernedToolError("approval has already been consumed")
                self._consumed.add(approval.approval_id)
            if not self._approval_consumer(approval):
                raise GovernedToolError("approval could not be verified or consumed")

        event = {
            "organization_id": self._organization_id,
            "project_id": self._project_id,
            "actor_issuer": self._actor_issuer,
            "actor_subject": self._actor_subject,
            "tool_name": name,
            "arguments_sha256": digest,
            "approval_id": approval.approval_id if approval else None,
        }
        try:
            self._audit({"event": "nexus.tool.started", **event})
        except Exception as exc:
            raise GovernedToolAuditError("audit unavailable; tool execution stopped") from exc
        try:
            result = definition.handler(dict(arguments))
            rendered = result if isinstance(result, str) else json.dumps(
                result, ensure_ascii=False, default=str
            )
            rendered = redact_secrets(rendered[:_MAX_RESULT_CHARS])
        except (ValueError, OSError) as exc:
            # Preserve bounded argument/workspace validation errors for the agent loop.
            try:
                self._audit({"event": "nexus.tool.failed", **event, "error_type": type(exc).__name__})
            except Exception as audit_exc:
                raise GovernedToolAuditError("audit unavailable; tool failure could not be recorded") from audit_exc
            raise
        except Exception as exc:
            try:
                self._audit({"event": "nexus.tool.failed", **event, "error_type": type(exc).__name__})
            except Exception as audit_exc:
                raise GovernedToolAuditError("audit unavailable; tool failure could not be recorded") from audit_exc
            raise GovernedToolError("tool execution failed") from exc
        try:
            self._audit({"event": "nexus.tool.completed", **event})
        except Exception as exc:
            raise GovernedToolError(
                "tool result is uncertain because audit delivery failed"
            ) from exc
        return rendered
