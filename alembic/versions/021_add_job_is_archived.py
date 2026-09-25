"""Add is_archived column to jobs.

Revision ID: 021
Revises: 020
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add is_archived NOT NULL Boolean column to jobs, defaulting to false."""
    op.add_column(
        "jobs",
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    """Drop is_archived column from jobs."""
    op.drop_column("jobs", "is_archived")
