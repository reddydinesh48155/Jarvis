from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - dependency is declared in pyproject
    Vector = None  # type: ignore[assignment,misc]


RAG_EMBEDDING_DIMENSION = 768


class EmbeddingVector(TypeDecorator[list[float]]):
    """Use pgvector in PostgreSQL and JSON for the SQLite test database."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            if Vector is None:
                raise RuntimeError("pgvector is required for PostgreSQL RAG storage")
            return dialect.type_descriptor(Vector(RAG_EMBEDDING_DIMENSION))
        return dialect.type_descriptor(JSON())


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    """A hashed, server-tracked refresh token that can be revoked on logout."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class AuditLog(Base):
    """Audit log entry tracking tool execution attempts and outcomes."""

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    permission_level: Mapped[str] = mapped_column(String(20), nullable=False)
    input_params: Mapped[str] = mapped_column(String, nullable=False)
    output_result: Mapped[str | None] = mapped_column(String, nullable=True)
    success: Mapped[bool] = mapped_column(nullable=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    requires_confirmation: Mapped[bool] = mapped_column(default=False, nullable=False)
    confirmed: Mapped[bool] = mapped_column(default=False, nullable=False)
    execution_time_ms: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KnowledgeDocument(Base):
    """An uploaded document owned by exactly one authenticated user."""

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="indexed")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    """A searchable, embedded passage belonging to a knowledge document."""

    __tablename__ = "document_chunks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding: Mapped[list[float]] = mapped_column(EmbeddingVector(), nullable=False)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class UserMemory(Base):
    """A long-term memory entry owned by exactly one user, stored with a vector embedding."""

    __tablename__ = "user_memories"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="general"
    )
    source_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding: Mapped[list[float]] = mapped_column(EmbeddingVector(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UserMemorySettings(Base):
    """Per-user memory system preferences."""

    __tablename__ = "user_memory_settings"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    memory_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
