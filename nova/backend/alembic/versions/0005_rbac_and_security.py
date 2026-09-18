"""Add role column to users table for RBAC.

Revision ID: 0005
"""

revision = "0005"
down_revision = "0004"

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="user"))


def downgrade() -> None:
    op.drop_column("users", "role")

