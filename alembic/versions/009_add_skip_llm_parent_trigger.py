"""Add skip_llm, parent_job_id and trigger columns to jobs table.

Revision ID: 009
Revises: 008
Create Date: 2026-04-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add skip_llm, parent_job_id, and trigger columns to jobs table."""
    op.add_column(
        "jobs",
        sa.Column(
            "skip_llm",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("parent_job_id", sa.VARCHAR(36), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "trigger",
            sa.VARCHAR(32),
            nullable=False,
            server_default=sa.text("'agent'"),
        ),
    )


def downgrade() -> None:
    """Drop skip_llm, parent_job_id, and trigger columns from jobs table."""
    op.drop_column("jobs", "trigger")
    op.drop_column("jobs", "parent_job_id")
    op.drop_column("jobs", "skip_llm")
