"""Unit tests for SASParser — block extraction and dependency ordering."""

import pytest
from src.worker.engine.models import BlockType
from src.worker.engine.parser import SASParser


@pytest.fixture()
def parser() -> SASParser:
    return SASParser()


# ── DATA step extraction ──────────────────────────────────────────────────────


def test_extracts_data_step(parser: SASParser) -> None:
    sas = """\
DATA output;
    SET input;
    x = 1;
RUN;
"""
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    data_blocks = [b for b in blocks if b.block_type == BlockType.DATA_STEP]
    assert len(data_blocks) == 1
    block = data_blocks[0]
    assert block.source_file == "test.sas"
    assert block.start_line == 1
    assert "DATA output" in block.raw_sas
    assert "output" in block.output_datasets
    assert "input" in block.input_datasets


def test_data_step_line_numbers(parser: SASParser) -> None:
    sas = "/* comment */\n\nDATA foo;\n    SET bar;\nRUN;\n"
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    data_blocks = [b for b in blocks if b.block_type == BlockType.DATA_STEP]
    assert len(data_blocks) == 1
    assert data_blocks[0].start_line == 3
    assert data_blocks[0].end_line == 5


def test_data_step_keep_drop_no_crash(parser: SASParser) -> None:
    sas = "DATA out;\n    SET src;\n    KEEP a b c;\nRUN;\n"
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    assert any(b.block_type == BlockType.DATA_STEP for b in blocks)


# ── PROC SQL extraction ───────────────────────────────────────────────────────


def test_extracts_proc_sql(parser: SASParser) -> None:
    sas = """\
PROC SQL;
    CREATE TABLE summary AS
    SELECT dept, COUNT(*) AS n
    FROM employees
    GROUP BY dept;
QUIT;
"""
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    sql_blocks = [b for b in blocks if b.block_type == BlockType.PROC_SQL]
    assert len(sql_blocks) == 1
    block = sql_blocks[0]
    assert "summary" in block.output_datasets
    assert "employees" in block.input_datasets


def test_proc_sql_case_insensitive(parser: SASParser) -> None:
    sas = "proc sql;\n    create table t as select 1 as x from src;\nquit;\n"
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    assert any(b.block_type == BlockType.PROC_SQL for b in blocks)


# ── Multi-file input ──────────────────────────────────────────────────────────


def test_multi_file_all_blocks_present(parser: SASParser) -> None:
    file_a = "DATA a_out;\n    SET raw;\n    y = 1;\nRUN;\n"
    file_b = "PROC SQL;\n    CREATE TABLE b_out AS SELECT * FROM a_out;\nQUIT;\n"
    result = parser.parse({"a.sas": file_a, "b.sas": file_b})
    blocks = result.blocks
    types = [b.block_type for b in blocks]
    assert BlockType.DATA_STEP in types
    assert BlockType.PROC_SQL in types
    files = {b.source_file for b in blocks}
    assert files == {"a.sas", "b.sas"}


# ── Dependency ordering ───────────────────────────────────────────────────────


def test_dependency_ordering(parser: SASParser) -> None:
    """The PROC SQL block reads a_out produced by the DATA step — it must come second."""
    file_a = "DATA a_out;\n    SET raw;\n    y = 1;\nRUN;\n"
    file_b = "PROC SQL;\n    CREATE TABLE result AS SELECT * FROM a_out;\nQUIT;\n"
    result = parser.parse({"a.sas": file_a, "b.sas": file_b})
    blocks = result.blocks
    translatable = [b for b in blocks if b.block_type != BlockType.UNTRANSLATABLE]
    data_idx = next(i for i, b in enumerate(translatable) if b.block_type == BlockType.DATA_STEP)
    sql_idx = next(i for i, b in enumerate(translatable) if b.block_type == BlockType.PROC_SQL)
    assert data_idx < sql_idx, "DATA step must precede the PROC SQL that consumes its output"


# ── PROC type detection ───────────────────────────────────────────────────────


def test_flags_unsupported_proc_as_proc_unknown(parser: SASParser) -> None:
    """Unfamiliar PROCs should yield PROC_UNKNOWN, not UNTRANSLATABLE."""
    sas = "PROC MIXED;\n    MODEL y = x;\nRUN;\n"
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    unknown = [b for b in blocks if b.block_type == BlockType.PROC_UNKNOWN]
    assert len(unknown) == 1
    assert "MIXED" in unknown[0].raw_sas.upper()
    # untranslatable_reason is NOT set on PROC_UNKNOWN blocks
    assert unknown[0].untranslatable_reason is None


def test_untranslatable_preserves_raw_sas(parser: SASParser) -> None:
    sas = "PROC REPORT DATA=src;\n    COLUMN a b;\nRUN;\n"
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    # PROC REPORT → PROC_UNKNOWN (not UNTRANSLATABLE)
    unknown = [b for b in blocks if b.block_type == BlockType.PROC_UNKNOWN]
    assert len(unknown) == 1
    assert "PROC REPORT" in unknown[0].raw_sas


# ── Sample file smoke test ────────────────────────────────────────────────────


def test_parses_sample_file(parser: SASParser) -> None:
    """Parsing the canonical sample must yield one DATA step and one PROC SQL."""
    import pathlib

    sample = pathlib.Path("samples/basic_etl.sas").read_text()
    result = parser.parse({"basic_etl.sas": sample})
    blocks = result.blocks
    types = [b.block_type for b in blocks]
    assert BlockType.DATA_STEP in types
    assert BlockType.PROC_SQL in types
    assert BlockType.UNTRANSLATABLE not in types


# ── PROC SORT extraction ──────────────────────────────────────────────────────


def test_extracts_proc_sort_basic_by(parser: SASParser) -> None:
    sas = "PROC SORT DATA=employees; BY salary; RUN;\n"
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    sort_blocks = [b for b in blocks if b.block_type == BlockType.PROC_SORT]
    assert len(sort_blocks) == 1
    block = sort_blocks[0]
    assert "employees" in block.input_datasets
    assert block.output_datasets == block.input_datasets


def test_proc_sort_with_out_parameter(parser: SASParser) -> None:
    sas = "PROC SORT DATA=employees OUT=sorted_out; BY salary; RUN;\n"
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    sort_blocks = [b for b in blocks if b.block_type == BlockType.PROC_SORT]
    assert len(sort_blocks) == 1
    result_block = sort_blocks[0]
    assert "sorted_out" in result_block.output_datasets
    assert "employees" in result_block.input_datasets


def test_proc_sort_descending_by(parser: SASParser) -> None:
    sas = "PROC SORT DATA=src; BY DESCENDING salary; RUN;\n"
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    sort_blocks = [b for b in blocks if b.block_type == BlockType.PROC_SORT]
    assert len(sort_blocks) == 1
    block = sort_blocks[0]
    assert "DESCENDING salary" in block.raw_sas


def test_proc_sort_without_out_fallback(parser: SASParser) -> None:
    sas = "PROC SORT DATA=mytable; BY col; RUN;\n"
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    sort_blocks = [b for b in blocks if b.block_type == BlockType.PROC_SORT]
    assert len(sort_blocks) == 1
    result_block = sort_blocks[0]
    assert result_block.output_datasets == ["mytable"]


def test_proc_sort_not_untranslatable(parser: SASParser) -> None:
    sas = "PROC SORT DATA=src; BY col; RUN;\n"
    result = parser.parse({"test.sas": sas})
    blocks = result.blocks
    assert not any(b.block_type == BlockType.UNTRANSLATABLE for b in blocks)
    sort_blocks = [b for b in blocks if b.block_type == BlockType.PROC_SORT]
    assert len(sort_blocks) == 1


# ── %LET macro variable extraction ───────────────────────────────────────────


def test_extracts_let_macro_var(parser: SASParser) -> None:
    sas = "%LET threshold = 42;\n"
    result = parser.parse({"test.sas": sas})
    assert len(result.macro_vars) == 1
    assert result.macro_vars[0].name == "THRESHOLD"
    assert result.macro_vars[0].raw_value == "42"
    assert result.macro_vars[0].line == 1


def test_let_macro_var_name_uppercased(parser: SASParser) -> None:
    sas = "%let myvar = hello;\n"
    result = parser.parse({"test.sas": sas})
    assert result.macro_vars[0].name == "MYVAR"


def test_let_multiple_declarations(parser: SASParser) -> None:
    sas = "%LET a = 1;\n%LET b = 2;\n%LET c = 3;\n"
    result = parser.parse({"test.sas": sas})
    assert len(result.macro_vars) == 3
    assert {mv.name for mv in result.macro_vars} == {"A", "B", "C"}


def test_let_does_not_produce_block(parser: SASParser) -> None:
    sas = "%LET x = foo;\n"
    result = parser.parse({"test.sas": sas})
    assert result.blocks == []
    assert len(result.macro_vars) == 1
