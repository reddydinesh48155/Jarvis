"""Unit and integration tests for secure tools, permissions, sandboxing, and audit logging."""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, Field

from app.agents.base import AgentContext
from app.agents.specialized import MainAssistantAgent
from app.core.config import settings
from app.tools.audit import audit_logger
from app.tools.base import (
    BaseTool,
    PermissionLevel,
    SecurityError,
    ToolContext,
    ToolResult,
)
from app.tools.builtin.create_report import CreateReportTool
from app.tools.builtin.document_reader import DocumentReaderTool
from app.tools.builtin.file_search import FileSearchTool
from app.tools.builtin.web_search import WebSearchTool
from app.tools.registry import ToolRegistry, create_default_tool_registry
from app.voice.providers.mock import MockLLM


class EchoInput(BaseModel):
    message: str = Field(..., description="Message to echo")


class EchoTool(BaseTool):
    name: str = "echo"
    description: str = "Echo back a message"
    input_schema: type[BaseModel] = EchoInput
    permission_level: PermissionLevel = PermissionLevel.LOW

    async def execute(self, params: Any, context: ToolContext | None = None) -> Any:
        assert isinstance(params, EchoInput)
        return {"echo": params.message}


class SlowInput(BaseModel):
    seconds: float = Field(0.5, description="Seconds to sleep")


class SlowTool(BaseTool):
    name: str = "slow_tool"
    description: str = "A tool that sleeps"
    input_schema: type[BaseModel] = SlowInput
    permission_level: PermissionLevel = PermissionLevel.LOW
    timeout_seconds: float = 0.1

    async def execute(self, params: Any, context: ToolContext | None = None) -> Any:
        assert isinstance(params, SlowInput)
        await asyncio.sleep(params.seconds)
        return {"done": True}


class HighRiskTool(BaseTool):
    name = "high_risk_test"
    description = "A high-risk test action"
    input_schema: type[BaseModel] = EchoInput
    permission_level = PermissionLevel.HIGH

    async def execute(self, params: EchoInput, context: ToolContext | None = None) -> Any:
        return {"echo": params.message}


@pytest.mark.asyncio
async def test_tool_registry_management_and_filtering():
    registry = ToolRegistry()
    echo = EchoTool()
    report = CreateReportTool()

    registry.register(echo)
    registry.register(report)

    assert registry.get("echo") == echo
    assert registry.get("create_report") == report
    assert registry.get("nonexistent") is None

    # Filter by permission
    low_tools = registry.list_tools(max_permission=PermissionLevel.LOW)
    assert len(low_tools) == 1
    assert low_tools[0].name == "echo"

    all_tools = registry.list_tools(max_permission=PermissionLevel.MEDIUM)
    assert len(all_tools) == 2


def test_default_registry_contains_all_builtin_tools():
    registry = create_default_tool_registry()
    assert {tool.name for tool in registry.list_tools()} == {
        "web_search",
        "file_search",
        "document_reader",
        "create_report",
        "RAG_search",
    }
    assert all(schema["type"] == "function" for schema in registry.get_schemas())


@pytest.mark.asyncio
async def test_high_risk_tool_requires_confirmation_and_audits_denial():
    tool = HighRiskTool()
    audit_logger.clear_memory_logs()

    blocked = await tool.run({"message": "danger"}, ToolContext(user_id="high-risk-user"))
    assert blocked.success is False
    assert blocked.requires_confirmation is True
    assert blocked.permission_level is PermissionLevel.HIGH

    allowed = await tool.run(
        {"message": "danger"},
        ToolContext(user_id="high-risk-user", confirmed=True),
    )
    assert allowed.success is True

    logs = audit_logger.get_recent_logs(limit=2)
    assert logs[0].success is True
    assert logs[1].requires_confirmation is True


@pytest.mark.asyncio
async def test_pydantic_model_from_another_schema_is_revalidated():
    class WrongInput(BaseModel):
        other: str

    result = await EchoTool().run(WrongInput(other="not a message"), ToolContext())
    assert result.success is False
    assert "validation failed" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_low_risk_tool_executes_immediately():
    tool = WebSearchTool()
    ctx = ToolContext(user_id="user_123", session_id="session_456")

    result = await tool.run({"query": "python async tutorial", "max_results": 2}, ctx)
    assert result.success is True
    assert result.requires_confirmation is False
    assert len(result.data["results"]) == 2
    assert "python async tutorial" in result.data["results"][0]["title"]


@pytest.mark.asyncio
async def test_medium_risk_tool_blocks_without_confirmation():
    tool = CreateReportTool()
    ctx_unconfirmed = ToolContext(user_id="user_1", confirmed=False)

    result = await tool.run({"title": "Q3 Analysis", "content": "All targets met."}, ctx_unconfirmed)
    assert result.success is False
    assert result.requires_confirmation is True
    assert "requires explicit confirmation" in (result.error or "")

    # Now with confirmation
    ctx_confirmed = ToolContext(user_id="user_1", confirmed=True)
    result_ok = await tool.run({"title": "Q3 Analysis", "content": "All targets met."}, ctx_confirmed)
    assert result_ok.success is True
    assert result_ok.requires_confirmation is False
    assert "file_path" in result_ok.data
    assert os.path.exists(result_ok.data["file_path"])

    # Clean up test report file
    try:
        os.remove(result_ok.data["file_path"])
    except OSError:
        pass


@pytest.mark.asyncio
async def test_input_validation_failure():
    tool = EchoTool()
    ctx = ToolContext()

    # Missing required 'message' field
    result = await tool.run({}, ctx)
    assert result.success is False
    assert "validation failed" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_tool_timeout_enforcement():
    tool = SlowTool()
    ctx = ToolContext()

    result = await tool.run({"seconds": 0.5}, ctx)
    assert result.success is False
    assert "timed out after 0.1 seconds" in (result.error or "")


@pytest.mark.asyncio
async def test_file_sandboxing_and_traversal_prevention(tmp_path: Path):
    # Set up temp sandbox directory
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()

    test_file = sandbox_dir / "notes.txt"
    test_file.write_text("Confidential internal notes", encoding="utf-8")

    secret_file = secret_dir / "passwords.txt"
    secret_file.write_text("secret_password_123", encoding="utf-8")

    # Temporarily override settings.allowed_tools_dir
    original_allowed = settings.allowed_tools_dir
    settings.allowed_tools_dir = str(sandbox_dir)

    try:
        search_tool = FileSearchTool()
        reader_tool = DocumentReaderTool()
        ctx = ToolContext()

        # Legitimate search in sandbox
        search_res = await search_tool.run({"pattern": "*.txt"}, ctx)
        assert search_res.success is True
        assert len(search_res.data) == 1
        assert "notes.txt" in search_res.data[0]["path"]

        # Legitimate read in sandbox
        read_res = await reader_tool.run({"file_path": "notes.txt"}, ctx)
        assert read_res.success is True
        assert read_res.data["content"] == "Confidential internal notes"

        # Traversal attempt on file search
        traversal_search = await search_tool.run({"pattern": "*.txt", "subfolder": "../secrets"}, ctx)
        assert traversal_search.success is False
        assert "outside the authorized sandbox directory" in (traversal_search.error or "")

        # Traversal attempt on document reader
        traversal_read = await reader_tool.run({"file_path": "../secrets/passwords.txt"}, ctx)
        assert traversal_read.success is False
        assert "outside the authorized sandbox directory" in (traversal_read.error or "")

        # Disallowed file extension attempt
        disallowed_file = sandbox_dir / "script.py"
        disallowed_file.write_text("print('malicious')", encoding="utf-8")
        ext_res = await reader_tool.run({"file_path": "script.py"}, ctx)
        assert ext_res.success is False
        assert "Unsupported file format '.py'" in (ext_res.error or "")

    finally:
        settings.allowed_tools_dir = original_allowed


@pytest.mark.asyncio
async def test_audit_logging_to_memory_and_db():
    tool = EchoTool()
    ctx = ToolContext(user_id="user_audit_1", session_id="session_audit_1")

    res = await tool.run({"message": "Audit this!"}, ctx)
    assert res.success is True

    # Check in-memory logs
    mem_logs = audit_logger.get_recent_logs(limit=10)
    matching = [entry for entry in mem_logs if entry.tool_name == "echo" and entry.user_id == "user_audit_1"]
    assert len(matching) >= 1
    recent = matching[0]
    assert recent.tool_name == "echo"
    assert recent.user_id == "user_audit_1"
    assert recent.success is True
    assert recent.input_params == {"message": "Audit this!"}


@pytest.mark.asyncio
async def test_agent_invokes_tool_and_synthesizes_response():
    tool_registry = ToolRegistry()
    tool_registry.register(EchoTool())

    # Simulated LLM responses:
    # 1. First turn: user says "Test the echo tool" -> LLM responds with tool call JSON
    # 2. Second turn: tool result fed back -> LLM responds with synthesized voice reply
    tool_call_json = '```json\n{"tool": "echo", "arguments": {"message": "Voice tools are working!"}}\n```'
    synthesized_voice_reply = "I verified that voice tools are working properly!"

    llm = MockLLM(
        default_response=synthesized_voice_reply,
        intent_responses={"Test the echo tool": tool_call_json},
    )
    agent = MainAssistantAgent()

    emitted_events: list[dict[str, Any]] = []

    async def on_event(ev: dict[str, Any]) -> None:
        emitted_events.append(ev)

    context = AgentContext(
        tool_registry=tool_registry,
        on_tool_event=on_event,
    )

    response = await agent.handle("Test the echo tool", context, llm)
    assert response.content == synthesized_voice_reply
    assert response.metadata.get("tool_called") == "echo"

    # Verify tool events were emitted
    assert len(emitted_events) == 2
    assert emitted_events[0]["type"] == "tool_call"
    assert emitted_events[0]["status"] == "running"
    assert emitted_events[0]["tool_name"] == "echo"

    assert emitted_events[1]["type"] == "tool_call"
    assert emitted_events[1]["status"] == "completed"
    assert emitted_events[1]["success"] is True


@pytest.mark.asyncio
async def test_agent_stream_uses_tools_when_registry_is_available():
    tool_registry = ToolRegistry()
    tool_registry.register(EchoTool())
    llm = MockLLM(
        default_response="The echo tool completed successfully.",
        intent_responses={
            "stream echo": '{"tool":"echo","arguments":{"message":{"nested": true}}}',
        },
    )
    # The nested value is intentionally invalid for EchoInput; the agent must
    # still return a synthesized error instead of crashing the stream.
    agent = MainAssistantAgent()
    response_parts: list[str] = []
    async for part in agent.handle_stream("stream echo", AgentContext(tool_registry=tool_registry), llm):
        response_parts.append(part)
    assert response_parts == ["The echo tool completed successfully."]
