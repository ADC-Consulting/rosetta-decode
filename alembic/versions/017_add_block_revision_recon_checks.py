"""Add recon_checks column to block_revisions.

Revision ID: 017
Revises: 016
Create Date: 2026-05-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add recon_checks JSON column to block_revisions."""
    op.add_column("block_revisions", sa.Column("recon_checks", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop recon_checks column from block_revisions."""
    op.drop_column("block_revisions", "recon_checks")
