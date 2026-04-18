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
    blocks = parser.parse({"test.sas": sas})
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
    blocks = parser.parse({"test.sas": sas})
    data_blocks = [b for b in blocks if b.block_type == BlockType.DATA_STEP]
    assert len(data_blocks) == 1
    assert data_blocks[0].start_line == 3
    assert data_blocks[0].end_line == 5


def test_data_step_keep_drop_no_crash(parser: SASParser) -> None:
    sas = "DATA out;\n    SET src;\n    KEEP a b c;\nRUN;\n"
    blocks = parser.parse({"test.sas": sas})
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
    blocks = parser.parse({"test.sas": sas})
    sql_blocks = [b for b in blocks if b.block_type == BlockType.PROC_SQL]
    assert len(sql_blocks) == 1
    block = sql_blocks[0]
    assert "summary" in block.output_datasets
    assert "employees" in block.input_datasets


def test_proc_sql_case_insensitive(parser: SASParser) -> None:
    sas = "proc sql;\n    create table t as select 1 as x from src;\nquit;\n"
    blocks = parser.parse({"test.sas": sas})
    assert any(b.block_type == BlockType.PROC_SQL for b in blocks)


# ── Multi-file input ──────────────────────────────────────────────────────────


def test_multi_file_all_blocks_present(parser: SASParser) -> None:
    file_a = "DATA a_out;\n    SET raw;\n    y = 1;\nRUN;\n"
    file_b = "PROC SQL;\n    CREATE TABLE b_out AS SELECT * FROM a_out;\nQUIT;\n"
    blocks = parser.parse({"a.sas": file_a, "b.sas": file_b})
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
    blocks = parser.parse({"a.sas": file_a, "b.sas": file_b})
    translatable = [b for b in blocks if b.block_type != BlockType.UNTRANSLATABLE]
    data_idx = next(i for i, b in enumerate(translatable) if b.block_type == BlockType.DATA_STEP)
    sql_idx = next(i for i, b in enumerate(translatable) if b.block_type == BlockType.PROC_SQL)
    assert data_idx < sql_idx, "DATA step must precede the PROC SQL that consumes its output"


# ── Untranslatable construct flagging ─────────────────────────────────────────


def test_flags_unsupported_proc(parser: SASParser) -> None:
    sas = "PROC MIXED;\n    MODEL y = x;\nRUN;\n"
    blocks = parser.parse({"test.sas": sas})
    untrans = [b for b in blocks if b.block_type == BlockType.UNTRANSLATABLE]
    assert len(untrans) == 1
    assert untrans[0].untranslatable_reason is not None
    assert "MIXED" in untrans[0].untranslatable_reason


def test_untranslatable_preserves_raw_sas(parser: SASParser) -> None:
    sas = "PROC REPORT DATA=src;\n    COLUMN a b;\nRUN;\n"
    blocks = parser.parse({"test.sas": sas})
    untrans = [b for b in blocks if b.block_type == BlockType.UNTRANSLATABLE]
    assert len(untrans) == 1
    assert "PROC REPORT" in untrans[0].raw_sas


# ── Sample file smoke test ────────────────────────────────────────────────────


def test_parses_sample_file(parser: SASParser) -> None:
    """Parsing the canonical sample must yield one DATA step and one PROC SQL."""
    import pathlib

    sample = pathlib.Path("samples/basic_etl.sas").read_text()
    blocks = parser.parse({"basic_etl.sas": sample})
    types = [b.block_type for b in blocks]
    assert BlockType.DATA_STEP in types
    assert BlockType.PROC_SQL in types
    assert BlockType.UNTRANSLATABLE not in types
