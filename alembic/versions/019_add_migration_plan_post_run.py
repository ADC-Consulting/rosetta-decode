"""Add migration_plan_post_run column to jobs.

Revision ID: 019
Revises: 018
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add migration_plan_post_run nullable JSON column to jobs."""
    op.add_column("jobs", sa.Column("migration_plan_post_run", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop migration_plan_post_run column from jobs."""
    op.drop_column("jobs", "migration_plan_post_run")
