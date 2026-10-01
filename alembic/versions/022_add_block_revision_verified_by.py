"""Add verified_by column to block_revisions.

Revision ID: 022
Revises: 021
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add verified_by nullable Text column to block_revisions."""
    op.add_column("block_revisions", sa.Column("verified_by", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop verified_by column from block_revisions."""
    op.drop_column("block_revisions", "verified_by")
