"""Add durable audit records for secure tool execution."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_tool_audit_logs"
down_revision: Union[str, None] = "0001_initial_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=True),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("permission_level", sa.String(length=20), nullable=False),
        sa.Column("input_params", sa.String(), nullable=False),
        sa.Column("output_result", sa.String(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("execution_time_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_tool_name"), "audit_logs", ["tool_name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_tool_name"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_user_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
