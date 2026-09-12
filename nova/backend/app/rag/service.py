"""Async document indexing, user-scoped retrieval, and document management."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db import session as db_session
from app.db.models import KnowledgeChunk, KnowledgeDocument
from app.rag.chunking import TextChunk, chunk_sections
from app.rag.embeddings import EmbeddingProvider, get_default_embedding_provider
from app.rag.extraction import extract_document


TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_'-]{1,}", re.IGNORECASE)
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "i",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "what",
    "when", "where", "which", "who", "with", "you", "your",
}


@dataclass(frozen=True)
class DocumentSummary:
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str
    uploaded_at: datetime
    chunk_count: int


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: UUID
    document_id: UUID
    filename: str
    page_number: int | None
    section: str | None
    content: str
    score: float
    vector_score: float
    keyword_score: float

    @property
    def location(self) -> str:
        if self.page_number is not None:
            return f"page {self.page_number}"
        return self.section or "document"

    @property
    def citation(self) -> str:
        return f"{self.filename} ({self.location})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "filename": self.filename,
            "page_number": self.page_number,
            "section": self.section,
            "location": self.location,
            "content": self.content,
            "score": round(self.score, 4),
            "citation": self.citation,
        }


def _as_uuid(user_id: UUID | str) -> UUID:
    if isinstance(user_id, UUID):
        return user_id
    return UUID(str(user_id))


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if token.lower() not in STOP_WORDS
    }


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)))


def _keyword_score(query: str, content: str, filename: str, section: str | None) -> float:
    query_terms = _tokens(query)
    if not query_terms:
        return 0.0
    content_terms = _tokens(content)
    overlap = len(query_terms & content_terms) / len(query_terms)
    metadata_terms = _tokens(f"{filename} {section or ''}")
    metadata_bonus = 0.10 if query_terms & metadata_terms else 0.0
    return min(1.0, overlap + metadata_bonus)


def _heuristic_rerank(query: str, hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Apply a cheap phrase/source boost without loading a cross-encoder."""
    normalized_query = " ".join(query.lower().split())
    ranked: list[tuple[float, RetrievalHit]] = []
    for hit in hits:
        normalized_content = " ".join(hit.content.lower().split())
        phrase_bonus = 0.05 if normalized_query and normalized_query in normalized_content else 0.0
        ranked.append((hit.score + phrase_bonus, hit))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [hit for _, hit in ranked]


class RAGService:
    """Own the complete Part 6 lifecycle while keeping DB/provider injection explicit."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        min_relevance: float | None = None,
        candidate_limit: int | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider or get_default_embedding_provider()
        if self.embedding_provider.dimension != settings.rag_embedding_dimension:
            raise ValueError(
                "embedding provider dimension must match RAG_EMBEDDING_DIMENSION "
                f"({settings.rag_embedding_dimension})"
            )
        self.session_factory = session_factory
        self.chunk_size = chunk_size or settings.rag_chunk_size
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.rag_chunk_overlap
        self.min_relevance = min_relevance if min_relevance is not None else settings.rag_min_relevance
        self.candidate_limit = candidate_limit or settings.rag_candidate_limit

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        return self.session_factory or db_session.SessionLocal

    async def index_document(
        self,
        db: AsyncSession,
        user_id: UUID | str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> DocumentSummary:
        owner_id = _as_uuid(user_id)
        safe_filename = PurePath(filename).name[:255] or "uploaded-document"
        sections = extract_document(safe_filename, data)
        chunks = chunk_sections(sections, self.chunk_size, self.chunk_overlap)
        if not chunks:
            raise ValueError("The document contains no extractable text")

        vectors = await self.embedding_provider.embed([chunk.text for chunk in chunks])
        document = KnowledgeDocument(
            user_id=owner_id,
            filename=safe_filename,
            content_type=content_type or "application/octet-stream",
            size_bytes=len(data),
            status="indexed",
        )
        db.add(document)
        await db.flush()
        db.add_all(
            [
                KnowledgeChunk(
                    document_id=document.id,
                    user_id=owner_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.text,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    embedding=vector,
                )
                for chunk, vector in zip(chunks, vectors)
            ]
        )
        await db.commit()
        await db.refresh(document)
        return DocumentSummary(
            id=document.id,
            filename=document.filename,
            content_type=document.content_type,
            size_bytes=document.size_bytes,
            status=document.status,
            uploaded_at=document.uploaded_at,
            chunk_count=len(chunks),
        )

    async def list_documents(self, db: AsyncSession, user_id: UUID | str) -> list[DocumentSummary]:
        owner_id = _as_uuid(user_id)
        statement = (
            select(KnowledgeDocument, func.count(KnowledgeChunk.id))
            .outerjoin(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeDocument.user_id == owner_id)
            .group_by(KnowledgeDocument.id)
            .order_by(KnowledgeDocument.uploaded_at.desc())
        )
        rows = (await db.execute(statement)).all()
        return [
            DocumentSummary(
                id=document.id,
                filename=document.filename,
                content_type=document.content_type,
                size_bytes=document.size_bytes,
                status=document.status,
                uploaded_at=document.uploaded_at,
                chunk_count=int(chunk_count),
            )
            for document, chunk_count in rows
        ]

    async def delete_document(self, db: AsyncSession, user_id: UUID | str, document_id: UUID) -> bool:
        owner_id = _as_uuid(user_id)
        document = await db.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.user_id == owner_id,
            )
        )
        if document is None:
            return False
        await db.delete(document)
        await db.commit()
        return True

    async def search(
        self,
        db: AsyncSession,
        user_id: UUID | str,
        query: str,
        top_k: int = 4,
        filename: str | None = None,
        document_id: UUID | None = None,
    ) -> list[RetrievalHit]:
        owner_id = _as_uuid(user_id)
        clean_query = query.strip()
        if not clean_query:
            return []
        top_k = max(1, min(top_k, 20))
        query_vector = await self.embedding_provider.embed_one(clean_query)

        statement = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(
                KnowledgeDocument.user_id == owner_id,
                KnowledgeChunk.user_id == owner_id,
            )
        )
        if filename:
            statement = statement.where(KnowledgeDocument.filename.ilike(f"%{filename.strip()}%"))
        if document_id is not None:
            statement = statement.where(KnowledgeDocument.id == document_id)

        bind = db.get_bind()
        vector_distance = None
        if bind.dialect.name == "postgresql":
            vector_distance = KnowledgeChunk.embedding.op("<=>")(query_vector).label("vector_distance")
            statement = statement.add_columns(vector_distance).order_by(vector_distance)
        statement = statement.limit(self.candidate_limit)
        rows = (await db.execute(statement)).all()

        hits: list[RetrievalHit] = []
        for row in rows:
            chunk = row[0]
            document = row[1]
            distance = float(row[2]) if vector_distance is not None else None
            vector_score = (1.0 - distance) if distance is not None else _cosine_similarity(chunk.embedding, query_vector)
            vector_score = max(0.0, min(1.0, vector_score))
            keyword_score = _keyword_score(clean_query, chunk.content, document.filename, chunk.section)
            # Hybrid ranking favors semantic similarity but gives an explicit
            # keyword match enough weight to keep local fallback retrieval useful.
            score = (0.65 * vector_score) + (0.35 * keyword_score)
            if score < self.min_relevance:
                continue
            hits.append(
                RetrievalHit(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    filename=document.filename,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    content=chunk.content,
                    score=score,
                    vector_score=vector_score,
                    keyword_score=keyword_score,
                )
            )
        return _heuristic_rerank(clean_query, hits)[:top_k]

    async def search_for_user(
        self,
        user_id: UUID | str,
        query: str,
        top_k: int = 4,
        filename: str | None = None,
        document_id: UUID | None = None,
    ) -> list[RetrievalHit]:
        async with self._factory()() as db:
            return await self.search(db, user_id, query, top_k, filename, document_id)
