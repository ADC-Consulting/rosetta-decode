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
    generated_files: dict[str, str] | None = None
    user_overrides: dict[str, Any] | None = None
    accepted_at: datetime | None = None
    parent_job_id: str | None = None
    trigger: str = "agent"
    skip_llm: bool = False


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


class ColumnFlowResponse(BaseModel):
    """A single column-level data-flow record within the lineage graph."""

    column: str
    source_dataset: str
    target_dataset: str
    via_block_id: str


class UpdatePythonCodeRequest(BaseModel):
    """Request body for PUT /jobs/{id}/python_code."""

    python_code: str


class RefineRequest(BaseModel):
    """Request body for POST /jobs/{id}/refine."""

    hint: str | None = None


class RefineResponse(BaseModel):
    """Response body for POST /jobs/{id}/refine."""

    job_id: str


class JobHistoryEntry(BaseModel):
    """A single entry in a job version chain."""

    job_id: str
    status: str
    trigger: str
    name: str | None
    created_at: datetime
    updated_at: datetime
    is_current: bool


class JobHistoryResponse(BaseModel):
    """Response body for GET /jobs/{id}/history."""

    entries: list[JobHistoryEntry]


class MacroUsageResponse(BaseModel):
    """A single SAS macro variable usage record within the lineage graph."""

    macro_name: str
    macro_value: str
    used_in_block_id: str


class JobLineageResponse(BaseModel):
    """Response body for GET /jobs/{id}/lineage."""

    job_id: uuid.UUID
    nodes: list[LineageNode]
    edges: list[LineageEdge]
    column_flows: list[ColumnFlowResponse] = []
    macro_usages: list[MacroUsageResponse] = []
    cross_file_edges: list[dict[str, Any]] = []
    dataset_summaries: dict[str, str] = {}


class JobDocResponse(BaseModel):
    """Response body for GET /jobs/{id}/doc."""

    job_id: uuid.UUID
    doc: str | None


class BlockPlanResponse(BaseModel):
    """Migration plan detail for a single parsed SAS block."""

    block_id: str
    source_file: str
    start_line: int
    block_type: str
    strategy: str
    risk: str
    rationale: str
    estimated_effort: str


class JobPlanResponse(BaseModel):
    """Response body for GET /jobs/{id}/plan."""

    job_id: uuid.UUID
    summary: str
    overall_risk: str
    block_plans: list[BlockPlanResponse]
    recommended_review_blocks: list[str]
    cross_file_dependencies: list[str]


class AcceptJobRequest(BaseModel):
    """Request body for POST /jobs/{id}/accept."""

    notes: str | None = None


class BlockOverride(BaseModel):
    """A single per-block reviewer override."""

    block_id: str
    strategy: str | None = None
    risk: str | None = None
    note: str | None = None


class PatchPlanRequest(BaseModel):
    """Request body for PATCH /jobs/{id}/plan."""

    block_overrides: list[BlockOverride] = []
