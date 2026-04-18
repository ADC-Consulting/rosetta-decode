"""Request and response Pydantic schemas for the backend API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MigrateResponse(BaseModel):
    """Response body for POST /migrate."""

    job_id: uuid.UUID


class JobStatusResponse(BaseModel):
    """Response body for GET /jobs/{id}."""

    job_id: uuid.UUID
    status: str
    python_code: str | None = None
    report: dict[str, Any] | None = None
    error: str | None = None


class JobSummary(BaseModel):
    """Summary row for a single job, used in list responses."""

    job_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime
    error: str | None = None


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
