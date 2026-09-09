"""BaseTool interface and common execution definitions for the NOVA tool system."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ValidationError


class PermissionLevel(str, Enum):
    """Tool risk and authorization levels."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SecurityError(Exception):
    """Raised when a security policy or sandbox boundary is violated."""


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""


@dataclass
class ToolContext:
    """Execution context passed to tools, containing user identity and confirmation flags."""

    user_id: str | None = None
    session_id: str | None = None
    confirmed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Standardized response from a tool execution."""

    success: bool
    data: Any = None
    error: str | None = None
    requires_confirmation: bool = False
    permission_level: PermissionLevel = PermissionLevel.LOW
    execution_time_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "requires_confirmation": self.requires_confirmation,
            "permission_level": self.permission_level.value,
            "execution_time_ms": self.execution_time_ms,
        }


class BaseTool(ABC):
    """Abstract base class for all tools executable by NOVA agents."""

    name: str
    description: str
    input_schema: type[BaseModel]
    permission_level: PermissionLevel = PermissionLevel.LOW
    timeout_seconds: float = 10.0

    def to_schema(self) -> dict[str, Any]:
        """Generate OpenAI/MCP compatible tool definition schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema.model_json_schema(),
            },
            "permission_level": self.permission_level.value,
        }

    @abstractmethod
    async def execute(self, params: Any, context: ToolContext | None = None) -> Any:
        """Core tool logic implemented by specialized tools."""

    async def run(
        self,
        input_data: BaseModel | dict[str, Any],
        context: ToolContext | None = None,
    ) -> ToolResult:
        """Run tool with schema validation, permission checks, timeout, and audit logging."""
        from app.tools.audit import audit_logger

        start_time = time.perf_counter()
        ctx = context or ToolContext()

        # Step 1: Permission Enforcement
        if self.permission_level in (PermissionLevel.MEDIUM, PermissionLevel.HIGH) and not ctx.confirmed:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            error_msg = (
                f"Tool '{self.name}' requires explicit confirmation "
                f"(risk level: {self.permission_level.value}). Pass confirmed=True to proceed."
            )
            raw_input = input_data.model_dump() if isinstance(input_data, BaseModel) else input_data
            await audit_logger.log_tool_call(
                tool_name=self.name,
                user_id=ctx.user_id,
                input_params=raw_input,
                output_result=None,
                success=False,
                error_message=error_msg,
                permission_level=self.permission_level,
                requires_confirmation=True,
                confirmed=False,
                execution_time_ms=elapsed_ms,
            )
            return ToolResult(
                success=False,
                data=None,
                error=error_msg,
                requires_confirmation=True,
                permission_level=self.permission_level,
                execution_time_ms=elapsed_ms,
            )

        # Step 2: Input Validation
        try:
            if isinstance(input_data, self.input_schema):
                validated_params = input_data
                raw_input = input_data.model_dump()
            elif isinstance(input_data, BaseModel):
                # Re-validate arbitrary Pydantic models against this tool's
                # schema instead of allowing a different model to bypass it.
                raw_input = input_data.model_dump()
                validated_params = self.input_schema.model_validate(raw_input)
            else:
                validated_params = self.input_schema.model_validate(input_data)
                raw_input = validated_params.model_dump()
        except ValidationError as val_err:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Schema validation failed for tool '{self.name}': {val_err}"
            await audit_logger.log_tool_call(
                tool_name=self.name,
                user_id=ctx.user_id,
                input_params=input_data if isinstance(input_data, dict) else {},
                output_result=None,
                success=False,
                error_message=err_msg,
                permission_level=self.permission_level,
                requires_confirmation=False,
                confirmed=ctx.confirmed,
                execution_time_ms=elapsed_ms,
            )
            return ToolResult(
                success=False,
                data=None,
                error=err_msg,
                requires_confirmation=False,
                permission_level=self.permission_level,
                execution_time_ms=elapsed_ms,
            )

        # Step 3: Execution with Timeout
        try:
            result_data = await asyncio.wait_for(
                self.execute(validated_params, ctx),
                timeout=self.timeout_seconds,
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            await audit_logger.log_tool_call(
                tool_name=self.name,
                user_id=ctx.user_id,
                input_params=raw_input,
                output_result=result_data,
                success=True,
                error_message=None,
                permission_level=self.permission_level,
                requires_confirmation=False,
                confirmed=ctx.confirmed,
                execution_time_ms=elapsed_ms,
            )
            return ToolResult(
                success=True,
                data=result_data,
                permission_level=self.permission_level,
                execution_time_ms=elapsed_ms,
            )
        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Tool '{self.name}' timed out after {self.timeout_seconds} seconds."
            await audit_logger.log_tool_call(
                tool_name=self.name,
                user_id=ctx.user_id,
                input_params=raw_input,
                output_result=None,
                success=False,
                error_message=err_msg,
                permission_level=self.permission_level,
                requires_confirmation=False,
                confirmed=ctx.confirmed,
                execution_time_ms=elapsed_ms,
            )
            return ToolResult(
                success=False,
                error=err_msg,
                permission_level=self.permission_level,
                execution_time_ms=elapsed_ms,
            )
        except SecurityError as sec_err:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Security error in '{self.name}': {sec_err}"
            await audit_logger.log_tool_call(
                tool_name=self.name,
                user_id=ctx.user_id,
                input_params=raw_input,
                output_result=None,
                success=False,
                error_message=err_msg,
                permission_level=self.permission_level,
                requires_confirmation=False,
                confirmed=ctx.confirmed,
                execution_time_ms=elapsed_ms,
            )
            return ToolResult(
                success=False,
                error=err_msg,
                permission_level=self.permission_level,
                execution_time_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            err_msg = f"Execution error in '{self.name}': {exc}"
            await audit_logger.log_tool_call(
                tool_name=self.name,
                user_id=ctx.user_id,
                input_params=raw_input,
                output_result=None,
                success=False,
                error_message=err_msg,
                permission_level=self.permission_level,
                requires_confirmation=False,
                confirmed=ctx.confirmed,
                execution_time_ms=elapsed_ms,
            )
            return ToolResult(
                success=False,
                error=err_msg,
                permission_level=self.permission_level,
                execution_time_ms=elapsed_ms,
            )
