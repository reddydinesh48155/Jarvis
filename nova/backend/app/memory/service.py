"""MemoryService: orchestrator combining all three memory layers.

This service coordinates short-term (in-process), session (fact extraction),
and long-term (persistent vector store) memory layers. It enforces the
consent flow: facts are only persisted to long-term storage after the user
explicitly confirms.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.memory.long_term import LongTermMemory, MemoryHit
from app.memory.session_memory import SessionFact, SessionMemory
from app.memory.short_term import ShortTermMemory
from app.rag.embeddings import EmbeddingProvider, get_default_embedding_provider
from app.voice.providers.base import LLMProvider

logger = logging.getLogger("nova.memory.service")


@dataclass
class ProposedFact:
    """A fact detected by the session memory layer, awaiting user confirmation."""

    fact_id: str
    content: str
    category: str
    confirmation_prompt: str


class MemoryService:
    """Unified memory orchestrator for the voice pipeline.

    Usage in the voice pipeline:
    1. At start of session, create a MemoryService instance
    2. Before agent reasoning, call retrieve_relevant_memories() to get context
    3. After agent response, call detect_and_propose_facts() to find memorable info
    4. On user confirmation, call confirm_and_store() to persist
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider or get_default_embedding_provider()
        self.short_term = ShortTermMemory()
        self.session = SessionMemory()
        self.long_term = LongTermMemory(
            embedding_provider=self._embedding_provider,
            session_factory=session_factory,
        )

    async def is_memory_enabled(self, db: AsyncSession, user_id: UUID | str) -> bool:
        """Check whether memory is enabled for this user."""
        return await self.long_term.get_settings(db, user_id)

    async def retrieve_relevant_memories(
        self,
        db: AsyncSession,
        user_id: UUID | str,
        query: str,
        top_k: int = 5,
    ) -> list[MemoryHit]:
        """Retrieve long-term memories relevant to the query.

        Returns empty list if memory is disabled for the user.
        """
        enabled = await self.is_memory_enabled(db, user_id)
        if not enabled:
            logger.debug("memory disabled for user %s — skipping retrieval", user_id)
            return []

        try:
            hits = await self.long_term.search(db, user_id, query, top_k=top_k)
            if hits:
                logger.info("recalled %d memories for user %s", len(hits), user_id)
            return hits
        except Exception as exc:
            logger.exception("memory retrieval failed for user %s: %s", user_id, exc)
            return []

    async def detect_and_propose_facts(
        self,
        user_input: str,
        assistant_response: str,
        llm: LLMProvider,
    ) -> list[ProposedFact]:
        """Detect memorable facts from the latest turn. Does NOT persist anything.

        Returns a list of proposed facts with confirmation prompts.
        The pipeline should present these to the user and only call
        confirm_and_store() on explicit approval.
        """
        if not settings.memory_fact_detection_enabled:
            return []

        extracted = await self.session.extract_facts(
            user_input=user_input,
            assistant_response=assistant_response,
            llm=llm,
        )
        proposals: list[ProposedFact] = []
        for fact in extracted:
            prompt = self.session.propose_for_confirmation(fact)
            proposals.append(ProposedFact(
                fact_id=fact.id,
                content=fact.content,
                category=fact.category,
                confirmation_prompt=prompt,
            ))
        return proposals

    async def confirm_and_store(
        self,
        db: AsyncSession,
        user_id: UUID | str,
        fact_content: str,
        category: str = "general",
        session_id: str | None = None,
    ) -> bool:
        """Persist a confirmed fact to long-term memory.

        Returns True if stored successfully, False if memory is disabled
        or the storage limit has been reached.
        """
        enabled = await self.is_memory_enabled(db, user_id)
        if not enabled:
            logger.info("memory disabled — not storing fact for user %s", user_id)
            return False

        # Check storage limit
        existing = await self.long_term.list_all(db, user_id)
        if len(existing) >= settings.memory_max_long_term_per_user:
            logger.warning(
                "user %s has reached the memory limit (%d)",
                user_id,
                settings.memory_max_long_term_per_user,
            )
            return False

        # Confirm the pending fact in session memory
        self.session.confirm_pending()

        await self.long_term.store(
            db=db,
            user_id=user_id,
            content=fact_content,
            category=category,
            session_id=session_id,
        )
        logger.info("confirmed and stored memory for user %s: %s", user_id, fact_content[:60])
        return True

    def format_memory_context(self, hits: list[MemoryHit]) -> str | None:
        """Format retrieved memories as a text block for injection into the agent prompt.

        Returns None if no memories to inject.
        """
        if not hits:
            return None
        lines = []
        for i, hit in enumerate(hits, 1):
            lines.append(f"- [{hit.category}] {hit.content}")
        return "\n".join(lines)

    def clear_session(self) -> None:
        """Clear short-term and session memory (called on session end)."""
        self.short_term.clear()
        self.session.clear()

