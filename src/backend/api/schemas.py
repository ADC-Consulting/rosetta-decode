"""Request and response Pydantic schemas for the backend API."""

import uuid
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
