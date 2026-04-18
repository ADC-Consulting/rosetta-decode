"""Add llm_model column to jobs table.

Revision ID: 002
Revises: 001
Create Date: 2026-04-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable llm_model column to jobs."""
    op.add_column("jobs", sa.Column("llm_model", sa.Text, nullable=True))


def downgrade() -> None:
    """Remove llm_model column from jobs."""
    op.drop_column("jobs", "llm_model")
