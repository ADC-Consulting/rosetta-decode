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
    source_file: str = ""
    block_type: str = ""
    status: Literal["migrated", "manual_review", "untranslatable"] = "migrated"


class LineageEdge(BaseModel):
    """A directed data-flow edge between two lineage nodes."""

    source: str
    target: str
    dataset: str
    inferred: bool = False


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


class FileNodeResponse(BaseModel):
    """A single SAS source file node in the lineage graph."""

    filename: str
    file_type: Literal["PROGRAM", "MACRO", "AUTOEXEC", "LOG", "OTHER"]
    blocks: list[str] = []
    status: Literal["OK", "UNTRANSLATABLE", "ERROR_PRONE"] | None = None
    status_reason: str | None = None


class FileEdgeResponse(BaseModel):
    """A directed dependency edge between two SAS source files."""

    source_file: str
    target_file: str
    reason: Literal["INCLUDE", "MACRO_CALL", "READS_DATASET", "WRITES_DATASET"]
    via_block_id: str


class PipelineStepResponse(BaseModel):
    """A higher-level named pipeline stage."""

    step_id: str
    name: str
    description: str
    files: list[str] = []
    blocks: list[str] = []
    inputs: list[str] = []
    outputs: list[str] = []


class BlockStatusResponse(BaseModel):
    """Per-block translation/health status."""

    block_id: str
    status: Literal["OK", "UNTRANSLATABLE", "ERROR_PRONE"]
    reason: str | None = None


class LogLinkResponse(BaseModel):
    """Links a SAS log file to related source files and blocks."""

    log_file: str
    related_files: list[str] = []
    related_blocks: list[str] = []
    severity: Literal["INFO", "WARNING", "ERROR"]


class JobLineageResponse(BaseModel):
    """Response body for GET /jobs/{id}/lineage."""

    job_id: uuid.UUID
    nodes: list[LineageNode]
    edges: list[LineageEdge]
    column_flows: list[ColumnFlowResponse] = []
    macro_usages: list[MacroUsageResponse] = []
    cross_file_edges: list[dict[str, Any]] = []
    dataset_summaries: dict[str, str] = {}
    file_nodes: list[FileNodeResponse] = []
    file_edges: list[FileEdgeResponse] = []
    pipeline_steps: list[PipelineStepResponse] = []
    block_status: list[BlockStatusResponse] = []
    log_links: list[LogLinkResponse] = []


class JobDocResponse(BaseModel):
    """Response body for GET /jobs/{id}/doc."""

    job_id: uuid.UUID
    doc: str | None
    non_technical_doc: str | None = None


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
    confidence_score: float = 0.0
    confidence_band: str = "unknown"


class JobPlanResponse(BaseModel):
    """Response body for GET /jobs/{id}/plan."""

    job_id: uuid.UUID
    summary: str
    overall_risk: str
    block_plans: list[BlockPlanResponse]
    recommended_review_blocks: list[str]
    cross_file_dependencies: list[str]
    risk_explanation: str = ""


class AcceptJobRequest(BaseModel):
    """Request body for POST /jobs/{id}/accept."""

    notes: str | None = None


StrategyLiteral = Literal[
    "translate",
    "translate_with_review",
    "manual_ingestion",
    "manual",
    "skip",
]


class BlockOverride(BaseModel):
    """A single per-block reviewer override."""

    block_id: str
    strategy: StrategyLiteral | None = None
    risk: str | None = None
    note: str | None = None


class PatchPlanRequest(BaseModel):
    """Request body for PATCH /jobs/{id}/plan."""

    block_overrides: list[BlockOverride] = []


class JobVersionSummary(BaseModel):
    """Summary of a job version (no content field)."""

    id: str
    job_id: str
    tab: str
    trigger: str
    created_at: datetime


class JobVersionDetail(BaseModel):
    """Full detail of a job version including content."""

    id: str
    job_id: str
    tab: str
    trigger: str
    created_at: datetime
    content: dict[str, Any]


class SaveVersionRequest(BaseModel):
    """Request body for POST /jobs/{id}/versions."""

    content: dict[str, Any]
    trigger: str = "human-save"


class SaveVersionResponse(BaseModel):
    """Response body for POST /jobs/{id}/versions."""

    id: str
    job_id: str
    tab: str
    created_at: datetime


class BlockRefineRequest(BaseModel):
    """Request body for POST /jobs/{id}/blocks/{block_id}/refine."""

    notes: str | None = None  # primary: user instructions, injected first into LLM
    hint: str | None = None  # secondary: structured hint (e.g. from reconciliation failure)


class BlockRefineResponse(BaseModel):
    """Response body for POST /jobs/{id}/blocks/{block_id}/refine."""

    block_id: str
    revision_number: int
    confidence: str = "high"
    confidence_score: float = 0.0
    confidence_band: str = "unknown"
    reconciliation_status: str | None
    python_code: str | None = None  # full updated job python_code after the refine


class BlockRevisionResponse(BaseModel):
    """A single block revision record."""

    id: str
    job_id: str
    block_id: str
    revision_number: int
    python_code: str
    strategy: str
    confidence: str
    confidence_score: float = 0.0
    confidence_band: str = "unknown"
    uncertainty_notes: list[str]
    reconciliation_status: str | None
    trigger: str
    notes: str | None
    hint: str | None
    diff_vs_previous: str | None
    created_at: datetime


class BlockRevisionListResponse(BaseModel):
    """Response body for GET /jobs/{id}/blocks/{block_id}/revisions."""

    block_id: str
    revisions: list[BlockRevisionResponse]


class BlockPythonEditRequest(BaseModel):
    """Request body for PATCH /jobs/{id}/blocks/{block_id}/python."""

    python_code: str
    notes: str | None = None


class BlockPythonEditResponse(BaseModel):
    """Response body for PATCH /jobs/{id}/blocks/{block_id}/python."""

    revision_number: int
    block_id: str


# S6 — Job-level changelog schemas


class ChangelogEntry(BaseModel):
    """A single block revision entry in the job-level changelog."""

    id: str
    block_id: str
    revision_number: int
    trigger: str
    strategy: str
    confidence: str
    reconciliation_status: str | None
    notes: str | None
    hint: str | None
    diff_vs_previous: str | None
    created_at: datetime


class JobChangelogResponse(BaseModel):
    """Response body for GET /jobs/{id}/changelog."""

    job_id: str
    entries: list[ChangelogEntry]


# S7 — Tiered trust report schemas


class TrustReportBlock(BaseModel):
    """Per-block trust data for the tiered trust report."""

    block_id: str
    source_file: str
    start_line: int
    block_type: str
    strategy: str
    self_confidence: str
    verified_confidence: str | None
    confidence_band: str | None = None
    reconciliation_status: str | None
    needs_attention: bool
    blast_radius: int | None  # null if lineage unavailable


class TrustReportFile(BaseModel):
    """Per-source-file aggregated trust metrics."""

    source_file: str
    total_blocks: int
    auto_verified: int
    needs_review: int
    manual_todo: int
    failed_reconciliation: int


class TrustReportResponse(BaseModel):
    """Response body for GET /jobs/{id}/trust-report."""

    job_id: str
    lineage_available: bool
    overall_confidence: str  # "high" / "medium" / "low" / "unknown"
    overall_confidence_score: float  # 0.0-1.0 average of block confidence_scores
    total_blocks: int
    auto_verified: int
    needs_review: int
    manual_todo: int
    failed_reconciliation: int
    files: list[TrustReportFile]
    blocks: list[TrustReportBlock]  # sorted by needs_attention DESC, then blast_radius DESC
    review_queue: list[TrustReportBlock]  # only needs_attention=True blocks


# Attachment schemas


class AttachmentInfo(BaseModel):
    """Metadata for a single non-SAS attachment stored with a job."""

    filename: str
    path_key: str
    category: str  # "log" | "output" | "other"
    size_bytes: int
    extension: str


class JobAttachmentsResponse(BaseModel):
    """Response body for GET /jobs/{id}/attachments."""

    job_id: str
    attachments: list[AttachmentInfo]


# FE8 — ExplainPage schemas


class ExplainMessage(BaseModel):
    """A single turn in an explain conversation."""

    role: Literal["user", "assistant"]
    content: str


class ExplainJobRequest(BaseModel):
    """Request body for POST /explain/job."""

    job_id: uuid.UUID
    question: str
    messages: list[ExplainMessage] = []
    context_fields: list[Literal["plan", "doc", "python_code"]] = ["plan", "doc"]


class ExplainResponse(BaseModel):
    """Response body for POST /explain and POST /explain/job."""

    answer: str
    context_files: list[str] = []
    tokens_used: int | None = None
    job_id: uuid.UUID | None = None


class CreateExplainSessionRequest(BaseModel):
    """Request body for POST /explain/sessions."""

    mode: Literal["migration", "sas_general"]
    job_id: str | None = None
    audience: Literal["tech", "non_tech"] = "tech"
    title: str | None = None
    file_name: str | None = None


class ExplainSessionResponse(BaseModel):
    """Response for explain session endpoints."""

    session_id: str
    messages: list[ExplainMessage]
    mode: str
    audience: str
    created_at: datetime
    title: str | None = None
    file_name: str | None = None
    job_id: str | None = None


class ExecuteRequest(BaseModel):
    """Request body for POST /jobs/{job_id}/execute."""

    block_id: str | None = None


class ExecuteResponse(BaseModel):
    """Response body for POST /jobs/{job_id}/execute — proxied from executor service."""

    stdout: str
    stderr: str
    result_json: list[dict[str, Any]] | None = None
    result_columns: list[str] | None = None
    checks: list[dict[str, Any]] | None = None
    error: str | None = None
    elapsed_ms: int
