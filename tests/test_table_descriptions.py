"""Unit tests for derive_table_descriptions and generate_create_table COMMENT clause."""

# SAS: tests/test_table_descriptions.py:1

from src.backend.api.schema_utils import derive_table_descriptions
from src.worker.engine.ddl_generator import generate_create_table

# ── derive_table_descriptions ────────────────────────────────────────────────


def test_output_table_gets_block_rationale() -> None:
    data_schema: dict[str, dict[str, object]] = {
        "uploads/job1/adsl.csv": {
            "columns": ["usubjid"],
            "column_labels": {},
            "row_count": None,
        }
    }
    plan: dict[str, object] = {
        "blocks": [{"rationale": "Build ADSL subject-level dataset.", "output_datasets": ["adsl"]}]
    }
    result = derive_table_descriptions(data_schema, plan)
    assert result["uploads/job1/adsl.csv"] == "Build ADSL subject-level dataset."


def test_source_table_uses_column_labels() -> None:
    data_schema: dict[str, dict[str, object]] = {
        "raw/dm_raw.xpt": {
            "columns": ["usubjid", "age"],
            "column_labels": {"usubjid": "Subject Identifier", "age": "Age at Screening"},
            "row_count": 150,
        }
    }
    plan: dict[str, object] = {"blocks": []}
    result = derive_table_descriptions(data_schema, plan)
    desc = result["raw/dm_raw.xpt"]
    assert "Subject Identifier" in desc
    assert "150" in desc


def test_source_table_fallback_when_no_labels() -> None:
    data_schema: dict[str, dict[str, object]] = {
        "raw/ae.xpt": {"columns": ["usubjid"], "column_labels": {}, "row_count": None}
    }
    plan: dict[str, object] = {"blocks": []}
    result = derive_table_descriptions(data_schema, plan)
    assert "SAS source dataset" in result["raw/ae.xpt"]


def test_empty_plan_no_crash() -> None:
    result = derive_table_descriptions({}, {})
    assert result == {}


# ── generate_create_table COMMENT ────────────────────────────────────────────


def test_ddl_with_description_contains_comment() -> None:
    cols = [{"name": "id", "semantic_type": "Integer"}]
    ddl = generate_create_table("patients", "public", cols, description="Patient demographics.")
    assert "COMMENT 'Patient demographics.'" in ddl


def test_ddl_without_description_has_no_comment() -> None:
    cols = [{"name": "id", "semantic_type": "Integer"}]
    ddl = generate_create_table("patients", "public", cols)
    assert "COMMENT" not in ddl


def test_ddl_description_escapes_single_quotes() -> None:
    cols = [{"name": "id", "semantic_type": "Integer"}]
    ddl = generate_create_table("t", "s", cols, description="It's a test.")
    assert "It''s a test." in ddl
