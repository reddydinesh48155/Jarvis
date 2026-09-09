"""Base agent interface and data structures for NOVA multi-agent system with secure tool calling."""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.voice.providers.base import ChatMessage, LLMProvider

if TYPE_CHECKING:
    from app.tools.base import BaseTool
    from app.tools.registry import ToolRegistry

logger = logging.getLogger("nova.agents.base")


@dataclass
class AgentContext:
    """Execution context and conversational state passed to an agent."""

    conversation_history: list[ChatMessage] = field(default_factory=list)
    user_id: str | None = None
    session_id: str | None = None
    confirmed: bool = False
    tool_registry: ToolRegistry | None = None
    on_tool_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Standardized response output produced by an agent."""

    content: str
    agent_name: str
    agent_display_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base class for all specialized and general NOVA agents."""

    name: str
    display_name: str
    description: str
    system_prompt: str
    tools: list[BaseTool] | None = None

    def get_messages_for_prompt(
        self, user_input: str, context: AgentContext
    ) -> list[ChatMessage]:
        """Build the list of ChatMessage items including system prompt and recent history."""
        messages = [ChatMessage(role="system", content=self.system_prompt)]
        messages.extend(context.conversation_history)
        messages.append(ChatMessage(role="user", content=user_input))
        return messages

    def _format_tools_prompt(self, tools: list[BaseTool]) -> str:
        lines = [
            "You have access to the following tools to assist the user:",
        ]
        for t in tools:
            lines.append(f"- {t.name} (Risk: {t.permission_level.value}): {t.description}")
            lines.append(f"  Parameters: {json.dumps(t.input_schema.model_json_schema())}")
        lines.append(
            "\nIf you need to execute a tool to answer the request, reply with ONLY a JSON block:\n"
            '```json\n{"tool": "<tool_name>", "arguments": {<arguments>}}\n```\n'
            "If no tool is required, reply directly with your conversational voice response."
        )
        return "\n".join(lines)

    def _parse_tool_call(self, text: str) -> dict[str, Any] | None:
        """Parse structured tool call from LLM response."""
        stripped = text.strip()
        # Look for ```json ... ``` blocks
        json_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL | re.IGNORECASE)
        candidate = json_block_match.group(1).strip() if json_block_match else stripped

        # Parse the complete JSON object. ``raw_decode`` also accepts a short
        # explanatory prefix/suffix while correctly handling nested arguments.
        candidates = [candidate]
        object_start = candidate.find("{")
        if object_start > 0:
            candidates.append(candidate[object_start:])
        for json_candidate in candidates:
            try:
                decoder = json.JSONDecoder()
                data, _ = decoder.raw_decode(json_candidate)
                if isinstance(data, dict) and isinstance(data.get("tool"), str):
                    arguments = data.get("arguments", {})
                    data["arguments"] = arguments if isinstance(arguments, dict) else {}
                    return data
            except json.JSONDecodeError:
                continue
        return None

    def _get_available_tools(
        self,
        context: AgentContext,
        tools: list[BaseTool] | None = None,
    ) -> list[BaseTool]:
        """Resolve the tools available to this turn in a single place."""
        return tools if tools is not None else (
            self.tools if self.tools is not None else (
                context.tool_registry.list_tools() if context.tool_registry else []
            )
        )

    async def handle(
        self,
        user_input: str,
        context: AgentContext,
        llm: LLMProvider,
        tools: list[BaseTool] | None = None,
    ) -> AgentResponse:
        """Process user input with tool decision, permission validation, execution, and synthesis."""
        from app.tools.base import ToolContext

        available_tools = self._get_available_tools(context, tools)

        if not available_tools:
            messages = self.get_messages_for_prompt(user_input, context)
            response_text = await llm.generate_response(messages)
            return AgentResponse(
                content=response_text,
                agent_name=self.name,
                agent_display_name=self.display_name,
            )

        # Build prompt equipped with tool instructions
        system_content = self.system_prompt + "\n\n" + self._format_tools_prompt(available_tools)
        messages = [ChatMessage(role="system", content=system_content)]
        messages.extend(context.conversation_history)
        messages.append(ChatMessage(role="user", content=user_input))

        first_response = await llm.generate_response(messages)
        tool_call = self._parse_tool_call(first_response)

        if tool_call is None:
            # LLM answered conversationally without a tool
            return AgentResponse(
                content=first_response,
                agent_name=self.name,
                agent_display_name=self.display_name,
            )

        tool_name = tool_call.get("tool", "")
        tool_args = tool_call.get("arguments", {})
        tool = next((t for t in available_tools if t.name == tool_name), None)

        if tool is None:
            logger.warning("agent requested unknown tool '%s'", tool_name)
            messages.append(ChatMessage(role="assistant", content=first_response))
            messages.append(ChatMessage(role="user", content=f"Tool error: '{tool_name}' is not recognized."))
            final_text = await llm.generate_response(messages)
            return AgentResponse(
                content=final_text,
                agent_name=self.name,
                agent_display_name=self.display_name,
            )

        # Emit running event
        if context.on_tool_event:
            await context.on_tool_event({
                "type": "tool_call",
                "tool_name": tool.name,
                "status": "running",
                "arguments": tool_args,
            })

        tool_ctx = ToolContext(
            user_id=context.user_id,
            session_id=context.session_id,
            confirmed=context.confirmed,
            metadata=dict(context.metadata),
        )
        tool_result = await tool.run(tool_args, tool_ctx)

        # Emit completed/blocked event
        if context.on_tool_event:
            status_str = (
                "confirmation_required"
                if tool_result.requires_confirmation
                else ("completed" if tool_result.success else "failed")
            )
            await context.on_tool_event({
                "type": "tool_call",
                "tool_name": tool.name,
                "status": status_str,
                "success": tool_result.success,
                "requires_confirmation": tool_result.requires_confirmation,
                "data": tool_result.data,
                "error": tool_result.error,
            })

        if tool_result.requires_confirmation:
            confirm_message = (
                f"The action '{tool.name}' requires your confirmation before proceeding. "
                f"Would you like me to proceed?"
            )
            return AgentResponse(
                content=confirm_message,
                agent_name=self.name,
                agent_display_name=self.display_name,
                metadata={
                    "requires_confirmation": True,
                    "tool_name": tool.name,
                    "arguments": tool_args,
                },
            )

        # Feed tool execution result back into LLM to synthesize final spoken answer
        tool_data_str = json.dumps(tool_result.data, default=str) if tool_result.success else f"Error: {tool_result.error}"
        messages.append(ChatMessage(role="assistant", content=first_response))
        messages.append(
            ChatMessage(
                role="user",
                content=(
                    f"Tool '{tool.name}' executed with result:\n{tool_data_str}\n\n"
                    "Now synthesize a natural, concise spoken answer for the user incorporating these findings."
                ),
            )
        )
        final_text = await llm.generate_response(messages)
        return AgentResponse(
            content=final_text,
            agent_name=self.name,
            agent_display_name=self.display_name,
            metadata={"tool_called": tool.name, "tool_result": tool_result.to_dict()},
        )

    async def handle_stream(
        self,
        user_input: str,
        context: AgentContext,
        llm: LLMProvider,
    ) -> AsyncIterator[str]:
        """Process user input and stream response tokens."""
        available_tools = self._get_available_tools(context)
        if available_tools:
            # Tool decisions require a complete first response. Once the
            # result is synthesized, yield it through the same async-stream
            # interface used by the voice pipeline.
            response = await self.handle(user_input, context, llm, available_tools)
            yield response.content
            return

        messages = self.get_messages_for_prompt(user_input, context)
        async for token in llm.stream_response(messages):
            yield token
