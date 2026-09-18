"""Session memory: facts extracted from the current session, pending user confirmation.

Facts are held in-process and only promoted to long-term storage after the user
explicitly agrees. If the session ends without promotion, unpromoted facts are
discarded — this is intentional for privacy.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.voice.providers.base import ChatMessage, LLMProvider

logger = logging.getLogger("nova.memory.session")


FACT_EXTRACTION_PROMPT = """\
You are a memory extraction module. Analyze the following conversation exchange and
determine whether the user revealed any personal facts, preferences, or information
they would likely want the assistant to recall in future conversations.

**Extract a fact when the user:**
- Says "remember that...", "keep in mind...", "don't forget that..."
- States a personal preference ("I prefer...", "I always...", "I like...")
- Shares biographical information (name, job, location, relationships)
- Mentions recurring patterns ("Every Monday I...", "I usually...")

**Do NOT extract:**
- Transient task requests ("set a timer", "search for X")
- Questions the user asks
- Generic conversational filler
- Anything the assistant said (only extract USER-side facts)

Respond ONLY with a JSON array of extracted facts. Each fact should have:
- "content": a concise first-person restatement of the fact
- "category": one of "preference", "personal", "habit", "instruction", "general"

If there are no extractable facts, respond with an empty array: []

Example output:
[{{"content": "I prefer dark mode for all applications", "category": "preference"}}]

USER said: {user_input}
ASSISTANT said: {assistant_response}

Extracted facts (JSON array only):"""


@dataclass
class SessionFact:
    """A single extracted fact pending user confirmation."""

    id: str = field(default_factory=lambda: str(uuid4()))
    content: str = ""
    category: str = "general"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    promoted: bool = False


class SessionMemory:
    """In-session fact buffer with LLM-based extraction."""

    def __init__(self) -> None:
        self._facts: list[SessionFact] = []
        self._pending_confirmation: SessionFact | None = None

    @property
    def facts(self) -> list[SessionFact]:
        return list(self._facts)

    @property
    def pending_confirmation(self) -> SessionFact | None:
        return self._pending_confirmation

    async def extract_facts(
        self,
        user_input: str,
        assistant_response: str,
        llm: LLMProvider,
    ) -> list[SessionFact]:
        """Use a focused LLM call to detect memorable facts from the conversation turn.

        Returns the newly-extracted facts (may be empty).
        """
        prompt = FACT_EXTRACTION_PROMPT.format(
            user_input=user_input,
            assistant_response=assistant_response,
        )
        messages = [ChatMessage(role="user", content=prompt)]
        try:
            raw = await llm.generate_response(messages)
            parsed = json.loads(raw.strip())
        except (json.JSONDecodeError, Exception) as exc:
            logger.debug("fact extraction returned non-JSON or failed: %s", exc)
            return []

        if not isinstance(parsed, list):
            return []

        extracted: list[SessionFact] = []
        for item in parsed:
            if not isinstance(item, dict) or "content" not in item:
                continue
            fact = SessionFact(
                content=str(item["content"]),
                category=str(item.get("category", "general")),
            )
            self._facts.append(fact)
            extracted.append(fact)

        return extracted

    def propose_for_confirmation(self, fact: SessionFact) -> str:
        """Set a fact as pending confirmation and return the confirmation prompt text."""
        self._pending_confirmation = fact
        return f'Should I remember that "{fact.content}"?'

    def confirm_pending(self) -> SessionFact | None:
        """Mark the pending fact as confirmed and return it. Returns None if nothing pending."""
        if self._pending_confirmation is None:
            return None
        fact = self._pending_confirmation
        fact.promoted = True
        self._pending_confirmation = None
        return fact

    def dismiss_pending(self) -> None:
        """Dismiss the pending confirmation without promoting."""
        self._pending_confirmation = None

    def get_fact_by_id(self, fact_id: str) -> SessionFact | None:
        return next((f for f in self._facts if f.id == fact_id), None)

    def clear(self) -> None:
        """Discard all session facts and pending confirmations."""
        self._facts.clear()
        self._pending_confirmation = None

