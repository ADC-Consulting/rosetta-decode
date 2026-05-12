"""Add notes and assessment columns to jobs table.

Revision ID: 018
Revises: 017
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add notes TEXT and assessment JSON columns to jobs."""
    op.add_column("jobs", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("assessment", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop notes and assessment columns from jobs."""
    op.drop_column("jobs", "assessment")
    op.drop_column("jobs", "notes")
