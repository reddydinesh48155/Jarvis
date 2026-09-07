"""Unit tests for AgentRegistry and AgentRouter."""

import pytest

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry, create_default_registry
from app.agents.router import AgentRouter
from app.voice.providers.base import ChatMessage, ProviderError
from app.voice.providers.mock import MockLLM


class CustomMathAgent(BaseAgent):
    """Custom pluggable agent for testing extensible registry."""

    name = "math_specialist"
    display_name = "Math Specialist"
    description = "Handles complex mathematical calculations and proofs."
    system_prompt = "You are a mathematics genius."


def test_agent_registry_operations():
    registry = create_default_registry()
    agents = registry.list_agents()
    agent_names = {a.name for a in agents}

    assert "main_assistant" in agent_names
    assert "research" in agent_names
    assert "coding" in agent_names
    assert "productivity" in agent_names

    # Add custom agent without altering core code
    custom_agent = CustomMathAgent()
    registry.register(custom_agent)

    assert "math_specialist" in registry
    assert registry.get("math_specialist") == custom_agent
    assert len(registry.list_agents()) == 5


@pytest.mark.asyncio
async def test_router_selects_expected_agent_from_llm():
    registry = create_default_registry()
    # Mock LLM returns the agent name matching intent
    llm = MockLLM(
        default_response="main_assistant",
        intent_responses={
            "debug": "coding",
            "compare": "research",
            "calendar": "productivity",
        },
    )
    router = AgentRouter(registry=registry, llm=llm)

    # Coding route
    agent, reason = await router.route("Can you help me debug this function?")
    assert agent.name == "coding"
    assert agent.display_name == "Coding Agent"
    assert "coding" in reason

    # Research route
    agent, reason = await router.route("Compare renewable energy sources")
    assert agent.name == "research"
    assert agent.display_name == "Research Agent"

    # Productivity route
    agent, reason = await router.route("Organize my calendar for tomorrow")
    assert agent.name == "productivity"
    assert agent.display_name == "Productivity Agent"


@pytest.mark.asyncio
async def test_router_fallback_on_unrecognized_agent():
    registry = create_default_registry()
    llm = MockLLM(default_response="unknown_nonexistent_agent_xyz")
    router = AgentRouter(registry=registry, llm=llm)

    agent, reason = await router.route("Tell me a random joke")
    assert agent.name == "main_assistant"
    assert "unrecognized classification" in reason


@pytest.mark.asyncio
async def test_router_fallback_on_empty_input():
    registry = create_default_registry()
    router = AgentRouter(registry=registry)

    agent, reason = await router.route("   ")
    assert agent.name == "main_assistant"
    assert "empty input" in reason


@pytest.mark.asyncio
async def test_router_fallback_on_llm_exception():
    class FailingLLM(MockLLM):
        async def generate_response(self, messages: list[ChatMessage], **kwargs) -> str:
            raise ProviderError("Network timeout during intent classification")

    registry = create_default_registry()
    router = AgentRouter(registry=registry, llm=FailingLLM())

    agent, reason = await router.route("Help me write a script")
    assert agent.name == "main_assistant"
    assert "classification error" in reason


@pytest.mark.asyncio
async def test_router_with_new_custom_agent():
    registry = create_default_registry()
    registry.register(CustomMathAgent())

    llm = MockLLM(default_response="math_specialist")
    router = AgentRouter(registry=registry, llm=llm)

    agent, reason = await router.route("Solve the quadratic equation x^2 - 4 = 0")
    assert agent.name == "math_specialist"
    assert agent.display_name == "Math Specialist"
