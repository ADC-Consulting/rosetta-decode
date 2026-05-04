"""Collapse 5-value strategy enum to 3 wire values.

Revision ID: 014
Revises: 013
Create Date: 2026-04-25

Normalises historic strategy values in block_revisions:
- 'translate' → 'translated'
- 'translate_with_review' / 'manual_ingestion' / 'skip' → 'translated_with_review'
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rewrite legacy strategy values to the 3-value canonical set."""
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE block_revisions SET strategy = 'translated' WHERE strategy = 'translate'")
    )
    conn.execute(
        sa.text(
            "UPDATE block_revisions"
            " SET strategy = 'translated_with_review'"
            " WHERE strategy IN ('translate_with_review', 'manual_ingestion', 'skip')"
        )
    )


def downgrade() -> None:
    """No-op: original strategy string values are not recoverable."""
    pass
