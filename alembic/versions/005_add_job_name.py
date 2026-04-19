"""Add name column to jobs table.

Revision ID: 005
Revises: 004
Create Date: 2026-04-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable name TEXT column to jobs."""
    op.add_column("jobs", sa.Column("name", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove name column from jobs."""
    op.drop_column("jobs", "name")
