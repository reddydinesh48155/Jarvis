"""Base agent interface and data structures for NOVA multi-agent system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.voice.providers.base import ChatMessage, LLMProvider


@dataclass
class AgentContext:
    """Execution context and conversational state passed to an agent."""

    conversation_history: list[ChatMessage] = field(default_factory=list)
    user_id: str | None = None
    session_id: str | None = None
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

    def get_messages_for_prompt(
        self, user_input: str, context: AgentContext
    ) -> list[ChatMessage]:
        """Build the list of ChatMessage items including system prompt and recent history."""
        messages = [ChatMessage(role="system", content=self.system_prompt)]
        # Include recent history if available
        messages.extend(context.conversation_history)
        # Append current user input
        messages.append(ChatMessage(role="user", content=user_input))
        return messages

    async def handle(
        self,
        user_input: str,
        context: AgentContext,
        llm: LLMProvider,
    ) -> AgentResponse:
        """Process user input and return a complete conversational response."""
        messages = self.get_messages_for_prompt(user_input, context)
        response_text = await llm.generate_response(messages)
        return AgentResponse(
            content=response_text,
            agent_name=self.name,
            agent_display_name=self.display_name,
        )

    async def handle_stream(
        self,
        user_input: str,
        context: AgentContext,
        llm: LLMProvider,
    ) -> AsyncIterator[str]:
        """Process user input and stream response tokens."""
        messages = self.get_messages_for_prompt(user_input, context)
        async for token in llm.stream_response(messages):
            yield token
