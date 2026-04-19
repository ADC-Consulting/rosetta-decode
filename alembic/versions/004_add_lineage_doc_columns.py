"""Add lineage and doc columns to jobs table.

Revision ID: 004
Revises: 003
Create Date: 2026-04-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable lineage JSON and doc Text columns to jobs."""
    op.add_column("jobs", sa.Column("lineage", postgresql.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("doc", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove lineage and doc columns from jobs."""
    op.drop_column("jobs", "doc")
    op.drop_column("jobs", "lineage")
