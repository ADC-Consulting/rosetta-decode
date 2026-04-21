"""Pydantic models shared across the migration engine (parser → LLM → codegen)."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class BlockType(StrEnum):
    """SAS construct types handled by the migration engine."""

    DATA_STEP = "DATA_STEP"
    PROC_SQL = "PROC_SQL"
    PROC_SORT = "PROC_SORT"
    UNTRANSLATABLE = "UNTRANSLATABLE"


class MacroVar(BaseModel):
    """A resolved SAS macro variable declared via %LET.

    Attributes:
        name: Macro variable name, stored uppercase.
        raw_value: Raw string value as declared (e.g. "100", "department").
        source_file: Name of the `.sas` file containing the %LET declaration.
        line: 1-based line number of the %LET declaration.
    """

    name: str
    raw_value: str
    source_file: str
    line: int = Field(ge=1)

    def model_post_init(self, __context: object) -> None:
        """Normalise name to uppercase after construction."""
        object.__setattr__(self, "name", self.name.upper())


class SASBlock(BaseModel):
    """A single parsed SAS construct extracted from one source file.

    Attributes:
        block_type: Construct category (DATA step, PROC SQL, or untranslatable).
        source_file: Name of the `.sas` file this block was extracted from.
        start_line: 1-based line number of the first line of the block.
        end_line: 1-based line number of the last line of the block (inclusive).
        raw_sas: Exact SAS source text for this block, including whitespace.
        untranslatable_reason: Human-readable reason when block_type is UNTRANSLATABLE.
        input_datasets: Dataset names read by this block (used for dependency ordering).
        output_datasets: Dataset names written by this block.
    """

    block_type: BlockType
    source_file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    raw_sas: str
    untranslatable_reason: str | None = None
    input_datasets: list[str] = Field(default_factory=list)
    output_datasets: list[str] = Field(default_factory=list)


class ParseResult(BaseModel):
    """Aggregated output of the SAS parser for a single file.

    Attributes:
        blocks: Ordered list of SAS construct blocks extracted from the file.
        macro_vars: Macro variables declared via %LET in the file.
    """

    blocks: list[SASBlock] = Field(default_factory=list)
    macro_vars: list[MacroVar] = Field(default_factory=list)


class GeneratedBlock(BaseModel):
    """LLM-translated Python code for a single SAS block.

    Attributes:
        source_block: The original SASBlock this was generated from.
        python_code: Translated Python source lines. Each logical line group
            must be followed by a ``# SAS: <file>:<line>`` provenance comment.
            Untranslatable blocks contain only a ``# SAS-UNTRANSLATABLE: <reason>``
            comment with no executable code.
        is_untranslatable: True when the block could not be reliably translated.
    """

    source_block: SASBlock
    python_code: str
    is_untranslatable: bool = False
    confidence: str = "high"
    uncertainty_notes: list[str] = []


class ReconciliationReport(BaseModel):
    """Outcome of a single reconciliation run against reference data."""

    passed: bool
    row_count_match: bool
    column_match: bool
    diff_summary: str
    affected_block_ids: list[str] = Field(default_factory=list)


class TranslationStrategy(StrEnum):
    """Strategy to apply when migrating a SAS block."""

    TRANSLATE = "translate"
    TRANSLATE_WITH_REVIEW = "translate_with_review"
    MANUAL_INGESTION = "manual_ingestion"
    MANUAL = "manual"
    SKIP = "skip"


class BlockRisk(StrEnum):
    """Risk level assigned to a SAS block or migration as a whole."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BlockPlan(BaseModel):
    """Migration plan for a single SAS block.

    Attributes:
        block_id: Unique identifier for the block.
        source_file: Name of the `.sas` file containing the block.
        start_line: 1-based line number where the block starts.
        block_type: SAS construct type (e.g. DATA_STEP, PROC_SQL).
        strategy: Translation strategy to apply.
        risk: Risk level for this block.
        rationale: Explanation of the chosen strategy and risk level.
        estimated_effort: Human-readable effort estimate (e.g. "low", "2h").
    """

    block_id: str
    source_file: str
    start_line: int
    block_type: str
    strategy: TranslationStrategy
    risk: BlockRisk
    rationale: str
    estimated_effort: str


class MigrationPlan(BaseModel):
    """Overall migration plan produced by the planning agent.

    Attributes:
        summary: High-level description of the migration scope.
        block_plans: Per-block plans ordered by dependency.
        overall_risk: Aggregate risk level for the full migration.
        recommended_review_blocks: Block IDs that require human review.
        cross_file_dependencies: Dataset/macro names shared across files.
    """

    summary: str
    block_plans: list[BlockPlan]
    overall_risk: BlockRisk
    recommended_review_blocks: list[str]
    cross_file_dependencies: list[str]


class ColumnFlow(BaseModel):
    """A single column lineage edge from source to target dataset.

    Attributes:
        column: Column name.
        source_dataset: Name of the dataset the column originates from.
        target_dataset: Name of the dataset the column flows into.
        via_block_id: ID of the block that performs the transformation.
        transformation: Optional description of the transformation applied.
    """

    column: str
    source_dataset: str
    target_dataset: str
    via_block_id: str
    transformation: str | None = None


class MacroUsage(BaseModel):
    """A single resolved macro variable usage within a block.

    Attributes:
        macro_name: Name of the macro variable.
        macro_value: Resolved value at time of usage.
        used_in_block_id: ID of the block where the macro is referenced.
    """

    macro_name: str
    macro_value: str
    used_in_block_id: str


class FileNode(BaseModel):
    """A single SAS source file node in the lineage graph."""

    filename: str
    file_type: Literal["PROGRAM", "MACRO", "AUTOEXEC", "LOG", "OTHER"]
    blocks: list[str] = Field(default_factory=list)
    status: Literal["OK", "UNTRANSLATABLE", "ERROR_PRONE"] | None = None
    status_reason: str | None = None


class FileEdge(BaseModel):
    """A directed dependency edge between two SAS source files."""

    source_file: str
    target_file: str
    reason: Literal["INCLUDE", "MACRO_CALL", "READS_DATASET", "WRITES_DATASET"]
    via_block_id: str


class PipelineStep(BaseModel):
    """A higher-level named pipeline stage grouping files and blocks."""

    step_id: str
    name: str
    description: str
    files: list[str] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class BlockStatus(BaseModel):
    """Per-block translation/health status."""

    block_id: str
    status: Literal["OK", "UNTRANSLATABLE", "ERROR_PRONE"]
    reason: str | None = None


class LogLink(BaseModel):
    """Links a SAS log file to related source files and blocks."""

    log_file: str
    related_files: list[str] = Field(default_factory=list)
    related_blocks: list[str] = Field(default_factory=list)
    severity: Literal["INFO", "WARNING", "ERROR"]


class EnrichedLineage(BaseModel):
    """Full enriched lineage graph produced by the lineage agent."""

    column_flows: list[ColumnFlow]
    macro_usages: list[MacroUsage]
    cross_file_edges: list[dict[str, str]]
    dataset_summaries: dict[str, str]
    file_nodes: list[FileNode] = Field(default_factory=list)
    file_edges: list[FileEdge] = Field(default_factory=list)
    pipeline_steps: list[PipelineStep] = Field(default_factory=list)
    block_status: list[BlockStatus] = Field(default_factory=list)
    log_links: list[LogLink] = Field(default_factory=list)


class JobContext(BaseModel):
    """Shared context object passed between all agentic pipeline stages."""

    source_files: dict[str, str]
    resolved_macros: list[MacroVar]
    dependency_order: list[str]
    risk_flags: list[str]
    blocks: list[SASBlock]
    generated: list[GeneratedBlock]
    reconciliation: ReconciliationReport | None = None
    retry_count: int = 0
    llm_call_count: int = 0
    migration_plan: MigrationPlan | None = None
    enriched_lineage: EnrichedLineage | None = None

    def windowed_context(self, block: SASBlock) -> "JobContext":
        """Return a windowed view of this context scoped to a single block.

        Translation agents receive only:
        - source_files: empty (full source only for AnalysisAgent/DocumentationAgent)
        - resolved_macros: full list (needed for macro substitution in any block)
        - dependency_order: only entries relevant to block's input/output datasets
        - risk_flags: full list
        - blocks: only this block
        - generated: empty (not needed during per-block translation)
        - reconciliation, retry_count, llm_call_count: preserved as-is
        """
        relevant_datasets = set(block.input_datasets) | set(block.output_datasets)
        return JobContext(
            source_files={},
            resolved_macros=self.resolved_macros,
            dependency_order=[d for d in self.dependency_order if d in relevant_datasets],
            risk_flags=self.risk_flags,
            blocks=[block],
            generated=[],
            reconciliation=self.reconciliation,
            retry_count=self.retry_count,
            llm_call_count=self.llm_call_count,
            migration_plan=self.migration_plan,
        )
