"""Create jobs table.

Revision ID: 001
Revises:
Create Date: 2026-04-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the jobs table."""
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("input_hash", sa.Text, nullable=False),
        sa.Column("files", sa.JSON, nullable=False),
        sa.Column("python_code", sa.Text, nullable=True),
        sa.Column("report", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name="jobs_status_check",
        ),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])


def downgrade() -> None:
    """Drop the jobs table."""
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")
