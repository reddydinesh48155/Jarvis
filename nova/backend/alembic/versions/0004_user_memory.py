"""Create user memory tables.

Revision ID: 0004
Revises: 0003_rag_documents
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    op.create_table(
        "user_memories",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="general"),
        sa.Column("source_session_id", sa.String(100), nullable=True),
        sa.Column(
            "embedding",
            Vector(EMBEDDING_DIM) if Vector else sa.JSON(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "user_memory_settings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("memory_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_memory_settings")
    op.drop_table("user_memories")

