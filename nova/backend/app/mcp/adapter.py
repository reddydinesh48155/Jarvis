"""MCP Adapter wrapping untrusted remote MCP tools into secure BaseTool instances."""

from __future__ import annotations

import logging
from typing import Any, Type

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.mcp.client import BaseMCPClient
from app.tools.base import BaseTool, PermissionLevel, ToolContext, ToolExecutionError

logger = logging.getLogger("nova.mcp.adapter")

TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def create_pydantic_model_from_schema(tool_name: str, schema: dict[str, Any]) -> Type[BaseModel]:
    """Dynamically generate a Pydantic model from an MCP JSON Schema for strict validation."""
    if not isinstance(schema, dict):
        schema = {}
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}
    required_value = schema.get("required", [])
    required_fields = set(required_value) if isinstance(required_value, list) else set()

    field_definitions: dict[str, Any] = {}
    for field_name, field_spec in properties.items():
        if not isinstance(field_spec, dict):
            field_spec = {}
        field_type_str = field_spec.get("type", "string")
        if not isinstance(field_type_str, str):
            field_type_str = "string"
        py_type = TYPE_MAP.get(field_type_str, Any)
        description = field_spec.get("description")

        if field_name in required_fields:
            field_definitions[field_name] = (
                py_type,
                Field(..., description=description) if description else ...,
            )
        else:
            default_val = field_spec.get("default", None)
            field_definitions[field_name] = (
                py_type | None,
                Field(default=default_val, description=description) if description else default_val,
            )

    # If no properties defined, create an empty model that allows no extra fields
    clean_class_name = "".join(part.capitalize() for part in tool_name.split("_")) + "Input"
    try:
        return create_model(
            clean_class_name,
            __config__=ConfigDict(extra="forbid"),
            **field_definitions,
        )
    except Exception as exc:
        logger.warning("could not build dynamic model for %s: %s; using generic model", tool_name, exc)

        class FallbackInput(BaseModel):
            model_config = ConfigDict(extra="forbid")

        return FallbackInput


class MCPToolAdapter(BaseTool):
    """Adapts an untrusted tool discovered from an MCP server into a secure BaseTool."""

    def __init__(
        self,
        mcp_client: BaseMCPClient,
        tool_spec: dict[str, Any],
        default_permission: PermissionLevel = PermissionLevel.MEDIUM,
    ) -> None:
        self.mcp_client = mcp_client
        self.tool_spec = tool_spec
        raw_name = tool_spec.get("name", "unnamed_mcp_tool")
        self.name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else "unnamed_mcp_tool"
        self.description = tool_spec.get("description", "Remote MCP tool")

        # Untrusted security policy: default to MEDIUM risk unless explicitly marked or classified
        spec_level = str(tool_spec.get("permission_level", tool_spec.get("permissionLevel", ""))).upper()
        if spec_level in ("LOW", "MEDIUM", "HIGH"):
            self.permission_level = PermissionLevel(spec_level)
        else:
            self.permission_level = default_permission

        input_schema_dict = tool_spec.get("inputSchema", {})
        self.input_schema = create_pydantic_model_from_schema(self.name, input_schema_dict)
        try:
            self.timeout_seconds = min(max(float(tool_spec.get("timeout_seconds", 12.0)), 0.1), 60.0)
        except (TypeError, ValueError):
            self.timeout_seconds = 12.0

    async def execute(self, params: Any, context: ToolContext | None = None) -> Any:
        args = params.model_dump() if isinstance(params, BaseModel) else dict(params)
        logger.info("dispatching call to remote MCP tool '%s' with args: %s", self.name, list(args.keys()))

        try:
            mcp_response = await self.mcp_client.call_tool(self.name, args)
        except Exception as exc:
            raise ToolExecutionError(f"Remote MCP server error executing '{self.name}': {exc}") from exc

        if not isinstance(mcp_response, dict):
            raise ToolExecutionError(f"MCP tool '{self.name}' returned an invalid response")

        # Standard MCP responses place the call result under JSON-RPC
        # ``result``; accept both that envelope and NOVA's legacy shape.
        if "error" in mcp_response:
            error = mcp_response["error"]
            raise ToolExecutionError(f"MCP tool '{self.name}' returned an error: {error}")
        mcp_response = mcp_response.get("result", mcp_response)
        if not isinstance(mcp_response, dict):
            raise ToolExecutionError(f"MCP tool '{self.name}' returned an invalid result")

        if mcp_response.get("isError", False):
            error_content = mcp_response.get("content", [{"text": "Unknown MCP error"}])
            first_error = error_content[0] if isinstance(error_content, list) and error_content else {}
            err_msg = first_error.get("text", "Error reported by MCP tool")
            raise ToolExecutionError(f"MCP tool '{self.name}' returned an error: {err_msg}")

        # Extract text content from MCP format
        contents = mcp_response.get("content", [])
        text_parts = [
            c.get("text", "")
            for c in contents
            if isinstance(c, dict) and c.get("type") == "text"
        ] if isinstance(contents, list) else []
        if text_parts:
            # Sanitize untrusted MCP output to prevent prompt injection (Part 8)
            from app.middleware.sanitization import sanitize_tool_output
            return sanitize_tool_output(" ".join(text_parts).strip())
        return mcp_response.get("structuredContent", mcp_response)
