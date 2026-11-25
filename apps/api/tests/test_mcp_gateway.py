import json

import httpx
import pytest

from odei_api.services.mcp_gateway import (
    McpGateway,
    McpGatewayError,
    load_mcp_servers,
)


def config():
    return load_mcp_servers(json.dumps([{
        "id": "docs",
        "endpoint": "https://mcp.example.com/mcp",
        "allowed_tools": ["search_docs"],
    }]))


def test_mcp_gateway_initializes_lists_and_calls_only_configured_read_only_tools():
    calls = []

    def respond(request):
        body = json.loads(request.content)
        calls.append((body.get("method"), request.headers.get("Mcp-Session-Id")))
        method = body.get("method")
        if method == "initialize":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": body["id"],
                "result": {"protocolVersion": "2025-03-26", "capabilities": {}, "serverInfo": {"name": "docs", "version": "1"}},
            }, headers={"Mcp-Session-Id": "session-1"})
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": body["id"],
                "result": {"tools": [{
                    "name": "search_docs", "description": "Search documentation",
                    "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "maxLength": 100}}, "required": ["query"]},
                    "annotations": {"readOnlyHint": True, "destructiveHint": False},
                }]},
            })
        if method == "tools/call":
            assert request.headers.get("Mcp-Session-Id") == "session-1"
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": body["id"],
                "result": {"content": [{"type": "text", "text": "Found three documents"}], "isError": False},
            })
        raise AssertionError("unexpected MCP method")

    client = httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)
    gateway = McpGateway(config(), client=client)
    definitions = gateway.agent_tools()
    assert [item["name"] for item in definitions] == ["mcp_docs_search_docs"]
    assert definitions[0]["parameters"]["required"] == ["query"]
    assert definitions[0]["handler"]({"query": "release"}) == "Found three documents"
    assert [item[0] for item in calls] == [
        "initialize", "notifications/initialized", "tools/list", "tools/list", "tools/call",
    ]
    client.close()


def test_mcp_gateway_rejects_unannotated_or_mutating_tools():
    def respond(request):
        body = json.loads(request.content)
        if body.get("method") == "initialize":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": body["id"],
                "result": {"protocolVersion": "2025-03-26"},
            })
        if body.get("method") == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": body["id"],
            "result": {"tools": [{
                "name": "search_docs", "inputSchema": {"type": "object"},
                "annotations": {"readOnlyHint": False, "destructiveHint": True},
            }]},
        })

    client = httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)
    with pytest.raises(McpGatewayError):
        McpGateway(config(), client=client).agent_tools()
    client.close()


def test_mcp_gateway_rejects_schema_changes_between_discovery_and_call():
    list_count = 0

    def respond(request):
        nonlocal list_count
        body = json.loads(request.content)
        if body.get("method") == "initialize":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": body["id"],
                "result": {"protocolVersion": "2025-03-26"},
            })
        if body.get("method") == "notifications/initialized":
            return httpx.Response(202)
        if body.get("method") == "tools/list":
            list_count += 1
            maximum = 100 if list_count == 1 else 200
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": body["id"],
                "result": {"tools": [{
                    "name": "search_docs",
                    "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "maxLength": maximum}}, "required": ["query"]},
                    "annotations": {"readOnlyHint": True},
                }]},
            })
        raise AssertionError("tool call must not be dispatched")

    client = httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)
    gateway = McpGateway(config(), client=client)
    definition = gateway.agent_tools()[0]
    with pytest.raises(McpGatewayError, match="schema changed"):
        definition["handler"]({"query": "test"})
    client.close()


@pytest.mark.parametrize("endpoint", [
    "http://mcp.example.com/mcp",
    "https://localhost/mcp",
    "https://127.0.0.1/mcp",
    "https://10.0.0.4/mcp",
    "https://mcp.example.com/mcp?token=secret",
    "https://user:pass@mcp.example.com/mcp",
])
def test_mcp_configuration_rejects_insecure_endpoints(endpoint):
    with pytest.raises(ValueError):
        load_mcp_servers(json.dumps([{
            "id": "docs", "endpoint": endpoint, "allowed_tools": ["search_docs"],
        }]))


def test_mcp_configuration_rejects_duplicate_server_ids_and_tool_names():
    with pytest.raises(ValueError):
        load_mcp_servers(json.dumps([
            {"id": "docs", "endpoint": "https://one.example/mcp", "allowed_tools": ["search"]},
            {"id": "docs", "endpoint": "https://two.example/mcp", "allowed_tools": ["search"]},
        ]))
    with pytest.raises(ValueError):
        load_mcp_servers(json.dumps([{
            "id": "docs", "endpoint": "https://one.example/mcp",
            "allowed_tools": ["search", "search"],
        }]))


def test_mcp_tool_schema_rejects_nested_or_unsupported_argument_types():
    def respond(request):
        body = json.loads(request.content)
        if body.get("method") == "initialize":
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": body["id"],
                "result": {"protocolVersion": "2025-03-26"},
            })
        if body.get("method") == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": body["id"],
            "result": {"tools": [{
                "name": "search_docs",
                "inputSchema": {"type": "object", "properties": {"filter": {"type": "object"}}, "required": ["filter"]},
                "annotations": {"readOnlyHint": True},
            }]},
        })

    client = httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)
    with pytest.raises(McpGatewayError):
        McpGateway(config(), client=client).agent_tools()
    client.close()
