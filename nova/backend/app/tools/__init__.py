"""Secure permissioned tool system for NOVA agents."""

from app.tools.audit import AuditLogEntry, AuditLogger, audit_logger
from app.tools.base import (
    BaseTool,
    PermissionLevel,
    SecurityError,
    ToolContext,
    ToolExecutionError,
    ToolResult,
)
from app.tools.builtin import (
    CreateReportInput,
    CreateReportTool,
    DocumentReaderInput,
    DocumentReaderTool,
    FileSearchInput,
    FileSearchTool,
    WebSearchInput,
    WebSearchTool,
)
from app.tools.registry import (
    ToolRegistry,
    create_default_tool_registry,
    default_tool_registry,
)

__all__ = [
    "AuditLogEntry",
    "AuditLogger",
    "BaseTool",
    "CreateReportInput",
    "CreateReportTool",
    "DocumentReaderInput",
    "DocumentReaderTool",
    "FileSearchInput",
    "FileSearchTool",
    "PermissionLevel",
    "SecurityError",
    "ToolContext",
    "ToolExecutionError",
    "ToolRegistry",
    "ToolResult",
    "WebSearchInput",
    "WebSearchTool",
    "audit_logger",
    "create_default_tool_registry",
    "default_tool_registry",
]
