"""Model Context Protocol (MCP) Client interface and implementation."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger("nova.mcp.client")


class BaseMCPClient(ABC):
    """Abstract interface for communicating with an MCP server."""

    @abstractmethod
    async def initialize(self) -> dict[str, Any]:
        """Send initialize handshake to MCP server."""

    @abstractmethod
    async def list_tools(self) -> list[dict[str, Any]]:
        """Discover tools exposed by the MCP server."""

    @abstractmethod
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool on the MCP server."""


class HTTPMCPClient(BaseMCPClient):
    """MCP client communicating with an external MCP server over HTTP.

    NOVA originally used three small REST-style endpoints. The client keeps
    those endpoints for compatibility and falls back to the standard MCP
    JSON-RPC methods when a server exposes a single ``/mcp`` endpoint.
    """

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.server_info: dict[str, Any] = {}
        self._request_id = 0

    @property
    def _legacy_root(self) -> str:
        return self.base_url[:-4] if self.base_url.endswith("/mcp") else self.base_url

    @property
    def _standard_endpoint(self) -> str:
        return self.base_url if self.base_url.endswith("/mcp") else f"{self.base_url}/mcp"

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError("MCP server returned a non-object JSON response")
            return data

    @staticmethod
    def _unwrap_json_rpc(data: dict[str, Any]) -> dict[str, Any]:
        if "error" in data:
            error = data["error"]
            if isinstance(error, dict):
                message = error.get("message", "Unknown JSON-RPC error")
            else:
                message = str(error)
            raise RuntimeError(f"MCP JSON-RPC error: {message}")
        result = data.get("result")
        return result if isinstance(result, dict) else data

    async def _legacy_or_standard(
        self,
        legacy_url: str,
        legacy_payload: dict[str, Any],
        rpc_method: str,
        rpc_params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self._unwrap_json_rpc(await self._post(legacy_url, legacy_payload))
        except Exception as legacy_error:
            rpc_payload = {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": rpc_method,
                "params": rpc_params,
            }
            try:
                return self._unwrap_json_rpc(await self._post(self._standard_endpoint, rpc_payload))
            except Exception:
                raise legacy_error

    async def initialize(self) -> dict[str, Any]:
        url = f"{self._legacy_root}/mcp/initialize"
        payload = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "nova-mcp-client", "version": "0.1.0"},
        }
        try:
            data = await self._legacy_or_standard(
                url,
                payload,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "nova-mcp-client", "version": "0.1.0"},
                },
            )
            self.server_info = data
            return data
        except Exception as exc:
            logger.warning("failed to initialize MCP server at %s: %s", url, exc)
            return {"serverInfo": {"name": "offline-mcp-server"}}

    async def list_tools(self) -> list[dict[str, Any]]:
        url = f"{self._legacy_root}/mcp/tools/list"
        try:
            data = await self._legacy_or_standard(url, {}, "tools/list", {})
            tools = data.get("tools", [])
            return tools if isinstance(tools, list) else []
        except Exception as exc:
            logger.warning("failed to list tools from MCP server at %s: %s", url, exc)
            return []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._legacy_root}/mcp/tools/call"
        payload = {"name": name, "arguments": arguments}
        return await self._legacy_or_standard(
            url,
            payload,
            "tools/call",
            {"name": name, "arguments": arguments},
        )


class MockMCPClient(BaseMCPClient):
    """In-memory Mock MCP client for testing and offline integration."""

    def __init__(self, tools: list[dict[str, Any]] | None = None) -> None:
        self.tools = tools or [
            {
                "name": "external_weather",
                "description": "Fetch weather forecast from external service.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                    },
                    "required": ["location"],
                },
                "permission_level": "LOW",
            },
            {
                "name": "external_database_exec",
                "description": "Execute remote database migration or modification.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SQL statement"},
                    },
                    "required": ["query"],
                },
                "permission_level": "HIGH",
            },
        ]
        self.invocations: list[tuple[str, dict[str, Any]]] = []

    async def initialize(self) -> dict[str, Any]:
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "mock-mcp-server", "version": "1.0.0"},
        }

    async def list_tools(self) -> list[dict[str, Any]]:
        return self.tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.invocations.append((name, arguments))
        if name == "external_weather":
            loc = arguments.get("location", "unknown")
            return {
                "content": [{"type": "text", "text": f"Sunny and 22°C in {loc}."}],
                "isError": False,
            }
        elif name == "external_database_exec":
            return {
                "content": [{"type": "text", "text": "Database command executed."}],
                "isError": False,
            }
        return {
            "content": [{"type": "text", "text": f"Mock output from MCP tool '{name}'."}],
            "isError": False,
        }
