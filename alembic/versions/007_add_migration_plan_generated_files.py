"""Add migration_plan and generated_files columns to jobs table.

Revision ID: 007
Revises: 006
Create Date: 2026-04-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add migration_plan and generated_files JSON columns."""
    op.add_column("jobs", sa.Column("migration_plan", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("generated_files", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop migration_plan and generated_files JSON columns."""
    op.drop_column("jobs", "migration_plan")
    op.drop_column("jobs", "generated_files")
