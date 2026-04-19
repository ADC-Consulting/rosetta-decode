"""Pydantic models shared across the migration engine (parser → LLM → codegen)."""

from enum import StrEnum

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


class ReconciliationReport(BaseModel):
    """Outcome of a single reconciliation run against reference data."""

    passed: bool
    row_count_match: bool
    column_match: bool
    diff_summary: str
    affected_block_ids: list[str] = Field(default_factory=list)


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
        )
