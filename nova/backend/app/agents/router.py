"""Multi-agent router that dynamically classifies user intent and delegates to specialized agents."""

from __future__ import annotations

import logging
import re
from typing import Tuple

from app.agents.base import AgentContext, BaseAgent
from app.agents.registry import AgentRegistry, create_default_registry
from app.voice.providers.base import ChatMessage, LLMProvider

logger = logging.getLogger("nova.agents.router")


class AgentRouter:
    """Classifies user intent and routes incoming requests to the optimal agent."""

    def __init__(
        self,
        registry: AgentRegistry | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self.registry = registry or create_default_registry()
        self.llm = llm

    def _build_classification_prompt(self) -> str:
        agent_descriptions = []
        for agent in self.registry.list_agents():
            agent_descriptions.append(f"- {agent.name}: {agent.description}")

        agents_bullet_list = "\n".join(agent_descriptions)
        default_name = self.registry.get_default().name

        return (
            "You are a lightweight intent classifier for NOVA voice assistant.\n"
            "Analyze the user's input and choose the best agent to handle it.\n\n"
            "Available agents:\n"
            f"{agents_bullet_list}\n\n"
            f"Rules:\n"
            f"1. Reply with ONLY the exact agent name (e.g., '{default_name}').\n"
            f"2. Do not explain your choice. Output nothing else.\n"
            f"3. If the request is a greeting, general chat, or ambiguous, choose '{default_name}'."
        )

    def _sanitize_agent_name(self, raw_output: str) -> str:
        """Extract a clean identifier from the LLM output."""
        cleaned = raw_output.strip().lower()
        match = re.search(r"\b([a-z0-9_-]+)\b", cleaned)
        if match:
            return match.group(1)
        return cleaned

    async def route(
        self,
        user_input: str,
        context: AgentContext | None = None,
        llm: LLMProvider | None = None,
    ) -> Tuple[BaseAgent, str]:
        """Classify user intent and return the selected agent along with the routing reason."""
        active_llm = llm or self.llm
        default_agent = self.registry.get_default()

        clean_input = user_input.strip()
        if not clean_input:
            logger.info("empty input routed to default agent '%s'", default_agent.name)
            return default_agent, "empty input"

        if active_llm is None:
            logger.info("no LLM provider configured; using default agent '%s'", default_agent.name)
            return default_agent, "no router llm provided"

        # Build prompt using registered agents dynamically
        system_prompt = self._build_classification_prompt()
        prompt_messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=f"Request: {clean_input}"),
        ]

        try:
            raw_classification = await active_llm.generate_response(
                prompt_messages,
                temperature=0.0,
                max_tokens=15,
            )
            candidate_name = self._sanitize_agent_name(raw_classification)
            selected_agent = self.registry.get(candidate_name)

            if selected_agent is not None:
                logger.info(
                    "successfully routed '%s' to agent '%s' (%s)",
                    clean_input[:30],
                    selected_agent.name,
                    selected_agent.display_name,
                )
                return selected_agent, f"classified as {selected_agent.name}"

            logger.info(
                "unrecognized agent '%s' from LLM classification '%s'; falling back to default agent '%s'",
                candidate_name,
                raw_classification.strip(),
                default_agent.name,
            )
            return default_agent, f"unrecognized classification '{candidate_name}'"

        except Exception as exc:
            logger.warning(
                "intent classification failed (%s); falling back to default agent '%s'",
                exc,
                default_agent.name,
            )
            return default_agent, f"classification error: {exc}"
