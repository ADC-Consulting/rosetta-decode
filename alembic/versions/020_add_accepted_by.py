"""Add accepted_by column to jobs.

Revision ID: 020
Revises: 019
Create Date: 2026-06-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add accepted_by nullable Text column to jobs."""
    op.add_column("jobs", sa.Column("accepted_by", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop accepted_by column from jobs."""
    op.drop_column("jobs", "accepted_by")
