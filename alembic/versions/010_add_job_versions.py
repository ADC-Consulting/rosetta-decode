"""Add job_versions table for per-tab version history.

Revision ID: 010
Revises: 009
Create Date: 2026-04-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create job_versions table with index on (job_id, tab)."""
    op.create_table(
        "job_versions",
        sa.Column("id", sa.VARCHAR(36), primary_key=True, nullable=False),
        sa.Column(
            "job_id",
            sa.VARCHAR(36),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tab",
            sa.VARCHAR(16),
            sa.CheckConstraint("tab IN ('plan', 'editor', 'report')", name="ck_job_versions_tab"),
            nullable=False,
        ),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column(
            "trigger",
            sa.VARCHAR(32),
            nullable=False,
            server_default=sa.text("'human-save'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_job_versions_job_id_tab",
        "job_versions",
        ["job_id", "tab"],
    )


def downgrade() -> None:
    """Drop job_versions table and its index."""
    op.drop_index("ix_job_versions_job_id_tab", table_name="job_versions")
    op.drop_table("job_versions")
