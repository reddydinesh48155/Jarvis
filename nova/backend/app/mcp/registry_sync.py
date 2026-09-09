"""Helper for discovering and registering tools from an MCP server into the ToolRegistry."""

from __future__ import annotations

import logging

from app.mcp.adapter import MCPToolAdapter
from app.mcp.client import BaseMCPClient
from app.tools.base import PermissionLevel
from app.tools.registry import ToolRegistry

logger = logging.getLogger("nova.mcp.sync")


async def discover_and_register_mcp_tools(
    mcp_client: BaseMCPClient,
    registry: ToolRegistry,
    default_permission: PermissionLevel = PermissionLevel.MEDIUM,
) -> list[MCPToolAdapter]:
    """Discover tools from an MCP client and register them into the ToolRegistry."""
    logger.info("discovering tools from MCP server...")
    await mcp_client.initialize()
    tool_specs = await mcp_client.list_tools()

    registered_adapters: list[MCPToolAdapter] = []
    for spec in tool_specs:
        try:
            adapter = MCPToolAdapter(
                mcp_client=mcp_client,
                tool_spec=spec,
                default_permission=default_permission,
            )
        except Exception as exc:
            logger.warning("skipping malformed MCP tool specification: %s", exc)
            continue
        registry.register(adapter)
        registered_adapters.append(adapter)
        logger.info(
            "registered MCP tool '%s' (permission: %s)",
            adapter.name,
            adapter.permission_level.value,
        )

    return registered_adapters
