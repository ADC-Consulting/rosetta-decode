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
        "block_plans": [
            {"rationale": "Build ADSL subject-level dataset.", "output_datasets": ["adsl"]}
        ]
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
    plan: dict[str, object] = {"block_plans": []}
    result = derive_table_descriptions(data_schema, plan)
    desc = result["raw/dm_raw.xpt"]
    assert "Subject Identifier" in desc
    assert "150" in desc


def test_source_table_fallback_when_no_labels() -> None:
    data_schema: dict[str, dict[str, object]] = {
        "raw/ae.xpt": {"columns": ["usubjid"], "column_labels": {}, "row_count": None}
    }
    plan: dict[str, object] = {"block_plans": []}
    result = derive_table_descriptions(data_schema, plan)
    assert "SAS source dataset" in result["raw/ae.xpt"]


def test_output_dataset_libname_prefix_stripped() -> None:
    data_schema: dict[str, dict[str, object]] = {
        "data/output/customer_revenue_daily.parquet": {
            "columns": ["CUSTOMER_ID"],
            "column_labels": {},
            "row_count": None,
        }
    }
    plan: dict[str, object] = {
        "block_plans": [
            {
                "rationale": "Daily revenue aggregation per customer in EUR.",
                "output_datasets": ["outdir.customer_revenue_daily"],
            }
        ]
    }
    result = derive_table_descriptions(data_schema, plan)
    assert result["data/output/customer_revenue_daily.parquet"] == (
        "Daily revenue aggregation per customer in EUR."
    )


def test_dataset_summaries_take_priority_over_rationale() -> None:
    data_schema: dict[str, dict[str, object]] = {
        "data/output/customer_revenue_daily.parquet": {
            "columns": ["CUSTOMER_ID"],
            "column_labels": {},
            "row_count": 39874,
        }
    }
    plan: dict[str, object] = {
        "block_plans": [
            {
                "rationale": "GROUP BY aggregation with INNER JOIN.",
                "output_datasets": ["outdir.customer_revenue_daily"],
            }
        ]
    }
    lineage: dict[str, object] = {
        "dataset_summaries": {
            "outdir.customer_revenue_daily": "Daily revenue per customer in EUR — 39,874 rows"
        }
    }
    result = derive_table_descriptions(data_schema, plan, lineage=lineage)
    assert result["data/output/customer_revenue_daily.parquet"] == (
        "Daily revenue per customer in EUR — 39,874 rows"
    )


def test_pipeline_step_description_used_when_no_dataset_summary() -> None:
    data_schema: dict[str, dict[str, object]] = {
        "data/output/category_revenue.parquet": {
            "columns": ["CATEGORY"],
            "column_labels": {},
            "row_count": 12,
        }
    }
    plan: dict[str, object] = {"block_plans": []}
    lineage: dict[str, object] = {
        "pipeline_steps": [
            {
                "description": "Aggregate revenue by product category.",
                "outputs": ["category_revenue"],
            }
        ]
    }
    result = derive_table_descriptions(data_schema, plan, lineage=lineage)
    assert result["data/output/category_revenue.parquet"] == (
        "Aggregate revenue by product category."
    )


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
