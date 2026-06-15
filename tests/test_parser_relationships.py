"""Unit tests for relationship extraction in SASParser (F34 P3-A / P3-B).

Covers:
- merge_by_vars extraction from DATA step MERGE … BY clauses
- join_on_keys extraction from PROC SQL JOIN … ON clauses (with alias resolution)
"""

# SAS: test_parser_relationships.py:module
import pytest
from src.worker.engine.models import BlockType
from src.worker.engine.parser import (
    SASParser,
    _build_alias_map,
    _extract_join_on_keys,
    _extract_merge_by_vars,
)


@pytest.fixture()
def parser() -> SASParser:
    """Shared SASParser instance."""
    return SASParser()


# ── _extract_merge_by_vars unit tests ────────────────────────────────────────


def test_merge_by_vars_single_column() -> None:
    """BY clause with a single column after MERGE returns that column."""
    # SAS: test_parser_relationships.py:test_merge_by_vars_single_column
    raw = "DATA merged;\n    MERGE dm(in=a) ex(in=b);\n    BY USUBJID;\nRUN;"
    assert _extract_merge_by_vars(raw) == ["usubjid"]


def test_merge_by_vars_multiple_columns() -> None:
    """BY clause with multiple columns after MERGE returns all of them lowercased."""
    # SAS: test_parser_relationships.py:test_merge_by_vars_multiple_columns
    raw = "DATA merged;\n    MERGE dm(in=a) ex(in=b);\n    BY USUBJID STUDYID;\nRUN;"
    result = _extract_merge_by_vars(raw)
    assert result == ["usubjid", "studyid"]


def test_merge_by_vars_no_merge_returns_empty() -> None:
    """DATA step without a MERGE statement returns an empty list."""
    # SAS: test_parser_relationships.py:test_merge_by_vars_no_merge_returns_empty
    raw = "DATA out;\n    SET input;\n    BY col1;\nRUN;"
    assert _extract_merge_by_vars(raw) == []


def test_merge_by_vars_case_insensitive_keyword() -> None:
    """merge / by keywords are matched case-insensitively."""
    # SAS: test_parser_relationships.py:test_merge_by_vars_case_insensitive_keyword
    raw = "data merged;\n    merge dm ex;\n    by patid;\nrun;"
    assert _extract_merge_by_vars(raw) == ["patid"]


# ── _build_alias_map unit tests ───────────────────────────────────────────────


def test_build_alias_map_simple_from() -> None:
    """FROM table alias maps alias to table name."""
    # SAS: test_parser_relationships.py:test_build_alias_map_simple_from
    sql = "SELECT * FROM dm a JOIN ex b ON a.USUBJID = b.USUBJID"
    alias_map = _build_alias_map(sql)
    assert alias_map.get("a") == "dm"
    assert alias_map.get("b") == "ex"


def test_build_alias_map_as_keyword() -> None:
    """FROM table AS alias form is resolved correctly."""
    # SAS: test_parser_relationships.py:test_build_alias_map_as_keyword
    sql = "SELECT * FROM patients AS p JOIN visits AS v ON p.id = v.pid"
    alias_map = _build_alias_map(sql)
    assert alias_map.get("p") == "patients"
    assert alias_map.get("v") == "visits"


def test_build_alias_map_schema_qualified() -> None:
    """Libref-qualified table names (lib.tbl) resolve to member name only."""
    # SAS: test_parser_relationships.py:test_build_alias_map_schema_qualified
    sql = "SELECT * FROM work.dm a JOIN work.ex b ON a.id = b.id"
    alias_map = _build_alias_map(sql)
    assert alias_map.get("a") == "dm"
    assert alias_map.get("b") == "ex"


# ── _extract_join_on_keys unit tests ─────────────────────────────────────────


def test_join_on_keys_single_join() -> None:
    """A single JOIN ON predicate produces one entry with correct table/col names."""
    # SAS: test_parser_relationships.py:test_join_on_keys_single_join
    sql = (
        "PROC SQL;\n"
        "    CREATE TABLE result AS\n"
        "    SELECT a.USUBJID, b.AVAL\n"
        "    FROM dm a JOIN ex b ON a.USUBJID = b.USUBJID;\n"
        "QUIT;"
    )
    keys = _extract_join_on_keys(sql)
    assert len(keys) == 1
    assert keys[0] == {
        "left_table": "dm",
        "right_table": "ex",
        "left_col": "usubjid",
        "right_col": "usubjid",
    }


def test_join_on_keys_no_join_returns_empty() -> None:
    """PROC SQL without a JOIN ON clause returns an empty list."""
    # SAS: test_parser_relationships.py:test_join_on_keys_no_join_returns_empty
    sql = "PROC SQL;\n    CREATE TABLE t AS SELECT * FROM src;\nQUIT;"
    assert _extract_join_on_keys(sql) == []


def test_join_on_keys_multiple_joins() -> None:
    """Multiple JOIN ON clauses produce one entry each."""
    # SAS: test_parser_relationships.py:test_join_on_keys_multiple_joins
    sql = (
        "PROC SQL;\n"
        "    SELECT a.id, b.name, c.score\n"
        "    FROM patients a\n"
        "    JOIN visits b ON a.id = b.pid\n"
        "    JOIN labs c ON a.id = c.sid;\n"
        "QUIT;"
    )
    keys = _extract_join_on_keys(sql)
    assert len(keys) == 2
    tables_left = {k["left_table"] for k in keys}
    assert "patients" in tables_left


def test_join_on_keys_unknown_alias_skipped() -> None:
    """Predicates with unresolvable aliases are silently skipped."""
    # SAS: test_parser_relationships.py:test_join_on_keys_unknown_alias_skipped
    # 'z' is not declared in any FROM/JOIN clause
    sql = "PROC SQL;\n    SELECT * FROM dm a ON a.id = z.id;\nQUIT;"
    keys = _extract_join_on_keys(sql)
    assert keys == []


def test_join_on_keys_case_insensitive() -> None:
    """ON keyword and alias references are matched case-insensitively."""
    # SAS: test_parser_relationships.py:test_join_on_keys_case_insensitive
    sql = "proc sql;\n    select * from dm A join ex B on A.usubjid = B.usubjid;\nquit;"
    keys = _extract_join_on_keys(sql)
    assert len(keys) == 1
    assert keys[0]["left_col"] == "usubjid"
    assert keys[0]["right_col"] == "usubjid"


# ── Integration via SASParser.parse ──────────────────────────────────────────


def test_parser_populates_merge_by_vars(parser: SASParser) -> None:
    """SASParser.parse() sets merge_by_vars on DATA step blocks with MERGE."""
    # SAS: test_parser_relationships.py:test_parser_populates_merge_by_vars
    sas = "DATA merged;\n    MERGE dm(in=a) ex(in=b);\n    BY USUBJID STUDYID;\nRUN;\n"
    result = parser.parse({"test.sas": sas})
    data_blocks = [b for b in result.blocks if b.block_type == BlockType.DATA_STEP]
    assert len(data_blocks) == 1
    assert data_blocks[0].merge_by_vars == ["usubjid", "studyid"]


def test_parser_merge_by_vars_empty_without_merge(parser: SASParser) -> None:
    """DATA step without MERGE has merge_by_vars == []."""
    # SAS: test_parser_relationships.py:test_parser_merge_by_vars_empty_without_merge
    sas = "DATA out;\n    SET src;\nRUN;\n"
    result = parser.parse({"test.sas": sas})
    data_blocks = [b for b in result.blocks if b.block_type == BlockType.DATA_STEP]
    assert data_blocks[0].merge_by_vars == []


def test_parser_populates_join_on_keys(parser: SASParser) -> None:
    """SASParser.parse() sets join_on_keys on PROC SQL blocks with JOIN ON."""
    # SAS: test_parser_relationships.py:test_parser_populates_join_on_keys
    sas = (
        "PROC SQL;\n"
        "    CREATE TABLE result AS\n"
        "    SELECT a.USUBJID\n"
        "    FROM dm a JOIN ex b ON a.USUBJID = b.USUBJID;\n"
        "QUIT;\n"
    )
    result = parser.parse({"test.sas": sas})
    sql_blocks = [b for b in result.blocks if b.block_type == BlockType.PROC_SQL]
    assert len(sql_blocks) == 1
    keys = sql_blocks[0].join_on_keys
    assert len(keys) == 1
    assert keys[0]["left_table"] == "dm"
    assert keys[0]["right_table"] == "ex"
    assert keys[0]["left_col"] == "usubjid"
    assert keys[0]["right_col"] == "usubjid"


def test_parser_join_on_keys_empty_without_join(parser: SASParser) -> None:
    """PROC SQL block without JOIN has join_on_keys == []."""
    # SAS: test_parser_relationships.py:test_parser_join_on_keys_empty_without_join
    sas = "PROC SQL;\n    CREATE TABLE t AS SELECT * FROM src;\nQUIT;\n"
    result = parser.parse({"test.sas": sas})
    sql_blocks = [b for b in result.blocks if b.block_type == BlockType.PROC_SQL]
    assert sql_blocks[0].join_on_keys == []


def test_parser_join_on_keys_multiple_joins(parser: SASParser) -> None:
    """PROC SQL with two JOIN ON clauses yields two join_on_keys entries."""
    # SAS: test_parser_relationships.py:test_parser_join_on_keys_multiple_joins
    sas = (
        "PROC SQL;\n"
        "    SELECT a.id, b.name, c.score\n"
        "    FROM patients a\n"
        "    JOIN visits b ON a.id = b.pid\n"
        "    JOIN labs c ON a.id = c.sid;\n"
        "QUIT;\n"
    )
    result = parser.parse({"test.sas": sas})
    sql_blocks = [b for b in result.blocks if b.block_type == BlockType.PROC_SQL]
    assert len(sql_blocks[0].join_on_keys) == 2
