"""Unit tests for MCP client, schema adapter, and tool registry synchronization."""

import pytest
import httpx
from pydantic import BaseModel

from app.mcp.adapter import MCPToolAdapter
from app.mcp.client import HTTPMCPClient, MockMCPClient
from app.mcp.registry_sync import discover_and_register_mcp_tools
from app.tools.base import PermissionLevel, ToolContext
from app.tools.registry import ToolRegistry


class JsonRpcMCPClient(MockMCPClient):
    async def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        response = await super().call_tool(name, arguments)
        return {"jsonrpc": "2.0", "id": 1, "result": response}


@pytest.mark.asyncio
async def test_mock_mcp_client_lifecycle():
    client = MockMCPClient(
        tools=[
            {
                "name": "calculator",
                "description": "Performs basic math operations",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "Math expression like 2+2"},
                    },
                    "required": ["expression"],
                },
            }
        ]
    )

    init_info = await client.initialize()
    assert "protocolVersion" in init_info

    tools = await client.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "calculator"

    result = await client.call_tool("calculator", {"expression": "2+2"})
    assert "content" in result


@pytest.mark.asyncio
async def test_mcp_tool_adapter_schema_validation_and_execution():
    client = MockMCPClient(
        tools=[
            {
                "name": "fetch_weather",
                "description": "Fetch weather for a city",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                    },
                    "required": ["location"],
                },
                "permission_level": "LOW",
            }
        ]
    )
    await client.initialize()

    tools_raw = await client.list_tools()
    adapter = MCPToolAdapter(mcp_client=client, tool_spec=tools_raw[0])

    assert adapter.name == "fetch_weather"
    assert adapter.description == "Fetch weather for a city"
    assert adapter.permission_level == PermissionLevel.LOW

    # Valid execution
    ctx = ToolContext(user_id="user_test")
    res = await adapter.run({"location": "San Francisco"}, ctx)
    assert res.success is True
    assert "Mock output" in res.data or "San Francisco" in str(res.data)

    # Schema validation failure (missing required 'location')
    fail_res = await adapter.run({}, ctx)
    assert fail_res.success is False
    assert "validation failed" in (fail_res.error or "").lower()


@pytest.mark.asyncio
async def test_discover_and_register_mcp_tools():
    client = MockMCPClient(
        tools=[
            {
                "name": "git_status",
                "description": "Check git repository status",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "database_query",
                "description": "Execute read query on database",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string"},
                    },
                    "required": ["sql"],
                },
            },
        ]
    )

    registry = ToolRegistry()
    registered = await discover_and_register_mcp_tools(
        mcp_client=client,
        registry=registry,
        default_permission=PermissionLevel.LOW,
    )

    assert len(registered) == 2
    assert "git_status" in registry
    assert "database_query" in registry
    assert registry.get("git_status") is not None
    assert registry.get("database_query") is not None


@pytest.mark.asyncio
async def test_mcp_adapter_handles_untrusted_malformed_spec():
    client = MockMCPClient()
    malformed_spec = {
        "name": "broken_tool",
        # missing description and inputSchema
    }

    adapter = MCPToolAdapter(mcp_client=client, tool_spec=malformed_spec)
    assert adapter.name == "broken_tool"
    assert adapter.description == "Remote MCP tool"
    assert issubclass(adapter.input_schema, BaseModel)


@pytest.mark.asyncio
async def test_mcp_adapter_accepts_standard_json_rpc_result_envelope():
    client = JsonRpcMCPClient()
    adapter = MCPToolAdapter(
        mcp_client=client,
        tool_spec={
            "name": "external_weather",
            "permission_level": "LOW",
            "inputSchema": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    )

    result = await adapter.run({"location": "Delhi"}, ToolContext())
    assert result.success is True
    assert "Delhi" in result.data


@pytest.mark.asyncio
async def test_mcp_adapter_rejects_untrusted_extra_arguments():
    client = MockMCPClient()
    adapter = MCPToolAdapter(
        mcp_client=client,
        tool_spec={
            "name": "external_weather",
            "permission_level": "LOW",
            "inputSchema": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    )

    result = await adapter.run({"location": "Delhi", "unexpected": True}, ToolContext())
    assert result.success is False
    assert "validation failed" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_http_mcp_client_falls_back_to_standard_json_rpc(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return None

        async def post(self, url: str, json: dict[str, object]):
            calls.append((url, json))
            request = httpx.Request("POST", url)
            if url.endswith("/mcp"):
                if json.get("method") == "initialize":
                    payload = {
                        "jsonrpc": "2.0",
                        "id": json["id"],
                        "result": {"protocolVersion": "2024-11-05"},
                    }
                elif json.get("method") == "tools/list":
                    payload = {"jsonrpc": "2.0", "id": json["id"], "result": {"tools": []}}
                else:
                    payload = {
                        "jsonrpc": "2.0",
                        "id": json["id"],
                        "result": {"content": [{"type": "text", "text": "ok"}]},
                    }
                return httpx.Response(200, json=payload, request=request)
            return httpx.Response(404, json={"detail": "not found"}, request=request)

    monkeypatch.setattr("app.mcp.client.httpx.AsyncClient", FakeAsyncClient)
    client = HTTPMCPClient("https://mcp.example.test")

    assert (await client.initialize())["protocolVersion"] == "2024-11-05"
    assert await client.list_tools() == []
    assert (await client.call_tool("ping", {}))["content"][0]["text"] == "ok"
    assert any(payload.get("jsonrpc") == "2.0" for _, payload in calls)
