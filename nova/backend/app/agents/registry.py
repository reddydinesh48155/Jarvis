"""Agent registry providing extensible registration and discovery of agents."""

from __future__ import annotations

import logging

from app.agents.base import BaseAgent
from app.agents.specialized import (
    CodingAgent,
    MainAssistantAgent,
    ProductivityAgent,
    ResearchAgent,
)

logger = logging.getLogger("nova.agents.registry")


class AgentRegistry:
    """Registry maintaining available agents for routing and discovery."""

    def __init__(self, default_agent: BaseAgent | None = None) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._default_agent = default_agent or MainAssistantAgent()
        self.register(self._default_agent)

    def register(self, agent: BaseAgent) -> None:
        """Register an agent instance into the registry."""
        if agent.name in self._agents:
            logger.info("replacing existing registered agent '%s'", agent.name)
        else:
            logger.info("registered agent '%s' (%s)", agent.name, agent.display_name)
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent | None:
        """Retrieve an agent by unique name."""
        return self._agents.get(name)

    def get_default(self) -> BaseAgent:
        """Return the default fallback agent (Main Assistant)."""
        return self._default_agent

    def list_agents(self) -> list[BaseAgent]:
        """Return all registered agents."""
        return list(self._agents.values())

    def __contains__(self, name: str) -> bool:
        return name in self._agents


def create_default_registry() -> AgentRegistry:
    """Create a registry preloaded with NOVA's standard specialized agents."""
    main_agent = MainAssistantAgent()
    registry = AgentRegistry(default_agent=main_agent)
    registry.register(ResearchAgent())
    registry.register(CodingAgent())
    registry.register(ProductivityAgent())
    return registry
