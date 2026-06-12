"""Add token_usage column to jobs.

Revision ID: 018
Revises: 017
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add token_usage nullable JSON column to jobs."""
    op.add_column("jobs", sa.Column("token_usage", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop token_usage column from jobs."""
    op.drop_column("jobs", "token_usage")
