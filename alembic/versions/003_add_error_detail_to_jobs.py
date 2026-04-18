"""Add error_detail column to jobs table.

Revision ID: 003
Revises: 002
Create Date: 2026-04-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable error_detail JSON column to jobs."""
    op.add_column("jobs", sa.Column("error_detail", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove error_detail column from jobs."""
    op.drop_column("jobs", "error_detail")
