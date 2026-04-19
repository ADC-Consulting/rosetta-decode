"""Request and response Pydantic schemas for the backend API."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class FileRejection(BaseModel):
    """A file rejected during zip upload."""

    filename: str
    reason: str


class MigrateResponse(BaseModel):
    """Response body for POST /migrate."""

    job_id: uuid.UUID
    accepted: list[str] = []
    rejected: list[FileRejection] = []


class JobStatusResponse(BaseModel):
    """Response body for GET /jobs/{id}."""

    job_id: uuid.UUID
    status: str
    python_code: str | None = None
    report: dict[str, Any] | None = None
    error: str | None = None
    name: str | None = None


class JobSummary(BaseModel):
    """Summary row for a single job, used in list responses."""

    job_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    name: str | None = None
    file_count: int = 0


class JobListResponse(BaseModel):
    """Response body for GET /jobs."""

    jobs: list[JobSummary]


class AuditResponse(BaseModel):
    """Response body for GET /jobs/{id}/audit."""

    job_id: uuid.UUID
    input_hash: str
    llm_model: str | None
    created_at: datetime
    updated_at: datetime
    report: dict[str, Any] | None


class JobSourcesResponse(BaseModel):
    """Response body for GET /jobs/{id}/sources."""

    job_id: uuid.UUID
    sources: dict[str, str]


class LineageNode(BaseModel):
    """A single block node in the job lineage graph."""

    id: str
    label: str
    source_file: str
    block_type: str
    status: Literal["migrated", "manual_review", "untranslatable"]


class LineageEdge(BaseModel):
    """A directed data-flow edge between two lineage nodes."""

    source: str
    target: str
    dataset: str
    inferred: bool


class JobLineageResponse(BaseModel):
    """Response body for GET /jobs/{id}/lineage."""

    job_id: uuid.UUID
    nodes: list[LineageNode]
    edges: list[LineageEdge]


class JobDocResponse(BaseModel):
    """Response body for GET /jobs/{id}/doc."""

    job_id: uuid.UUID
    doc: str | None
