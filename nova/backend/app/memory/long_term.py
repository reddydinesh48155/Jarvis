"""Long-term memory: persistent, user-scoped facts with vector embeddings.

Stores confirmed facts in PostgreSQL (user_memories table) with pgvector
embeddings for semantic retrieval. All queries are strictly filtered by
user_id to enforce per-user isolation — the same pattern used for RAG
document chunks in Part 6.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db import session as db_session
from app.db.models import UserMemory, UserMemorySettings
from app.rag.embeddings import EmbeddingProvider, get_default_embedding_provider

logger = logging.getLogger("nova.memory.long_term")


@dataclass(frozen=True)
class MemoryHit:
    """A single memory search result."""

    memory_id: UUID
    content: str
    category: str
    score: float
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.memory_id),
            "content": self.content,
            "category": self.category,
            "score": round(self.score, 4),
            "created_at": self.created_at.isoformat(),
        }


def _as_uuid(user_id: UUID | str) -> UUID:
    if isinstance(user_id, UUID):
        return user_id
    return UUID(str(user_id))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """Pure-Python cosine similarity fallback for SQLite tests."""
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    left_norm = math.sqrt(sum(v * v for v in left))
    right_norm = math.sqrt(sum(v * v for v in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)))


class LongTermMemory:
    """Persistent memory store with semantic search capabilities."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider or get_default_embedding_provider()
        self.session_factory = session_factory

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        return self.session_factory or db_session.SessionLocal

    async def store(
        self,
        db: AsyncSession,
        user_id: UUID | str,
        content: str,
        category: str = "general",
        session_id: str | None = None,
    ) -> UserMemory:
        """Embed and persist a confirmed fact to the user_memories table."""
        owner_id = _as_uuid(user_id)
        vector = await self.embedding_provider.embed_one(content)

        memory = UserMemory(
            user_id=owner_id,
            content=content,
            category=category,
            source_session_id=session_id,
            embedding=vector,
        )
        db.add(memory)
        await db.commit()
        await db.refresh(memory)
        logger.info("stored long-term memory %s for user %s", memory.id, owner_id)
        return memory

    async def search(
        self,
        db: AsyncSession,
        user_id: UUID | str,
        query: str,
        top_k: int = 5,
        min_relevance: float | None = None,
    ) -> list[MemoryHit]:
        """Semantic search over the user's long-term memories."""
        owner_id = _as_uuid(user_id)
        threshold = min_relevance if min_relevance is not None else settings.memory_relevance_threshold

        query_vector = await self.embedding_provider.embed_one(query)

        # Build query — use pgvector operator if available, else fallback
        statement = select(UserMemory).where(UserMemory.user_id == owner_id)

        dialect_name = db.bind.dialect.name if db.bind else "sqlite"

        if dialect_name == "postgresql":
            # Use pgvector cosine distance operator
            vector_distance = UserMemory.embedding.op("<=>")(query_vector).label("vector_distance")
            statement = (
                select(UserMemory)
                .add_columns(vector_distance)
                .where(UserMemory.user_id == owner_id)
                .order_by(vector_distance)
                .limit(top_k * 3)  # Over-fetch then filter by threshold
            )
            result = await db.execute(statement)
            rows = result.all()
            hits: list[MemoryHit] = []
            for row in rows:
                memory = row[0]
                distance = row[1]
                score = 1.0 - distance
                if score >= threshold:
                    hits.append(MemoryHit(
                        memory_id=memory.id,
                        content=memory.content,
                        category=memory.category,
                        score=score,
                        created_at=memory.created_at,
                    ))
            hits = hits[:top_k]
        else:
            # SQLite fallback — fetch all user memories, compute similarity in Python
            result = await db.execute(statement)
            all_memories = result.scalars().all()
            scored: list[tuple[float, UserMemory]] = []
            for memory in all_memories:
                score = _cosine_similarity(memory.embedding, query_vector)
                if score >= threshold:
                    scored.append((score, memory))
            scored.sort(key=lambda x: x[0], reverse=True)
            hits = [
                MemoryHit(
                    memory_id=mem.id,
                    content=mem.content,
                    category=mem.category,
                    score=sc,
                    created_at=mem.created_at,
                )
                for sc, mem in scored[:top_k]
            ]

        # Update last_accessed_at for returned memories
        if hits:
            memory_ids = [h.memory_id for h in hits]
            await db.execute(
                update(UserMemory)
                .where(UserMemory.id.in_(memory_ids))
                .values(last_accessed_at=datetime.now(timezone.utc))
            )
            await db.commit()

        return hits

    async def list_all(
        self,
        db: AsyncSession,
        user_id: UUID | str,
    ) -> list[UserMemory]:
        """Return all long-term memories for the user (most recent first)."""
        owner_id = _as_uuid(user_id)
        result = await db.execute(
            select(UserMemory)
            .where(UserMemory.user_id == owner_id)
            .order_by(UserMemory.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_one(
        self,
        db: AsyncSession,
        user_id: UUID | str,
        memory_id: UUID | str,
    ) -> bool:
        """Delete a specific memory. Returns True if found and deleted."""
        owner_id = _as_uuid(user_id)
        mid = _as_uuid(memory_id) if isinstance(memory_id, str) else memory_id
        result = await db.execute(
            delete(UserMemory).where(
                UserMemory.id == mid,
                UserMemory.user_id == owner_id,
            )
        )
        await db.commit()
        return result.rowcount > 0  # type: ignore[union-attr]

    async def delete_all(
        self,
        db: AsyncSession,
        user_id: UUID | str,
    ) -> int:
        """Delete all memories for the user. Returns count deleted."""
        owner_id = _as_uuid(user_id)
        result = await db.execute(
            delete(UserMemory).where(UserMemory.user_id == owner_id)
        )
        await db.commit()
        return result.rowcount  # type: ignore[union-attr]

    # --- Memory Settings ---

    async def get_settings(
        self,
        db: AsyncSession,
        user_id: UUID | str,
    ) -> bool:
        """Return whether memory is enabled for this user. Defaults to True."""
        owner_id = _as_uuid(user_id)
        result = await db.execute(
            select(UserMemorySettings).where(UserMemorySettings.user_id == owner_id)
        )
        row = result.scalar_one_or_none()
        return row.memory_enabled if row else True

    async def update_settings(
        self,
        db: AsyncSession,
        user_id: UUID | str,
        enabled: bool,
    ) -> UserMemorySettings:
        """Create or update the user's memory settings."""
        owner_id = _as_uuid(user_id)
        result = await db.execute(
            select(UserMemorySettings).where(UserMemorySettings.user_id == owner_id)
        )
        row = result.scalar_one_or_none()
        if row:
            row.memory_enabled = enabled
            row.updated_at = datetime.now(timezone.utc)
        else:
            row = UserMemorySettings(
                user_id=owner_id,
                memory_enabled=enabled,
            )
            db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

