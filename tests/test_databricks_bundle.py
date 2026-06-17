"""Unit tests for src/backend/api/databricks_bundle.py.

Covers build_dataset_graph, render_dlt_pipeline, and render_databricks_yml
as pure-function tests — no database, no network, no side effects required.
"""

# SAS: tests/test_databricks_bundle.py:1

from dataclasses import dataclass, field
from typing import Any

import yaml
from src.backend.api.databricks_bundle import (
    _normalise_ds_name,
    _slugify,
    build_dataset_graph,
    render_databricks_yml,
    render_dlt_pipeline,
)
from src.backend.api.schemas import ColumnSchema, TableSchema

# ---------------------------------------------------------------------------
# Fixtures — minimal stubs
# ---------------------------------------------------------------------------


@dataclass
class FakeJob:
    """Lightweight stand-in for a SQLAlchemy Job ORM instance."""

    id: str = "test-job-id"
    name: str = "My Test Job"
    migration_plan: dict[str, Any] = field(default_factory=dict)


def _make_table_schema(
    dataset_name: str,
    target_schema: str = "public",
    columns: list[ColumnSchema] | None = None,
) -> TableSchema:
    return TableSchema(
        path=f"data/{dataset_name}.sas7bdat",
        dataset_name=dataset_name,
        target_schema=target_schema,
        columns=columns or [],
    )


# ---------------------------------------------------------------------------
# _normalise_ds_name
# ---------------------------------------------------------------------------


class TestNormaliseDs:
    def test_strips_libname_prefix(self) -> None:
        assert _normalise_ds_name("WORK.MYDS") == "myds"

    def test_already_plain(self) -> None:
        assert _normalise_ds_name("myds") == "myds"

    def test_lowercases(self) -> None:
        assert _normalise_ds_name("RAWDIR.DM_RAW") == "dm_raw"

    def test_no_double_dot(self) -> None:
        # Only the first segment (libname) is stripped.
        assert _normalise_ds_name("lib.sub.ds") == "sub.ds"


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_simple(self) -> None:
        assert _slugify("My Test Job") == "my_test_job"

    def test_special_chars(self) -> None:
        assert _slugify("Job-2024/Q1!") == "job_2024_q1"

    def test_empty_fallback(self) -> None:
        assert _slugify("!!!") == "job"


# ---------------------------------------------------------------------------
# build_dataset_graph
# ---------------------------------------------------------------------------


BLOCK_A = {
    "block_id": "blk_a",
    "source_file": "pipeline.sas",
    "start_line": 1,
    "input_datasets": ["rawdir.dm"],
    "output_datasets": ["WORK.DM_CLEAN"],
}

BLOCK_B = {
    "block_id": "blk_b",
    "source_file": "pipeline.sas",
    "start_line": 50,
    "input_datasets": ["WORK.DM_CLEAN", "rawdir.ex"],
    "output_datasets": ["WORK.DM_MERGED"],
}


class TestBuildDatasetGraph:
    def test_root_datasets_identified(self) -> None:
        graph = build_dataset_graph([BLOCK_A, BLOCK_B])
        assert "dm" in graph["root_datasets"]
        assert "ex" in graph["root_datasets"]

    def test_block_outputs_present(self) -> None:
        graph = build_dataset_graph([BLOCK_A, BLOCK_B])
        assert "dm_clean" in graph["block_outputs"]
        assert "dm_merged" in graph["block_outputs"]

    def test_edges_recorded(self) -> None:
        graph = build_dataset_graph([BLOCK_A, BLOCK_B])
        # dm_clean is an input to dm_merged
        assert ("dm_clean", "dm_merged") in graph["edges"]

    def test_topological_order(self) -> None:
        graph = build_dataset_graph([BLOCK_A, BLOCK_B])
        ordered = graph["ordered_datasets"]
        # dm_clean must appear before dm_merged
        assert ordered.index("dm_clean") < ordered.index("dm_merged")

    def test_block_for_output_mapping(self) -> None:
        graph = build_dataset_graph([BLOCK_A, BLOCK_B])
        assert graph["block_for_output"]["dm_clean"]["block_id"] == "blk_a"
        assert graph["block_for_output"]["dm_merged"]["block_id"] == "blk_b"

    def test_empty_block_plans(self) -> None:
        graph = build_dataset_graph([])
        assert graph["ordered_datasets"] == []
        assert graph["root_datasets"] == set()
        assert graph["block_outputs"] == set()
        assert graph["edges"] == []
        assert graph["block_for_output"] == {}

    def test_cycle_fallback_does_not_raise(self) -> None:
        # A → B → A
        cyclic_a = {
            **BLOCK_A,
            "input_datasets": ["WORK.DM_MERGED"],
            "output_datasets": ["WORK.DM_CLEAN"],
        }
        cyclic_b = {
            **BLOCK_B,
            "input_datasets": ["WORK.DM_CLEAN"],
            "output_datasets": ["WORK.DM_MERGED"],
        }
        graph = build_dataset_graph([cyclic_a, cyclic_b])
        # Should return something without raising.
        assert "ordered_datasets" in graph

    def test_deterministic(self) -> None:
        g1 = build_dataset_graph([BLOCK_A, BLOCK_B])
        g2 = build_dataset_graph([BLOCK_A, BLOCK_B])
        assert g1["ordered_datasets"] == g2["ordered_datasets"]


# ---------------------------------------------------------------------------
# render_dlt_pipeline
# ---------------------------------------------------------------------------


class TestRenderDltPipeline:
    def _make_job(self, block_plans: list[dict[str, Any]]) -> FakeJob:
        return FakeJob(migration_plan={"block_plans": block_plans})

    def test_module_header_present(self) -> None:
        job = self._make_job([BLOCK_A])
        code = render_dlt_pipeline(job, {"blk_a": "result = dm_clean_df"}, [])
        assert "import dlt" in code
        assert "DATABRICKS_DATA_ROOT" in code
        assert "from pyspark.sql.types import" in code

    def test_dlt_table_decorator_emitted(self) -> None:
        job = self._make_job([BLOCK_A])
        code = render_dlt_pipeline(job, {"blk_a": "result = dm_clean_df"}, [])
        assert "@dlt.table(" in code
        assert 'name="dm_clean"' in code

    def test_root_input_uses_spark_read(self) -> None:
        job = self._make_job([BLOCK_A])
        code = render_dlt_pipeline(job, {"blk_a": "pass"}, [])
        assert "spark.read.format" in code
        assert "DATABRICKS_DATA_ROOT" in code

    def test_inter_block_input_uses_dlt_read(self) -> None:
        job = self._make_job([BLOCK_A, BLOCK_B])
        code = render_dlt_pipeline(
            job,
            {"blk_a": "pass", "blk_b": "pass"},
            [],
        )
        assert 'dlt.read("dm_clean")' in code

    def test_zero_output_block_skipped(self) -> None:
        print_block = {
            "block_id": "blk_print",
            "source_file": "pipeline.sas",
            "start_line": 100,
            "input_datasets": ["WORK.DM_CLEAN"],
            "output_datasets": [],
        }
        job = self._make_job([BLOCK_A, print_block])
        code = render_dlt_pipeline(
            job,
            {"blk_a": "pass", "blk_print": "PROC PRINT DATA=work.dm_clean; RUN;"},
            [],
        )
        # No table for the print block.
        assert "blk_print" not in code

    def test_untranslatable_block_emits_stub(self) -> None:
        job = self._make_job([BLOCK_A])
        code = render_dlt_pipeline(
            job,
            {"blk_a": "# SAS-UNRECOGNIZED\nsome_code()"},
            [],
        )
        assert "NotImplementedError" in code

    def test_empty_code_emits_stub(self) -> None:
        job = self._make_job([BLOCK_A])
        code = render_dlt_pipeline(job, {"blk_a": ""}, [])
        assert "NotImplementedError" in code

    def test_schema_structtype_emitted(self) -> None:
        col = ColumnSchema(name="usubjid", sas_type="character", semantic_type="String")
        ts = _make_table_schema("dm_clean", columns=[col])
        job = self._make_job([BLOCK_A])
        code = render_dlt_pipeline(job, {"blk_a": "pass"}, [ts])
        assert "StructType" in code
        assert "StructField" in code
        assert '"usubjid"' in code

    def test_pk_expect_or_fail_emitted(self) -> None:
        col = ColumnSchema(name="usubjid", sas_type="character", semantic_type="String", is_pk=True)
        ts = _make_table_schema("dm_clean", columns=[col])
        job = self._make_job([BLOCK_A])
        code = render_dlt_pipeline(job, {"blk_a": "pass"}, [ts])
        assert "@dlt.expect_or_fail" in code
        assert "pk_usubjid_not_null" in code

    def test_multi_output_repeats_code(self) -> None:
        multi_block = {
            "block_id": "blk_multi",
            "source_file": "pipeline.sas",
            "start_line": 10,
            "input_datasets": [],
            "output_datasets": ["WORK.OUT_A", "WORK.OUT_B"],
        }
        job = self._make_job([multi_block])
        code = render_dlt_pipeline(job, {"blk_multi": "x = 1"}, [])
        assert 'name="out_a"' in code
        assert 'name="out_b"' in code

    def test_deterministic(self) -> None:
        job = self._make_job([BLOCK_A, BLOCK_B])
        code_1 = render_dlt_pipeline(job, {"blk_a": "pass", "blk_b": "pass"}, [])
        code_2 = render_dlt_pipeline(job, {"blk_a": "pass", "blk_b": "pass"}, [])
        assert code_1 == code_2

    def test_no_output_blocks_returns_header_only(self) -> None:
        job = self._make_job([])
        code = render_dlt_pipeline(job, {}, [])
        assert "import dlt" in code
        assert "@dlt.table" not in code

    def test_override_type_surfaces_in_structfield(self) -> None:
        """ColumnSchema.override_type takes precedence over semantic_type in DLT StructField.

        A column with semantic_type="Number" (→ DoubleType) but override_type="Integer"
        must emit LongType() in the generated StructField, not DoubleType().
        """
        # SAS: tests/test_databricks_bundle.py:test_override_type_surfaces_in_structfield
        col = ColumnSchema(
            name="age",
            sas_type="double",
            semantic_type="Number",
            override_type="Integer",
        )
        ts = _make_table_schema("dm_clean", columns=[col])
        job = self._make_job([BLOCK_A])
        code = render_dlt_pipeline(job, {"blk_a": "pass"}, [ts])
        # Override "Integer" maps to LongType(), not DoubleType() from "Number".
        assert "LongType()" in code
        assert 'StructField("age", LongType(), nullable=True)' in code
        # The non-override default would have been DoubleType() — confirm it is absent.
        assert "DoubleType()" not in code

    def test_dlt_module_is_syntactically_valid(self) -> None:
        """render_dlt_pipeline output must be syntactically valid Python (compile check).

        Uses compile() / ast.parse() to guard against any template regression that
        would produce unparseable Python.
        """
        # SAS: tests/test_databricks_bundle.py:test_dlt_module_is_syntactically_valid
        col = ColumnSchema(name="usubjid", sas_type="character", semantic_type="String", is_pk=True)
        ts = _make_table_schema("dm_clean", columns=[col])
        job = self._make_job([BLOCK_A, BLOCK_B])
        code = render_dlt_pipeline(
            job,
            {"blk_a": "result = dm_df.rename(columns={'id': 'usubjid'})", "blk_b": "pass"},
            [ts],
        )
        # Raises SyntaxError if the generated source is not valid Python.
        try:
            compile(code, "<dlt_pipeline>", "exec")
        except SyntaxError as exc:
            raise AssertionError(f"render_dlt_pipeline produced invalid Python: {exc}") from exc


# ---------------------------------------------------------------------------
# render_databricks_yml
# ---------------------------------------------------------------------------


class TestRenderDatabricksYml:
    def _make_job(self, name: str = "My Test Job") -> FakeJob:
        return FakeJob(name=name)

    def _parse(self, yml: str) -> dict[str, Any]:
        result: dict[str, Any] = yaml.safe_load(yml)
        return result

    def test_valid_yaml(self) -> None:
        job = self._make_job()
        yml = render_databricks_yml(job, {}, [])
        doc = self._parse(yml)
        assert isinstance(doc, dict)

    def test_bundle_name(self) -> None:
        job = self._make_job("My Test Job")
        doc = self._parse(render_databricks_yml(job, {}, []))
        assert doc["bundle"]["name"] == "rosetta_my_test_job"

    def test_pipeline_resource_present(self) -> None:
        job = self._make_job()
        doc = self._parse(render_databricks_yml(job, {}, []))
        pipelines = doc["resources"]["pipelines"]
        assert "rosetta_my_test_job_pipeline" in pipelines

    def test_job_resource_present(self) -> None:
        job = self._make_job()
        doc = self._parse(render_databricks_yml(job, {}, []))
        jobs = doc["resources"]["jobs"]
        assert "rosetta_my_test_job_job" in jobs

    def test_schedule_present(self) -> None:
        job = self._make_job()
        doc = self._parse(render_databricks_yml(job, {}, []))
        schedule = doc["resources"]["jobs"]["rosetta_my_test_job_job"]["schedule"]
        assert "quartz_cron_expression" in schedule
        assert schedule["timezone_id"] == "UTC"

    def test_pipeline_references_dlt_file(self) -> None:
        job = self._make_job()
        doc = self._parse(render_databricks_yml(job, {}, []))
        libs = doc["resources"]["pipelines"]["rosetta_my_test_job_pipeline"]["libraries"]
        assert any("rosetta_my_test_job_dlt.py" in str(lib) for lib in libs)

    def test_target_schema_default_from_table_schema(self) -> None:
        ts = _make_table_schema("dm", target_schema="sdtm")
        job = self._make_job()
        doc = self._parse(render_databricks_yml(job, {}, [ts]))
        assert doc["variables"]["target_schema"]["default"] == "sdtm"

    def test_target_schema_fallback_to_slug(self) -> None:
        # No schema or schema with default "public" → fallback to slug.
        ts = _make_table_schema("dm", target_schema="public")
        job = self._make_job("My Test Job")
        doc = self._parse(render_databricks_yml(job, {}, [ts]))
        assert doc["variables"]["target_schema"]["default"] == "my_test_job"

    def test_serverless_true(self) -> None:
        job = self._make_job()
        doc = self._parse(render_databricks_yml(job, {}, []))
        pipeline = doc["resources"]["pipelines"]["rosetta_my_test_job_pipeline"]
        assert pipeline["serverless"] is True

    def test_deterministic(self) -> None:
        ts = _make_table_schema("dm", target_schema="sdtm")
        job = self._make_job()
        yml_1 = render_databricks_yml(job, {}, [ts])
        yml_2 = render_databricks_yml(job, {}, [ts])
        assert yml_1 == yml_2

    def test_pipeline_id_references_pipeline_resource(self) -> None:
        job = self._make_job()
        doc = self._parse(render_databricks_yml(job, {}, []))
        tasks = doc["resources"]["jobs"]["rosetta_my_test_job_job"]["tasks"]
        pipeline_id = tasks[0]["pipeline_task"]["pipeline_id"]
        assert "rosetta_my_test_job_pipeline" in pipeline_id

    def test_variables_block_has_three_entries(self) -> None:
        job = self._make_job()
        doc = self._parse(render_databricks_yml(job, {}, []))
        assert set(doc["variables"].keys()) == {"catalog", "target_schema", "storage_root"}
