"""Tests for JobContext.windowed_context() and ReconciliationReport."""

import pytest
from src.worker.engine.models import (
    BlockType,
    GeneratedBlock,
    JobContext,
    MacroVar,
    ReconciliationReport,
    SASBlock,
)


@pytest.fixture()
def sample_block() -> SASBlock:
    return SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="etl.sas",
        start_line=10,
        end_line=20,
        raw_sas="data out; set in; run;",
        input_datasets=["in"],
        output_datasets=["out"],
    )


@pytest.fixture()
def sample_context(sample_block: SASBlock) -> JobContext:
    macro = MacroVar(name="threshold", raw_value="100", source_file="etl.sas", line=1)
    other_block = SASBlock(
        block_type=BlockType.PROC_SQL,
        source_file="etl.sas",
        start_line=30,
        end_line=40,
        raw_sas="proc sql; quit;",
        input_datasets=["other"],
        output_datasets=["result"],
    )
    return JobContext(
        source_files={"etl.sas": "data out; set in; run;"},
        resolved_macros=[macro],
        dependency_order=["in", "out", "other", "result"],
        risk_flags=["nested macro at etl.sas:42"],
        blocks=[sample_block, other_block],
        generated=[],
        retry_count=2,
        llm_call_count=5,
    )


def test_windowed_context_contains_only_given_block(
    sample_context: JobContext, sample_block: SASBlock
) -> None:
    windowed = sample_context.windowed_context(sample_block)
    assert windowed.blocks == [sample_block]


def test_windowed_context_source_files_empty(
    sample_context: JobContext, sample_block: SASBlock
) -> None:
    windowed = sample_context.windowed_context(sample_block)
    assert windowed.source_files == {}


def test_windowed_context_filters_dependency_order(
    sample_context: JobContext, sample_block: SASBlock
) -> None:
    windowed = sample_context.windowed_context(sample_block)
    assert set(windowed.dependency_order) == {"in", "out"}
    assert "other" not in windowed.dependency_order
    assert "result" not in windowed.dependency_order


def test_windowed_context_preserves_resolved_macros(
    sample_context: JobContext, sample_block: SASBlock
) -> None:
    windowed = sample_context.windowed_context(sample_block)
    assert windowed.resolved_macros == sample_context.resolved_macros


def test_windowed_context_preserves_risk_flags(
    sample_context: JobContext, sample_block: SASBlock
) -> None:
    windowed = sample_context.windowed_context(sample_block)
    assert windowed.risk_flags == sample_context.risk_flags


def test_windowed_context_preserves_counts(
    sample_context: JobContext, sample_block: SASBlock
) -> None:
    windowed = sample_context.windowed_context(sample_block)
    assert windowed.retry_count == 2
    assert windowed.llm_call_count == 5


def test_windowed_context_generated_is_empty(
    sample_context: JobContext, sample_block: SASBlock
) -> None:
    gen = GeneratedBlock(source_block=sample_block, python_code="df = df")
    sample_context = sample_context.model_copy(update={"generated": [gen]})
    windowed = sample_context.windowed_context(sample_block)
    assert windowed.generated == []


def test_reconciliation_report_construction() -> None:
    report = ReconciliationReport(
        passed=True,
        row_count_match=True,
        column_match=True,
        diff_summary="OK",
        affected_block_ids=["etl.sas:10"],
    )
    assert report.passed is True
    assert report.diff_summary == "OK"
    assert report.affected_block_ids == ["etl.sas:10"]


def test_job_context_reconciliation_defaults_to_none(
    sample_context: JobContext,
) -> None:
    assert sample_context.reconciliation is None


def test_macro_var_name_normalised_to_uppercase() -> None:
    macro = MacroVar(name="threshold", raw_value="100", source_file="etl.sas", line=1)
    assert macro.name == "THRESHOLD"
