"""Add under_review to jobs status check constraint.

Revision ID: 015
Revises: 014
Create Date: 2026-04-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Expand status constraint to include under_review."""
    op.drop_constraint("jobs_status_check", "jobs", type_="check")
    op.create_check_constraint(
        "jobs_status_check",
        "jobs",
        "status IN ('queued', 'running', 'done', 'failed', 'proposed', 'accepted', 'under_review')",
    )


def downgrade() -> None:
    """Remove under_review from status constraint."""
    op.execute("UPDATE jobs SET status = 'failed' WHERE status = 'under_review'")
    op.drop_constraint("jobs_status_check", "jobs", type_="check")
    op.create_check_constraint(
        "jobs_status_check",
        "jobs",
        "status IN ('queued', 'running', 'done', 'failed', 'proposed', 'accepted')",
    )
