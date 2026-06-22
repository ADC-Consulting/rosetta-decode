"""Add mode and scoping_report columns to jobs.

Revision ID: 021
Revises: 020
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add mode (default 'migrate') and nullable scoping_report JSON columns to jobs."""
    op.add_column(
        "jobs",
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="migrate"),
    )
    op.add_column("jobs", sa.Column("scoping_report", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop scoping_report and mode columns from jobs."""
    op.drop_column("jobs", "scoping_report")
    op.drop_column("jobs", "mode")
