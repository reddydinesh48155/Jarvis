"""ToolRegistry managing available tools and permission filtering."""

from __future__ import annotations

import logging
from typing import Any

from app.tools.base import BaseTool, PermissionLevel
from app.tools.builtin.create_report import CreateReportTool
from app.tools.builtin.document_reader import DocumentReaderTool
from app.tools.builtin.file_search import FileSearchTool
from app.tools.builtin.web_search import WebSearchTool

logger = logging.getLogger("nova.tools.registry")

PERMISSION_RANK = {
    PermissionLevel.LOW: 1,
    PermissionLevel.MEDIUM: 2,
    PermissionLevel.HIGH: 3,
}


class ToolRegistry:
    """Registry maintaining available native and MCP-discovered tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if tool.name in self._tools:
            logger.info("replacing registered tool '%s' (%s)", tool.name, tool.permission_level.value)
        else:
            logger.info("registered tool '%s' (%s)", tool.name, tool.permission_level.value)
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Retrieve a tool by name."""
        return self._tools.get(name)

    def list_tools(self, max_permission: PermissionLevel | None = None) -> list[BaseTool]:
        """Return all registered tools, optionally filtered by maximum permission level."""
        if max_permission is not None:
            return self.filter_by_permission(max_permission)
        return list(self._tools.values())

    def filter_by_permission(self, max_level: PermissionLevel) -> list[BaseTool]:
        """Return tools whose permission level is less than or equal to max_level."""
        threshold = PERMISSION_RANK.get(max_level, 3)
        return [
            tool
            for tool in self._tools.values()
            if PERMISSION_RANK.get(tool.permission_level, 1) <= threshold
        ]

    def get_schemas(self, max_level: PermissionLevel | None = None) -> list[dict[str, Any]]:
        """Return OpenAI/MCP function calling schemas for registered tools."""
        tools = self.filter_by_permission(max_level) if max_level else self.list_tools()
        return [tool.to_schema() for tool in tools]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


def create_default_tool_registry() -> ToolRegistry:
    """Create a ToolRegistry preloaded with NOVA's standard builtin sandboxed tools."""
    registry = ToolRegistry()
    registry.register(WebSearchTool())
    registry.register(FileSearchTool())
    registry.register(DocumentReaderTool())
    registry.register(CreateReportTool())
    return registry


# Global default instance
default_tool_registry = create_default_tool_registry()
