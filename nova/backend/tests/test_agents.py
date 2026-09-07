"""Unit tests for BaseAgent and specialized agents."""

import pytest

from app.agents.base import AgentContext
from app.agents.specialized import (
    CodingAgent,
    MainAssistantAgent,
    ProductivityAgent,
    ResearchAgent,
)
from app.voice.providers.base import ChatMessage
from app.voice.providers.mock import MockLLM


@pytest.mark.asyncio
async def test_main_assistant_agent_handle():
    agent = MainAssistantAgent()
    assert agent.name == "main_assistant"
    assert agent.display_name == "Main Assistant"

    llm = MockLLM(default_response="Hello! I am NOVA, your voice assistant.")
    context = AgentContext()

    response = await agent.handle("Hi there", context, llm)
    assert response.agent_name == "main_assistant"
    assert response.agent_display_name == "Main Assistant"
    assert "NOVA" in response.content


@pytest.mark.asyncio
async def test_specialized_agents_system_prompts():
    research = ResearchAgent()
    coding = CodingAgent()
    prod = ProductivityAgent()

    assert research.name == "research"
    assert "Research Specialist" in research.system_prompt

    assert coding.name == "coding"
    assert "Coding" in coding.system_prompt

    assert prod.name == "productivity"
    assert "Productivity" in prod.system_prompt


@pytest.mark.asyncio
async def test_agent_includes_history_and_streams():
    agent = CodingAgent()
    llm = MockLLM(default_response="Use asyncio.gather for parallel tasks.")
    context = AgentContext(
        conversation_history=[
            ChatMessage(role="user", content="How do I run async tasks?"),
            ChatMessage(role="assistant", content="You can use asyncio."),
        ]
    )

    tokens: list[str] = []
    async for token in agent.handle_stream("Give an example", context, llm):
        tokens.append(token)

    assert "".join(tokens) == "Use asyncio.gather for parallel tasks."
    # Verify the LLM was passed system prompt + 2 history messages + 1 current message = 4 messages
    assert len(llm.recorded_messages[0]) == 4
    assert llm.recorded_messages[0][0].role == "system"
    assert llm.recorded_messages[0][1].content == "How do I run async tasks?"
    assert llm.recorded_messages[0][3].content == "Give an example"
