"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    error_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    doc: Mapped[str | None] = mapped_column(Text, nullable=True)
    migration_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    generated_files: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    user_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    skip_llm: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.text("false")
    )
    parent_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    trigger: Mapped[str] = mapped_column(
        String(32), nullable=False, default="agent", server_default=sa.text("'agent'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    versions: Mapped[list["JobVersion"]] = relationship(
        "JobVersion", back_populates="job", cascade="all, delete-orphan"
    )
    block_revisions: Mapped[list["BlockRevision"]] = relationship(
        "BlockRevision", back_populates="job", cascade="all, delete-orphan"
    )


class JobVersion(Base):
    """A saved snapshot of a specific editor tab for a migration job."""

    __tablename__ = "job_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    tab: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="human-save")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    job: Mapped["Job"] = relationship("Job", back_populates="versions")


class BlockRevision(Base):
    """A versioned translation of a single SAS code block within a migration job."""

    __tablename__ = "block_revisions"
    __table_args__ = (Index("ix_block_revisions_job_id_block_id", "job_id", "block_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    block_id: Mapped[str] = mapped_column(Text, nullable=False)  # "basename.sas:start_line"
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    python_code: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="high")
    uncertainty_notes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reconciliation_status: Mapped[str | None] = mapped_column(String(8), nullable=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="agent")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # verbatim user instructions
    hint: Mapped[str | None] = mapped_column(Text, nullable=True)  # auto-generated structured hint
    diff_vs_previous: Mapped[str | None] = mapped_column(Text, nullable=True)  # unified diff
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped["Job"] = relationship("Job", back_populates="block_revisions")


class ExplainSession(Base):
    """A persisted chat session on the Explain page."""

    __tablename__ = "explain_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    audience: Mapped[str] = mapped_column(Text, nullable=False, default="tech")
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    context_files: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
