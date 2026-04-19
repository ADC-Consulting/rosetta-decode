"""Add user_overrides and accepted_at columns; migrate done→accepted in existing rows.

Revision ID: 008
Revises: 007
Create Date: 2026-04-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Expand status constraint, migrate done→proposed, add user_overrides and accepted_at."""
    # Expand the status check constraint to include proposed/accepted
    op.drop_constraint("jobs_status_check", "jobs", type_="check")
    op.create_check_constraint(
        "jobs_status_check",
        "jobs",
        "status IN ('queued', 'running', 'done', 'failed', 'proposed', 'accepted')",
    )
    # Migrate legacy done rows to proposed (pre-review terminal state)
    op.execute("UPDATE jobs SET status = 'proposed' WHERE status = 'done'")
    op.add_column("jobs", sa.Column("user_overrides", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Reverse status constraint expansion and drop user_overrides/accepted_at columns."""
    op.drop_column("jobs", "accepted_at")
    op.drop_column("jobs", "user_overrides")
    op.execute("UPDATE jobs SET status = 'done' WHERE status IN ('proposed', 'accepted')")
    op.drop_constraint("jobs_status_check", "jobs", type_="check")
    op.create_check_constraint(
        "jobs_status_check",
        "jobs",
        "status IN ('queued', 'running', 'done', 'failed')",
    )
