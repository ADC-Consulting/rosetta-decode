"""Add block_revisions table for per-block translation history.

Revision ID: 011
Revises: 010
Create Date: 2026-04-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create block_revisions table with index on (job_id, block_id)."""
    op.create_table(
        "block_revisions",
        sa.Column("id", sa.VARCHAR(36), primary_key=True, nullable=False),
        sa.Column(
            "job_id",
            sa.VARCHAR(36),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("block_id", sa.Text(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("python_code", sa.Text(), nullable=False),
        sa.Column("strategy", sa.VARCHAR(32), nullable=False),
        sa.Column(
            "confidence",
            sa.VARCHAR(16),
            nullable=False,
            server_default=sa.text("'high'"),
        ),
        sa.Column(
            "uncertainty_notes",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("reconciliation_status", sa.VARCHAR(8), nullable=True),
        sa.Column(
            "trigger",
            sa.VARCHAR(32),
            nullable=False,
            server_default=sa.text("'agent'"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("hint", sa.Text(), nullable=True),
        sa.Column("diff_vs_previous", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_block_revisions_job_id_block_id",
        "block_revisions",
        ["job_id", "block_id"],
    )


def downgrade() -> None:
    """Drop block_revisions table and its index."""
    op.drop_index("ix_block_revisions_job_id_block_id", table_name="block_revisions")
    op.drop_table("block_revisions")
