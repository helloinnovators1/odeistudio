"""Deployment-allowlisted MCP Streamable HTTP client for read-only NEXUS tools.

Only server-owned HTTPS endpoints and tool names are exposed to the model. MCP
servers are treated as untrusted: schemas are narrowed to a strict primitive
subset, redirects are disabled, responses are bounded, and tool output is
redacted before it enters the agent context. Network egress must additionally
be restricted by the deployment firewall/proxy.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from odei_api.services.secret_redaction import redact_secrets

_MAX_SERVERS = 20
_MAX_TOOLS_PER_SERVER = 64
_MAX_RESPONSE_BYTES = 1_048_576
_MAX_TOOL_OUTPUT_CHARS = 16_000
_SERVER_ID = re.compile(r"^[a-z][a-z0-9_]{0,15}$")
_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_ALLOWED_PROPERTY_TYPES = {"string", "integer", "number", "boolean"}


class McpGatewayError(RuntimeError):
    """An MCP server, tool schema, or response failed closed validation."""


@dataclass(frozen=True)
class McpServerConfig:
    server_id: str
    endpoint: str
    allowed_tools: tuple[str, ...]
    bearer_token_env: str | None = None

    @classmethod
    def parse(cls, value: Any) -> "McpServerConfig":
        if not isinstance(value, dict) or set(value) - {
            "id", "endpoint", "allowed_tools", "bearer_token_env"
        }:
            raise ValueError("MCP server configuration contains unsupported fields")
        server_id = value.get("id")
        endpoint = value.get("endpoint")
        allowed = value.get("allowed_tools")
        token_env = value.get("bearer_token_env")
        if not isinstance(server_id, str) or not _SERVER_ID.fullmatch(server_id):
            raise ValueError("MCP server id is invalid")
        if not isinstance(endpoint, str) or len(endpoint) > 2048:
            raise ValueError("MCP endpoint is invalid")
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.port not in {None, 443}
            or parsed.hostname.lower() in {"localhost", "localhost.localdomain"}
            or parsed.hostname.lower().endswith((".localhost", ".local", ".internal"))
        ):
            raise ValueError("MCP endpoint must be a public HTTPS URL without credentials, query or fragment")
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and (
            address.is_private or address.is_loopback or address.is_link_local
            or address.is_multicast or address.is_reserved or address.is_unspecified
        ):
            raise ValueError("MCP endpoint cannot target a non-public IP address")
        if not isinstance(allowed, list) or not 1 <= len(allowed) <= _MAX_TOOLS_PER_SERVER:
            raise ValueError("MCP allowed_tools must contain 1 to 64 tool names")
        if (
            any(not isinstance(name, str) or not _TOOL_NAME.fullmatch(name) for name in allowed)
            or len(set(allowed)) != len(allowed)
        ):
            raise ValueError("MCP allowed tool names are invalid or duplicated")
        if token_env is not None and (
            not isinstance(token_env, str) or not _ENV_NAME.fullmatch(token_env)
        ):
            raise ValueError("MCP bearer token environment variable name is invalid")
        return cls(server_id, endpoint, tuple(allowed), token_env)


def load_mcp_servers(raw: str) -> tuple[McpServerConfig, ...]:
    """Parse a bounded deployment-owned MCP allowlist; never accept client URLs."""
    if not isinstance(raw, str) or not raw.strip():
        return ()
    if len(raw) > 65_536:
        raise ValueError("NEXUS_MCP_SERVERS_JSON exceeds the configuration limit")
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("NEXUS_MCP_SERVERS_JSON must be valid JSON") from exc
    if not isinstance(values, list) or not 1 <= len(values) <= _MAX_SERVERS:
        raise ValueError("NEXUS_MCP_SERVERS_JSON must contain 1 to 20 servers")
    servers = tuple(McpServerConfig.parse(item) for item in values)
    if len({item.server_id for item in servers}) != len(servers):
        raise ValueError("MCP server ids must be unique")
    return servers


def _strict_tool_schema(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("type") != "object":
        raise McpGatewayError("MCP tool input schema must be an object")
    properties = value.get("properties", {})
    required = value.get("required", [])
    if (
        not isinstance(properties, dict) or not isinstance(required, list)
        or any(not isinstance(name, str) for name in required)
        or len(set(required)) != len(required) or set(required) - set(properties)
        or len(properties) > 32
    ):
        raise McpGatewayError("MCP tool input schema is invalid")
    narrowed: dict[str, Any] = {}
    for name in required:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name):
            raise McpGatewayError("MCP tool argument name is invalid")
        spec = properties[name]
        if not isinstance(spec, dict) or spec.get("type") not in _ALLOWED_PROPERTY_TYPES:
            raise McpGatewayError("MCP tool arguments must use supported primitive types")
        item = {"type": spec["type"]}
        for key in ("minLength", "maxLength", "minimum", "maximum", "enum"):
            if key in spec:
                candidate = spec[key]
                if key == "enum" and (
                    not isinstance(candidate, list) or len(candidate) > 32
                    or any(not isinstance(x, (str, int, float, bool)) for x in candidate)
                ):
                    raise McpGatewayError("MCP tool enum is invalid")
                if key != "enum" and (
                    isinstance(candidate, bool) or not isinstance(candidate, (int, float))
                    or candidate < 0
                ):
                    raise McpGatewayError("MCP tool argument bound is invalid")
                item[key] = candidate
        if item["type"] == "string":
            item["maxLength"] = min(item.get("maxLength", 2048), 2048)
        if item["type"] in {"integer", "number"}:
            item["maximum"] = min(item.get("maximum", 1_000_000), 1_000_000)
            item["minimum"] = max(item.get("minimum", -1_000_000), -1_000_000)
        narrowed[name] = item
    return {"type": "object", "properties": narrowed, "required": list(required), "additionalProperties": False}


class McpGateway:
    """Bounded MCP JSON-RPC client; only configured read-only tools are exposed."""

    def __init__(
        self, servers: tuple[McpServerConfig, ...], *,
        client: httpx.Client | None = None,
    ) -> None:
        self._servers = {item.server_id: item for item in servers}
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(12.0, connect=4.0),
            follow_redirects=False,
            trust_env=False,
        )
        self._owns_client = client is None
        self._lock = threading.Lock()
        self._next_id = 0
        self._sessions: dict[str, str] = {}
        self._initialized: set[str] = set()
        self._tool_schema_digests: dict[tuple[str, str], str] = {}

    @property
    def configured(self) -> bool:
        return bool(self._servers)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request_id(self) -> int:
        with self._lock:
            self._next_id += 1
            return self._next_id

    def _headers(self, server: McpServerConfig) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if server.server_id in self._sessions:
            headers["Mcp-Session-Id"] = self._sessions[server.server_id]
        if server.bearer_token_env:
            token = os.environ.get(server.bearer_token_env, "")
            if not token or len(token) > 8192 or any(ord(ch) < 33 or ord(ch) > 126 for ch in token):
                raise McpGatewayError("MCP server credentials are unavailable or invalid")
            headers["Authorization"] = "Bearer " + token
        return headers

    def _post(self, server: McpServerConfig, payload: dict[str, Any]) -> tuple[dict[str, Any], httpx.Headers]:
        try:
            with self._client.stream("POST", server.endpoint, headers=self._headers(server), json=payload) as response:
                if response.status_code not in {200, 202}:
                    raise McpGatewayError("MCP server returned an unsuccessful HTTP status")
                content_type = response.headers.get("content-type", "").lower()
                if "application/json" not in content_type:
                    raise McpGatewayError("MCP server must return a JSON response")
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    if len(chunks) + len(chunk) > _MAX_RESPONSE_BYTES:
                        raise McpGatewayError("MCP server response exceeds the size limit")
                    chunks.extend(chunk)
                headers = response.headers
            body = json.loads(bytes(chunks)) if chunks else {}
        except McpGatewayError:
            raise
        except (httpx.HTTPError, ValueError, UnicodeDecodeError) as exc:
            raise McpGatewayError("MCP server request failed safely") from exc
        if not isinstance(body, dict):
            raise McpGatewayError("MCP server returned an invalid JSON-RPC response")
        return body, headers

    def _rpc(self, server: McpServerConfig, method: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": self._request_id(), "method": method, "params": params}
        body, headers = self._post(server, payload)
        session_id = headers.get("Mcp-Session-Id")
        if session_id:
            if len(session_id) > 256 or any(ord(ch) < 33 or ord(ch) > 126 for ch in session_id):
                raise McpGatewayError("MCP session identifier is invalid")
            self._sessions[server.server_id] = session_id
        if body.get("jsonrpc") != "2.0" or body.get("id") != payload["id"]:
            raise McpGatewayError("MCP server response did not match the request")
        if body.get("error") is not None:
            raise McpGatewayError("MCP server reported a tool protocol error")
        result = body.get("result")
        if not isinstance(result, dict):
            raise McpGatewayError("MCP server result is invalid")
        return result

    def _initialize(self, server: McpServerConfig) -> None:
        if server.server_id in self._initialized:
            return
        result = self._rpc(server, "initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "ODEI NEXUS", "version": "1"},
        })
        if result.get("protocolVersion") != "2025-03-26":
            raise McpGatewayError("MCP server negotiated an unsupported protocol version")
        payload = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        try:
            with self._client.stream(
                "POST", server.endpoint, headers=self._headers(server), json=payload,
            ) as response:
                if response.status_code not in {200, 202, 204}:
                    raise McpGatewayError("MCP server rejected initialization")
                for chunk in response.iter_bytes():
                    if chunk:
                        raise McpGatewayError("MCP notification unexpectedly returned a body")
        except McpGatewayError:
            raise
        except httpx.HTTPError as exc:
            raise McpGatewayError("MCP initialization failed safely") from exc
        self._initialized.add(server.server_id)

    def agent_tools(self) -> list[dict[str, Any]]:
        """Fetch and expose only configured allowlisted MCP tools."""
        exposed: list[dict[str, Any]] = []
        names: set[str] = set()
        for server in self._servers.values():
            self._initialize(server)
            result = self._rpc(server, "tools/list", {})
            available = result.get("tools")
            if not isinstance(available, list) or len(available) > 256:
                raise McpGatewayError("MCP tool catalogue is invalid")
            by_name = {
                item.get("name"): item for item in available
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            }
            for tool_name in server.allowed_tools:
                tool = by_name.get(tool_name)
                if tool is None:
                    raise McpGatewayError("A configured MCP tool is not available")
                name = "mcp_" + server.server_id + "_" + re.sub(r"[^a-zA-Z0-9_]", "_", tool_name)
                name = name.lower()[:64]
                if name in names:
                    raise McpGatewayError("MCP tool names collide after namespacing")
                names.add(name)
                description = tool.get("description", "Approved read-only MCP integration tool")
                annotations = tool.get("annotations")
                if (
                    not isinstance(description, str) or len(description) > 1000
                    or not isinstance(annotations, dict)
                    or annotations.get("readOnlyHint") is not True
                    or annotations.get("destructiveHint") is True
                ):
                    raise McpGatewayError("MCP tool is not explicitly annotated as read-only")
                raw_schema = tool.get("inputSchema", {"type": "object"})
                schema = _strict_tool_schema(raw_schema)
                self._tool_schema_digests[(server.server_id, tool_name)] = __import__("hashlib").sha256(
                    json.dumps(raw_schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                exposed.append({
                    "name": name,
                    "description": redact_secrets(description)[:1000],
                    "parameters": schema,
                    "handler": self._handler(server.server_id, tool_name),
                })
        return exposed

    def _handler(self, server_id: str, tool_name: str):
        def invoke(arguments: dict[str, Any]) -> str:
            return self.call_tool(server_id, tool_name, arguments)
        return invoke

    def call_tool(self, server_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
        server = self._servers.get(server_id)
        if server is None or tool_name not in server.allowed_tools:
            raise McpGatewayError("MCP tool is not allowlisted")
        if not isinstance(arguments, dict) or len(json.dumps(arguments, separators=(",", ":"))) > 16_384:
            raise McpGatewayError("MCP tool arguments exceed the size limit")
        self._initialize(server)
        current = self._rpc(server, "tools/list", {}).get("tools")
        if not isinstance(current, list):
            raise McpGatewayError("MCP tool catalogue is invalid")
        current_tool = next(
            (item for item in current if isinstance(item, dict) and item.get("name") == tool_name),
            None,
        )
        if current_tool is None:
            raise McpGatewayError("MCP tool is no longer available")
        current_digest = __import__("hashlib").sha256(
            json.dumps(current_tool.get("inputSchema", {"type": "object"}), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if current_digest != self._tool_schema_digests.get((server_id, tool_name)):
            raise McpGatewayError("MCP tool schema changed after it was approved for this session")
        annotations = current_tool.get("annotations")
        if not isinstance(annotations, dict) or annotations.get("readOnlyHint") is not True or annotations.get("destructiveHint") is True:
            raise McpGatewayError("MCP tool is no longer marked read-only")
        result = self._rpc(server, "tools/call", {"name": tool_name, "arguments": arguments})
        if result.get("isError") is True:
            raise McpGatewayError("MCP tool reported an execution error")
        content = result.get("content")
        if not isinstance(content, list) or len(content) > 64:
            raise McpGatewayError("MCP tool result content is invalid")
        text_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "text" or not isinstance(item.get("text"), str):
                raise McpGatewayError("MCP tool returned unsupported content")
            text_parts.append(item["text"])
        rendered = redact_secrets("\n".join(text_parts))
        if len(rendered) > _MAX_TOOL_OUTPUT_CHARS:
            rendered = rendered[:_MAX_TOOL_OUTPUT_CHARS] + "\n[output truncated]"
        return rendered
