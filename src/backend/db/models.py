"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all models."""


class Job(Base):
    """A single SAS-to-Python migration job."""

    __tablename__ = "jobs"

    # UUID stored as string for cross-dialect compatibility in tests (SQLite).
    # Alembic migration uses PostgreSQL native UUID type in production.
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="queued",
    )
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    files: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    python_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
