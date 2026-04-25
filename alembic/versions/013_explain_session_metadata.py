"""Add title and file_name to explain_sessions; backfill mode upload -> sas_general.

Revision ID: 013
Revises: 012
Create Date: 2026-04-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add title and file_name columns; migrate mode 'upload' -> 'sas_general'."""
    op.add_column("explain_sessions", sa.Column("title", sa.Text(), nullable=True))
    op.add_column("explain_sessions", sa.Column("file_name", sa.Text(), nullable=True))
    op.execute("UPDATE explain_sessions SET mode='sas_general' WHERE mode='upload'")


def downgrade() -> None:
    """Remove title and file_name columns; revert mode 'sas_general' -> 'upload'."""
    op.drop_column("explain_sessions", "title")
    op.drop_column("explain_sessions", "file_name")
    op.execute("UPDATE explain_sessions SET mode='upload' WHERE mode='sas_general'")
