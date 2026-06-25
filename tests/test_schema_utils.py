"""Unit tests for src.backend.api.schema_utils — type mapping and pk/fk inference."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from src.backend.api.schema_utils import (
    build_job_schema,
    infer_pk_fk,
    map_python_dtype_to_sql,
    map_sas_to_semantic_type,
    map_semantic_to_spark_type,
)


def test_character_is_string() -> None:
    assert map_sas_to_semantic_type("character", "$40.") == "String"


def test_character_no_format_is_string() -> None:
    assert map_sas_to_semantic_type("character", None) == "String"


def test_double_with_date_format() -> None:
    assert map_sas_to_semantic_type("double", "DATE9.") == "Date"


def test_double_with_datetime_format() -> None:
    assert map_sas_to_semantic_type("double", "DATETIME20.") == "Timestamp"


def test_double_with_decimal_format() -> None:
    assert map_sas_to_semantic_type("double", "COMMA12.2") == "Decimal"


def test_double_no_format_is_number() -> None:
    assert map_sas_to_semantic_type("double", None) == "Number"


def test_double_empty_format_is_number() -> None:
    assert map_sas_to_semantic_type("double", "") == "Number"


def test_iso8601_date() -> None:
    assert map_sas_to_semantic_type("double", "ISO8601DA10.") == "Date"


def test_time_is_timestamp() -> None:
    assert map_sas_to_semantic_type("double", "TIME8.") == "Timestamp"


def test_yymmdd_date() -> None:
    assert map_sas_to_semantic_type("double", "YYMMDD10.") == "Date"


def test_dollar_decimal_with_decimal_point() -> None:
    assert map_sas_to_semantic_type("double", "DOLLAR12.2") == "Decimal"


def test_dollar_no_decimal_point_is_number() -> None:
    # No "." within the format string itself → not Decimal
    assert map_sas_to_semantic_type("double", "DOLLAR12") == "Number"


def test_case_insensitive_date() -> None:
    assert map_sas_to_semantic_type("double", "date9.") == "Date"


def test_case_insensitive_datetime() -> None:
    assert map_sas_to_semantic_type("double", "datetime20.") == "Timestamp"


def test_empty_sas_type_is_unknown() -> None:
    """CSV/unknown files have no SAS type metadata; result must be 'Unknown', not 'Number'."""
    assert map_sas_to_semantic_type("", None) == "Unknown"


def test_empty_sas_type_with_format_is_unknown() -> None:
    """Empty sas_type takes priority over any format hint."""
    assert map_sas_to_semantic_type("", "DATE9.") == "Unknown"


def test_xport_string_type_maps_to_string() -> None:
    assert map_sas_to_semantic_type("string", None) == "String"


# ── map_python_dtype_to_sql ───────────────────────────────────────────────────


def test_object_maps_to_text() -> None:
    """object dtype → TEXT."""
    assert map_python_dtype_to_sql("object") == "TEXT"


def test_int64_maps_to_bigint() -> None:
    """int64 dtype → BIGINT."""
    assert map_python_dtype_to_sql("int64") == "BIGINT"


def test_int32_maps_to_bigint() -> None:
    """int32 dtype → BIGINT."""
    assert map_python_dtype_to_sql("int32") == "BIGINT"


def test_float64_maps_to_double_precision() -> None:
    """float64 dtype → DOUBLE PRECISION."""
    assert map_python_dtype_to_sql("float64") == "DOUBLE PRECISION"


def test_float32_maps_to_double_precision() -> None:
    """float32 dtype → DOUBLE PRECISION."""
    assert map_python_dtype_to_sql("float32") == "DOUBLE PRECISION"


def test_bool_maps_to_boolean() -> None:
    """bool dtype → BOOLEAN."""
    assert map_python_dtype_to_sql("bool") == "BOOLEAN"


def test_datetime64_ns_maps_to_timestamp() -> None:
    """datetime64[ns] dtype → TIMESTAMP."""
    assert map_python_dtype_to_sql("datetime64[ns]") == "TIMESTAMP"


def test_datetime64_us_maps_to_timestamp() -> None:
    """datetime64[us] dtype → TIMESTAMP."""
    assert map_python_dtype_to_sql("datetime64[us]") == "TIMESTAMP"


def test_unknown_dtype_maps_to_text() -> None:
    """Unrecognised dtype falls back to TEXT."""
    assert map_python_dtype_to_sql("category") == "TEXT"


def test_string_dtype_maps_to_text() -> None:
    """pandas StringDtype 'string' → TEXT."""
    assert map_python_dtype_to_sql("string") == "TEXT"


# ── infer_pk_fk ───────────────────────────────────────────────────────────────


def _make_table(
    name: str,
    columns: list[str],
    column_types: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "dataset_name": name,
        "columns": columns,
        "column_types": column_types or {},
        "target_columns": [],
    }


def test_infer_pk_fk_usubjid_dm_gets_pk() -> None:
    """DM table with USUBJID gets USUBJID as PK (lowercased)."""
    tables = [
        _make_table("dm", ["USUBJID", "AGE"]),
    ]
    result = infer_pk_fk(tables, [])
    assert "usubjid" in result["dm"]["pks"]


def test_infer_pk_fk_usubjid_non_dm_gets_fk() -> None:
    """Non-DM table with USUBJID gets USUBJID as FK pointing to dm.usubjid (lowercased)."""
    tables = [
        _make_table("dm", ["USUBJID"]),
        _make_table("ex", ["USUBJID", "EXDOSE"]),
    ]
    result = infer_pk_fk(tables, [])
    assert result["ex"]["fks"].get("usubjid") == "dm.usubjid"


def test_infer_pk_fk_studyid_usubjid_compound_pk() -> None:
    """Table with both STUDYID and USUBJID gets compound PK (lowercased)."""
    tables = [
        _make_table("dm", ["STUDYID", "USUBJID", "AGE"]),
    ]
    result = infer_pk_fk(tables, [])
    pks = result["dm"]["pks"]
    assert "studyid" in pks
    assert "usubjid" in pks


def test_infer_pk_fk_seq_rule_compound_pk() -> None:
    """Table with USUBJID + *SEQ column gets compound PK (lowercased)."""
    tables = [
        _make_table("ex", ["USUBJID", "EXSEQ", "EXDOSE"]),
    ]
    # ex is not a dm table → normally FK, but SEQ rule promotes it
    result = infer_pk_fk(tables, [])
    pks = result["ex"]["pks"]
    assert "exseq" in pks


def test_infer_pk_fk_relationship_hint_sets_fk() -> None:
    """Relationship hint sets FK for left_table.key_column → right_table (lowercased)."""
    tables = [
        _make_table("dm", ["USUBJID"]),
        _make_table("ex", ["USUBJID", "EXDOSE"]),
    ]
    relationships = [
        {
            "left_table": "ex",
            "right_table": "dm",
            "key_column": "USUBJID",
            "via_block_id": "b1",
            "relationship_type": "merge",
        }
    ]
    result = infer_pk_fk(tables, relationships)
    assert "usubjid" in result["ex"]["fks"]


def test_infer_pk_fk_user_pk_override_takes_precedence() -> None:
    """User pk_overrides replaces inferred PKs (lowercased)."""
    tables = [
        _make_table("dm", ["USUBJID", "SUBJID"]),
    ]
    result = infer_pk_fk(tables, [], user_pk_overrides={"dm": ["SUBJID"]})
    assert result["dm"]["pks"] == ["subjid"]


def test_infer_pk_fk_user_fk_override_takes_precedence() -> None:
    """User fk_overrides replaces/adds FK entries (lowercased)."""
    tables = [
        _make_table("ex", ["USUBJID"]),
    ]
    result = infer_pk_fk(
        tables,
        [],
        user_fk_overrides={"ex.USUBJID": "sdtm_dm.USUBJID"},
    )
    assert result["ex"]["fks"]["usubjid"] == "sdtm_dm.usubjid"


def test_infer_pk_fk_empty_tables_returns_empty() -> None:
    """Empty tables list returns empty result."""
    result = infer_pk_fk([], [])
    assert result == {}


# ── map_semantic_to_spark_type ────────────────────────────────────────────────


def test_spark_string() -> None:
    assert map_semantic_to_spark_type("String") == "StringType()"


def test_spark_date() -> None:
    assert map_semantic_to_spark_type("Date") == "DateType()"


def test_spark_timestamp() -> None:
    assert map_semantic_to_spark_type("Timestamp") == "TimestampType()"


def test_spark_decimal() -> None:
    assert map_semantic_to_spark_type("Decimal") == "DecimalType(18, 4)"


def test_spark_integer() -> None:
    assert map_semantic_to_spark_type("Integer") == "LongType()"


def test_spark_number() -> None:
    assert map_semantic_to_spark_type("Number") == "DoubleType()"


def test_spark_unknown_falls_back_to_string() -> None:
    assert map_semantic_to_spark_type("Unknown") == "StringType()"


def test_spark_empty_falls_back_to_string() -> None:
    assert map_semantic_to_spark_type("") == "StringType()"


# ── build_job_schema ──────────────────────────────────────────────────────────


def _make_mock_job(
    migration_plan: dict[str, Any],
    user_overrides: dict[str, Any] | None = None,
    lineage: dict[str, Any] | None = None,
) -> MagicMock:
    job = MagicMock()
    job.migration_plan = migration_plan
    job.user_overrides = user_overrides or {}
    job.lineage = lineage or {}
    return job


@pytest.mark.asyncio
async def test_build_job_schema_basic_columns() -> None:
    """build_job_schema returns one TableSchema per data_schema entry with correct columns."""
    plan: dict[str, Any] = {
        "libname_map": {},
        "data_schema": {
            "data/dm.sas7bdat": {
                "columns": ["USUBJID", "AGE"],
                "column_types": {"USUBJID": "character", "AGE": "double"},
                "column_labels": {},
                "column_formats": {},
                "row_count": 10,
            }
        },
        "relationships": [],
        "output_schema": {},
    }
    db = MagicMock()
    job = _make_mock_job(plan)
    tables = await build_job_schema(job, db)
    assert len(tables) == 1
    t = tables[0]
    assert t.dataset_name == "dm"
    assert t.row_count == 10
    col_names = [c.name for c in t.columns]
    assert col_names == ["USUBJID", "AGE"]
    assert t.columns[0].semantic_type == "String"
    assert t.columns[1].semantic_type == "Number"


@pytest.mark.asyncio
async def test_build_job_schema_applies_column_type_override() -> None:
    """build_job_schema applies user schema_overrides column_type_overrides."""
    plan: dict[str, Any] = {
        "libname_map": {},
        "data_schema": {
            "data/dm.sas7bdat": {
                "columns": ["AGE"],
                "column_types": {"AGE": "double"},
                "column_labels": {},
                "column_formats": {},
            }
        },
        "relationships": [],
        "output_schema": {},
    }
    overrides: dict[str, Any] = {
        "schema_overrides": {
            "data/dm.sas7bdat": {
                "column_type_overrides": {"AGE": "Integer"},
            }
        }
    }
    db = MagicMock()
    job = _make_mock_job(plan, user_overrides=overrides)
    tables = await build_job_schema(job, db)
    assert tables[0].columns[0].override_type == "Integer"


@pytest.mark.asyncio
async def test_build_job_schema_pure_output_appended() -> None:
    """build_job_schema appends placeholder TableSchema for pure output datasets."""
    plan: dict[str, Any] = {
        "libname_map": {},
        "data_schema": {},
        "relationships": [],
        "output_schema": {},
    }
    lineage: dict[str, Any] = {
        "pipeline_steps": [
            {"inputs": [], "outputs": ["summary"]},
        ]
    }
    db = MagicMock()
    job = _make_mock_job(plan, lineage=lineage)
    tables = await build_job_schema(job, db)
    assert any(t.dataset_name == "summary" for t in tables)
    summary = next(t for t in tables if t.dataset_name == "summary")
    assert summary.path == "output/summary"
    assert summary.schema_status == "not_run"


@pytest.mark.asyncio
async def test_build_job_schema_empty_plan_returns_empty() -> None:
    """build_job_schema returns empty list when migration_plan has no data_schema."""
    db = MagicMock()
    job = _make_mock_job({})
    tables = await build_job_schema(job, db)
    assert tables == []
