"""Add explain_sessions table for persistent chat sessions on the Explain page.

Revision ID: 012
Revises: 011
Create Date: 2026-04-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create explain_sessions table."""
    op.create_table(
        "explain_sessions",
        sa.Column("id", sa.VARCHAR(36), primary_key=True, nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("job_id", sa.VARCHAR(36), nullable=True),
        sa.Column("audience", sa.Text(), nullable=False, server_default="tech"),
        sa.Column("messages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("context_files", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_explain_sessions_created_at", "explain_sessions", ["created_at"])


def downgrade() -> None:
    """Drop explain_sessions table."""
    op.drop_index("ix_explain_sessions_created_at", table_name="explain_sessions")
    op.drop_table("explain_sessions")
