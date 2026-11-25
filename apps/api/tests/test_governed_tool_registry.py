import hashlib
import json
import time

import pytest

from odei_api.services.governed_tool_registry import (
    GovernedToolError,
    GovernedToolRegistry,
    ToolApproval,
    ToolDefinition,
)


def _registry(handler, *, audit=None, consume=None):
    events = []
    registry = GovernedToolRegistry(
        mode="agent", organization_id="org-1", project_id="project-1",
        actor_issuer="https://identity.example", actor_subject="user-1",
        approval_consumer=consume or (lambda _: True),
        audit_sink=audit or events.append,
    )
    registry.register(ToolDefinition(
        name="run_diagnostics", capability="execution.run",
        schema={"type": "object", "properties": {"profile": {"type": "string"}},
                "required": ["profile"], "additionalProperties": False},
        handler=handler,
    ))
    return registry, events


def _approval(arguments, **overrides):
    values = {
        "organization_id": "org-1",
        "project_id": "project-1",
        "actor_issuer": "https://identity.example",
        "actor_subject": "user-1",
        "tool_name": "run_diagnostics",
        "arguments_sha256": hashlib.sha256(
            json.dumps(arguments, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "expires_at": time.time() + 30,
        "approval_id": "approval-1",
    }
    values.update(overrides)
    return ToolApproval(**values)


def test_side_effecting_tool_requires_scope_bound_one_use_approval():
    calls = []
    registry, events = _registry(lambda args: calls.append(args) or {"ok": True})
    args = {"profile": "python"}
    with pytest.raises(GovernedToolError, match="approval"):
        registry.execute("run_diagnostics", args)
    approval = _approval(args)
    assert registry.execute("run_diagnostics", args, approval=approval) == '{"ok": true}'
    with pytest.raises(GovernedToolError, match="consumed"):
        registry.execute("run_diagnostics", args, approval=approval)
    assert calls == [args]
    assert [event["event"] for event in events] == [
        "nexus.tool.started", "nexus.tool.completed"
    ]


@pytest.mark.parametrize("changes", [
    {"project_id": "other"}, {"actor_subject": "other"},
    {"tool_name": "delete_workspace"}, {"arguments_sha256": "0" * 64},
    {"expires_at": 0},
])
def test_approval_is_bound_to_identity_scope_tool_and_exact_arguments(changes):
    calls = []
    registry, _ = _registry(lambda args: calls.append(args))
    with pytest.raises(GovernedToolError, match="approval"):
        registry.execute(
            "run_diagnostics", {"profile": "python"},
            approval=_approval({"profile": "python"}, **changes),
        )
    assert calls == []


def test_unknown_and_mode_unauthorized_tools_fail_closed():
    registry, _ = _registry(lambda _: "ok")
    with pytest.raises(GovernedToolError, match="not registered"):
        registry.execute("run_shell", {})
    ask = GovernedToolRegistry(
        mode="ask", organization_id="org", project_id="project",
        actor_issuer="https://identity.example", actor_subject="user",
        audit_sink=lambda _: None,
    )
    with pytest.raises(GovernedToolError, match="not granted"):
        ask.register(ToolDefinition(
            name="run_diagnostics", capability="execution.run",
            schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            handler=lambda _: None,
        ))


def test_audit_failure_prevents_handler_execution_and_secrets_are_redacted():
    calls = []

    def fail(_):
        raise RuntimeError("offline")

    registry, _ = _registry(lambda args: calls.append(args), audit=fail)
    args = {"profile": "python"}
    with pytest.raises(GovernedToolError, match="audit unavailable"):
        registry.execute("run_diagnostics", args, approval=_approval(args))
    assert calls == []

    safe, _ = _registry(lambda _: {"token": "ghp_" + "A" * 32})
    args = {"profile": "python"}
    result = safe.execute("run_diagnostics", args, approval=_approval(args))
    assert "ghp_" not in result and "[REDACTED]" in result



def test_tool_schema_is_enforced_before_audit_or_handler():
    calls = []
    registry, events = _registry(lambda args: calls.append(args) or "ok")
    with pytest.raises(GovernedToolError, match="unsupported fields"):
        registry.execute("run_diagnostics", {"profile": "python", "admin": True},
                         approval=_approval({"profile": "python", "admin": True}))
    with pytest.raises(GovernedToolError, match="invalid type"):
        registry.execute("run_diagnostics", {"profile": 42},
                         approval=_approval({"profile": 42}))
    with pytest.raises(GovernedToolError, match="missing required"):
        registry.execute("run_diagnostics", {},
                         approval=_approval({}))
    assert calls == []
    assert events == []


def test_tool_schema_description_is_exposed_to_model():
    registry = GovernedToolRegistry(
        mode="agent", organization_id="org", project_id="project",
        actor_issuer="https://identity.example", actor_subject="user",
        audit_sink=lambda _: None,
    )
    registry.register(ToolDefinition(
        name="read_project", capability="workspace.read",
        schema={"type": "object", "properties": {"path": {"type": "string"}},
                "required": ["path"], "additionalProperties": False},
        handler=lambda _: "ok", description="Read a bounded project file.",
        approval_required=False,
    ))
    assert registry.schemas()[0]["description"] == "Read a bounded project file."
