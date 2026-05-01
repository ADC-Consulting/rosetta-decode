"""Add job_traces table and cancellation_requested column to jobs.

Revision ID: 016
Revises: 015
Create Date: 2026-05-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add cancellation_requested to jobs and create job_traces table."""
    op.add_column(
        "jobs",
        sa.Column(
            "cancellation_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "job_traces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_job_traces_job_id", "job_traces", ["job_id"])
    op.create_index("ix_job_traces_job_id_id", "job_traces", ["job_id", "id"])


def downgrade() -> None:
    """Drop job_traces table and cancellation_requested column."""
    op.drop_index("ix_job_traces_job_id_id", table_name="job_traces")
    op.drop_index("ix_job_traces_job_id", table_name="job_traces")
    op.drop_table("job_traces")
    op.drop_column("jobs", "cancellation_requested")
