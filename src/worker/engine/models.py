"""Pydantic models shared across the migration engine (parser → LLM → codegen)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class BlockType(StrEnum):
    """SAS construct types handled by the migration engine."""

    DATA_STEP = "DATA_STEP"
    PROC_SQL = "PROC_SQL"
    UNTRANSLATABLE = "UNTRANSLATABLE"


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
