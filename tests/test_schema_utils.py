"""Unit tests for src.backend.api.schema_utils — type mapping and pk/fk inference."""

from src.backend.api.schema_utils import (
    infer_pk_fk,
    map_python_dtype_to_sql,
    map_sas_to_semantic_type,
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
    """DM table with USUBJID gets USUBJID as PK."""
    tables = [
        _make_table("dm", ["USUBJID", "AGE"]),
    ]
    result = infer_pk_fk(tables, [])
    assert "USUBJID" in result["dm"]["pks"]


def test_infer_pk_fk_usubjid_non_dm_gets_fk() -> None:
    """Non-DM table with USUBJID gets USUBJID as FK pointing to dm.USUBJID."""
    tables = [
        _make_table("dm", ["USUBJID"]),
        _make_table("ex", ["USUBJID", "EXDOSE"]),
    ]
    result = infer_pk_fk(tables, [])
    assert result["ex"]["fks"].get("USUBJID") == "dm.USUBJID"


def test_infer_pk_fk_studyid_usubjid_compound_pk() -> None:
    """Table with both STUDYID and USUBJID gets compound PK."""
    tables = [
        _make_table("dm", ["STUDYID", "USUBJID", "AGE"]),
    ]
    result = infer_pk_fk(tables, [])
    pks = result["dm"]["pks"]
    assert "STUDYID" in pks
    assert "USUBJID" in pks


def test_infer_pk_fk_seq_rule_compound_pk() -> None:
    """Table with USUBJID + *SEQ column gets compound PK."""
    tables = [
        _make_table("ex", ["USUBJID", "EXSEQ", "EXDOSE"]),
    ]
    # ex is not a dm table → normally FK, but SEQ rule promotes it
    result = infer_pk_fk(tables, [])
    pks = result["ex"]["pks"]
    assert "EXSEQ" in pks


def test_infer_pk_fk_relationship_hint_sets_fk() -> None:
    """Relationship hint sets FK for left_table.key_column → right_table."""
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
    assert "USUBJID" in result["ex"]["fks"]


def test_infer_pk_fk_user_pk_override_takes_precedence() -> None:
    """User pk_overrides replaces inferred PKs."""
    tables = [
        _make_table("dm", ["USUBJID", "SUBJID"]),
    ]
    result = infer_pk_fk(tables, [], user_pk_overrides={"dm": ["SUBJID"]})
    assert result["dm"]["pks"] == ["SUBJID"]


def test_infer_pk_fk_user_fk_override_takes_precedence() -> None:
    """User fk_overrides replaces/adds FK entries."""
    tables = [
        _make_table("ex", ["USUBJID"]),
    ]
    result = infer_pk_fk(
        tables,
        [],
        user_fk_overrides={"ex.USUBJID": "sdtm_dm.USUBJID"},
    )
    assert result["ex"]["fks"]["USUBJID"] == "sdtm_dm.USUBJID"


def test_infer_pk_fk_empty_tables_returns_empty() -> None:
    """Empty tables list returns empty result."""
    result = infer_pk_fk([], [])
    assert result == {}
