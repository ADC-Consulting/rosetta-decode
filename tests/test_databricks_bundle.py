"""Unit tests for src/backend/api/databricks_bundle.py.

Covers build_dataset_graph, render_dlt_pipeline, and render_databricks_yml
as pure-function tests — no database, no network, no side effects required.
"""

# SAS: tests/test_databricks_bundle.py:1

import ast
from dataclasses import dataclass, field
from typing import Any

import yaml
from src.backend.api.databricks_bundle import (
    DeploymentTarget,
    _normalise_ds_name,
    _slugify,
    bind_inter_block_inputs,
    build_dataset_graph,
    build_job_compute,
    build_pipeline_compute,
    render_databricks_yml,
    render_databricks_yml_spark_job,
    render_dlt_pipeline,
    render_spark_job_modules,
    resolve_deployment_target,
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


def _dlt_code(job: FakeJob, per_block_code: dict[str, str], schema: list[Any]) -> str:
    """Join all DLT module values into one string for single-source-file assertions."""
    return "\n".join(render_dlt_pipeline(job, per_block_code, schema).values())


class TestRenderDltPipeline:
    def _make_job(self, block_plans: list[dict[str, Any]]) -> FakeJob:
        return FakeJob(migration_plan={"block_plans": block_plans})

    def test_module_header_present(self) -> None:
        job = self._make_job([BLOCK_A])
        code = _dlt_code(job, {"blk_a": "result = dm_clean_df"}, [])
        assert "import dlt" in code
        assert "DATABRICKS_DATA_ROOT" in code
        assert "from pyspark.sql.types import" in code

    def test_dlt_table_decorator_emitted(self) -> None:
        job = self._make_job([BLOCK_A])
        code = _dlt_code(job, {"blk_a": "result = dm_clean_df"}, [])
        assert "@dlt.table(" in code
        assert 'name="dm_clean"' in code

    def test_root_input_gets_no_bind_line(self) -> None:
        # F76 S-0: root inputs are NOT bound by the renderer — the portable block
        # code reads them itself via DATA_ROOT. No `<stem>_df` / spark.read bind.
        job = self._make_job([BLOCK_A])
        code = _dlt_code(job, {"blk_a": "result = dm"}, [])
        assert "spark.read.format" not in code
        assert "dm_df" not in code
        assert "dm = dlt.read" not in code  # dm is a root, not inter-block

    def test_inter_block_input_uses_dlt_read_by_bare_stem(self) -> None:
        # F76 S-0: inter-block inputs bound by the BARE STEM (not <stem>_df).
        job = self._make_job([BLOCK_A, BLOCK_B])
        code = _dlt_code(
            job,
            {"blk_a": "result = dm", "blk_b": "result = dm_clean"},
            [],
        )
        assert 'dm_clean = dlt.read("dm_clean")' in code
        assert "dm_clean_df" not in code

    def test_dlt_function_ends_with_return_result(self) -> None:
        # F76 S-0: each @dlt.table function must `return result`.
        job = self._make_job([BLOCK_A])
        code = _dlt_code(job, {"blk_a": "result = dm"}, [])
        assert "    return result" in code

    def test_zero_output_block_skipped(self) -> None:
        print_block = {
            "block_id": "blk_print",
            "source_file": "pipeline.sas",
            "start_line": 100,
            "input_datasets": ["WORK.DM_CLEAN"],
            "output_datasets": [],
        }
        job = self._make_job([BLOCK_A, print_block])
        code = _dlt_code(
            job,
            {"blk_a": "pass", "blk_print": "PROC PRINT DATA=work.dm_clean; RUN;"},
            [],
        )
        # No table for the print block.
        assert "blk_print" not in code

    def test_untranslatable_block_emits_stub(self) -> None:
        job = self._make_job([BLOCK_A])
        code = _dlt_code(
            job,
            {"blk_a": "# SAS-UNRECOGNIZED\nsome_code()"},
            [],
        )
        assert "NotImplementedError" in code

    def test_empty_code_emits_stub(self) -> None:
        job = self._make_job([BLOCK_A])
        code = _dlt_code(job, {"blk_a": ""}, [])
        assert "NotImplementedError" in code

    def test_schema_structtype_emitted(self) -> None:
        col = ColumnSchema(name="usubjid", sas_type="character", semantic_type="String")
        ts = _make_table_schema("dm_clean", columns=[col])
        job = self._make_job([BLOCK_A])
        code = _dlt_code(job, {"blk_a": "pass"}, [ts])
        assert "StructType" in code
        assert "StructField" in code
        assert '"usubjid"' in code

    def test_pk_expect_or_fail_emitted(self) -> None:
        col = ColumnSchema(name="usubjid", sas_type="character", semantic_type="String", is_pk=True)
        ts = _make_table_schema("dm_clean", columns=[col])
        job = self._make_job([BLOCK_A])
        code = _dlt_code(job, {"blk_a": "pass"}, [ts])
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
        code = _dlt_code(job, {"blk_multi": "x = 1"}, [])
        assert 'name="out_a"' in code
        assert 'name="out_b"' in code

    def test_deterministic(self) -> None:
        job = self._make_job([BLOCK_A, BLOCK_B])
        mods_1 = render_dlt_pipeline(job, {"blk_a": "pass", "blk_b": "pass"}, [])
        mods_2 = render_dlt_pipeline(job, {"blk_a": "pass", "blk_b": "pass"}, [])
        assert mods_1 == mods_2

    def test_no_output_blocks_returns_empty_dict(self) -> None:
        job = self._make_job([])
        mods = render_dlt_pipeline(job, {}, [])
        assert mods == {}

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
        code = _dlt_code(job, {"blk_a": "pass"}, [ts])
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
        mods = render_dlt_pipeline(
            job,
            {"blk_a": "result = dm_df.rename(columns={'id': 'usubjid'})", "blk_b": "pass"},
            [ts],
        )
        # Raises SyntaxError if any generated source is not valid Python.
        for path, source in mods.items():
            try:
                compile(source, path, "exec")
            except SyntaxError as exc:
                raise AssertionError(
                    f"render_dlt_pipeline produced invalid Python in {path}: {exc}"
                ) from exc


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

    def test_variables_block_has_four_entries(self) -> None:
        # F76 S-B: added the rosetta_data_root variable (drives ROSETTA_DATA_ROOT).
        job = self._make_job()
        doc = self._parse(render_databricks_yml(job, {}, []))
        assert set(doc["variables"].keys()) == {
            "catalog",
            "target_schema",
            "storage_root",
            "rosetta_data_root",
        }

    def test_pipeline_configuration_sets_rosetta_data_root(self) -> None:
        # F76 S-0: the DLT pipeline configuration must set ROSETTA_DATA_ROOT so the
        # portable block code's DATA_ROOT resolves on Databricks.
        job = self._make_job()
        doc = self._parse(render_databricks_yml(job, {}, []))
        cfg = doc["resources"]["pipelines"]["rosetta_my_test_job_pipeline"]["configuration"]
        assert cfg["ROSETTA_DATA_ROOT"] == "${var.rosetta_data_root}"


# ---------------------------------------------------------------------------
# F75 — deployment-target resolver (resolve_deployment_target, compute)
# ---------------------------------------------------------------------------


class TestResolveDeploymentTarget:
    def test_none_yields_azure_serverless_defaults(self) -> None:
        target = resolve_deployment_target(None)
        assert target.provider == "azure"
        assert target.ingestion_approach == "historical"
        assert target.compute_mode == "serverless"
        assert target.catalog == "main"
        assert target.schema is None

    def test_empty_dict_yields_defaults(self) -> None:
        assert resolve_deployment_target({}) == DeploymentTarget()

    def test_full_answers_round_trip(self) -> None:
        target = resolve_deployment_target(
            {
                "provider": "aws",
                "ingestion_approach": "staging",
                "compute_mode": "classic",
                "catalog": "analytics",
                "schema": "sdtm",
            }
        )
        assert target.provider == "aws"
        assert target.ingestion_approach == "staging"
        assert target.compute_mode == "classic"
        assert target.catalog == "analytics"
        assert target.schema == "sdtm"

    def test_unknown_provider_falls_back_to_azure(self) -> None:
        assert resolve_deployment_target({"provider": "oracle"}).provider == "azure"

    def test_partial_answers_fill_defaults(self) -> None:
        target = resolve_deployment_target({"provider": "gcp"})
        assert target.provider == "gcp"
        assert target.compute_mode == "serverless"
        assert target.catalog == "main"

    def test_provider_scheme_and_host(self) -> None:
        azure = resolve_deployment_target({"provider": "azure"})
        aws = resolve_deployment_target({"provider": "aws"})
        gcp = resolve_deployment_target({"provider": "gcp"})
        assert azure.scheme == "abfss"
        assert azure.storage_root.startswith("abfss://")
        assert "azuredatabricks.net" in azure.auth_host
        assert aws.scheme == "s3"
        assert aws.storage_root.startswith("s3://")
        assert "cloud.databricks.com" in aws.auth_host
        assert gcp.scheme == "gs"
        assert gcp.storage_root.startswith("gs://")
        assert "gcp.databricks.com" in gcp.auth_host


class TestBuildPipelineCompute:
    def test_serverless_block(self) -> None:
        target = resolve_deployment_target({"compute_mode": "serverless"})
        assert build_pipeline_compute(target) == {"serverless": True}

    def test_classic_block_has_placeholder_and_todo(self) -> None:
        target = resolve_deployment_target({"compute_mode": "classic", "provider": "azure"})
        block = build_pipeline_compute(target)
        assert "serverless" not in block
        cluster = block["clusters"][0]
        assert "Standard_DS3_v2" in cluster["node_type_id"]
        assert "TODO" in cluster["node_type_id"]
        assert cluster["autoscale"] == {"min_workers": 1, "max_workers": 2}

    def test_classic_node_type_per_provider(self) -> None:
        aws = build_pipeline_compute(
            resolve_deployment_target({"compute_mode": "classic", "provider": "aws"})
        )
        gcp = build_pipeline_compute(
            resolve_deployment_target({"compute_mode": "classic", "provider": "gcp"})
        )
        assert "i3.xlarge" in aws["clusters"][0]["node_type_id"]
        assert "n1-standard-4" in gcp["clusters"][0]["node_type_id"]


# ---------------------------------------------------------------------------
# F75 — cloud-aware generators
# ---------------------------------------------------------------------------


class TestCloudAwareGenerators:
    def _job(self) -> FakeJob:
        return FakeJob(
            migration_plan={
                "block_plans": [
                    {"block_id": "blk_a", "output_datasets": ["dm"], "input_datasets": ["raw"]}
                ]
            }
        )

    def _yml(self, target: DeploymentTarget) -> dict[str, Any]:
        job = FakeJob(name="My Test Job")
        doc: dict[str, Any] = yaml.safe_load(render_databricks_yml(job, {}, [], None, target))
        return doc

    def test_each_provider_scheme_in_both_files(self) -> None:
        for provider, scheme in (("azure", "abfss"), ("aws", "s3"), ("gcp", "gs")):
            target = resolve_deployment_target({"provider": provider})
            dlt_mods = render_dlt_pipeline(self._job(), {"blk_a": "x = 1"}, [], target)
            dlt_src = "\n".join(dlt_mods.values())
            doc = self._yml(target)
            storage_root = doc["variables"]["storage_root"]["default"]
            assert f"{scheme}://" in storage_root, provider
            assert f"{scheme}://" in dlt_src, provider

    def test_serverless_vs_classic_compute_block(self) -> None:
        job = FakeJob(name="My Test Job")
        serverless = yaml.safe_load(
            render_databricks_yml(
                job, {}, [], None, resolve_deployment_target({"compute_mode": "serverless"})
            )
        )["resources"]["pipelines"]["rosetta_my_test_job_pipeline"]
        classic = yaml.safe_load(
            render_databricks_yml(
                job, {}, [], None, resolve_deployment_target({"compute_mode": "classic"})
            )
        )["resources"]["pipelines"]["rosetta_my_test_job_pipeline"]
        assert serverless["serverless"] is True
        assert "serverless" not in classic
        assert "clusters" in classic

    def test_catalog_and_schema_override(self) -> None:
        target = resolve_deployment_target({"catalog": "analytics", "schema": "sdtm"})
        doc = self._yml(target)
        assert doc["variables"]["catalog"]["default"] == "analytics"
        assert doc["variables"]["target_schema"]["default"] == "sdtm"

    def test_schema_falls_back_to_table_schema_when_absent(self) -> None:
        ts = _make_table_schema("dm", target_schema="sdtm")
        job = FakeJob(name="My Test Job")
        doc = yaml.safe_load(
            render_databricks_yml(job, {}, [ts], None, resolve_deployment_target(None))
        )
        assert doc["variables"]["target_schema"]["default"] == "sdtm"


# ---------------------------------------------------------------------------
# F75 — REGRESSION LOCK: absent target == azure/serverless default == F74 bytes
# ---------------------------------------------------------------------------


class TestRegressionLockDefaultBytes:
    def _job(self) -> FakeJob:
        return FakeJob(
            name="My Test Job",
            migration_plan={
                "block_plans": [
                    {"block_id": "blk_a", "output_datasets": ["dm"], "input_datasets": ["raw"]}
                ]
            },
        )

    def test_yml_none_target_equals_azure_serverless_default(self) -> None:
        job = self._job()
        # No target argument at all (F74 direct-caller path).
        legacy = render_databricks_yml(job, {}, [])
        # Explicit azure/serverless default target.
        defaulted = render_databricks_yml(job, {}, [], None, resolve_deployment_target(None))
        assert legacy == defaulted

    def test_dlt_none_target_equals_azure_serverless_default(self) -> None:
        job = self._job()
        legacy = render_dlt_pipeline(job, {"blk_a": "x = 1"}, [])
        defaulted = render_dlt_pipeline(
            job, {"blk_a": "x = 1"}, [], resolve_deployment_target(None)
        )
        assert legacy == defaulted

    def test_default_yml_preserves_f74_azure_literals(self) -> None:
        job = self._job()
        yml = render_databricks_yml(job, {}, [])
        # F74 byte landmarks — must not drift.
        assert "abfss://data@<storage>.dfs.core.windows.net/  # TODO: set storage account" in yml
        assert "Root ABFSS path for source Delta tables" in yml
        assert "serverless: true" in yml

    def test_default_dlt_preserves_f74_azure_literal(self) -> None:
        job = self._job()
        dlt_mods = render_dlt_pipeline(job, {"blk_a": "x = 1"}, [])
        dlt_src = next(iter(dlt_mods.values()))
        assert (
            'DATABRICKS_DATA_ROOT = os.environ.get("DATABRICKS_DATA_ROOT", '
            '"abfss://data@<storage>.dfs.core.windows.net/")  # TODO: set storage account'
        ) in dlt_src

    def test_byte_reproducible_on_second_build(self) -> None:
        job = self._job()
        target = resolve_deployment_target({"provider": "aws", "compute_mode": "classic"})
        assert render_databricks_yml(job, {}, [], None, target) == render_databricks_yml(
            job, {}, [], None, target
        )
        assert render_dlt_pipeline(job, {"blk_a": "x = 1"}, [], target) == render_dlt_pipeline(
            job, {"blk_a": "x = 1"}, [], target
        )


# ---------------------------------------------------------------------------
# F76 — name-binding helper for runnability checks
# ---------------------------------------------------------------------------


def _assigned_names(tree: ast.AST) -> set[str]:
    """Return the set of names bound by assignment/import in a module tree."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.FunctionDef):
            names.add(node.name)
    return names


# ---------------------------------------------------------------------------
# F76 — bind_inter_block_inputs
# ---------------------------------------------------------------------------


class TestBindInterBlockInputs:
    def test_dlt_binds_inter_block_by_bare_stem(self) -> None:
        lines = bind_inter_block_inputs(["WORK.DM_CLEAN", "rawdir.ex"], {"dm_clean"}, "dlt")
        assert lines == ['dm_clean = dlt.read("dm_clean")']

    def test_job_binds_inter_block_via_table(self) -> None:
        lines = bind_inter_block_inputs(["WORK.DM_CLEAN"], {"dm_clean"}, "job")
        assert lines == ['dm_clean = spark.read.table(f"{CATALOG}.{SCHEMA}.dm_clean")']

    def test_root_inputs_get_no_bind(self) -> None:
        # ex is a root (not in block_outputs) → no bind line.
        assert bind_inter_block_inputs(["rawdir.ex"], {"dm_clean"}, "dlt") == []

    def test_sorted_and_deduped(self) -> None:
        lines = bind_inter_block_inputs(["WORK.B", "WORK.A", "work.a"], {"a", "b"}, "dlt")
        assert lines == ['a = dlt.read("a")', 'b = dlt.read("b")']


# ---------------------------------------------------------------------------
# F76 S-0 — DLT runnability (binding + return + no hardcoded path)
# ---------------------------------------------------------------------------


class TestDltRunnability:
    def _job(self, plans: list[dict[str, Any]]) -> FakeJob:
        return FakeJob(migration_plan={"block_plans": plans})

    def test_no_literal_workspace_data_path(self) -> None:
        job = self._job([BLOCK_A, BLOCK_B])
        code = _dlt_code(job, {"blk_a": "result = dm", "blk_b": "result = dm_clean"}, [])
        assert "/workspace/data" not in code

    def test_every_referenced_input_stem_is_bound(self) -> None:
        # BLOCK_B reads dm_clean (inter-block). The block code references dm_clean;
        # the renderer must bind it so ast/name resolution finds no free input stem.
        job = self._job([BLOCK_A, BLOCK_B])
        code = _dlt_code(
            job,
            {"blk_a": "result = dm", "blk_b": "result = dm_clean.filter(F.col('x') > 0)"},
            [],
        )
        tree = ast.parse(code)
        # Locate the dm_merged function (consumer of dm_clean).
        fn = next(
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "dm_merged"
        )
        bound = _assigned_names(fn)
        assert "dm_clean" in bound, "inter-block input dm_clean must be bound in the function"
        assert "result" in bound


# ---------------------------------------------------------------------------
# F76 S-B — build_job_compute
# ---------------------------------------------------------------------------


class TestBuildJobCompute:
    def test_serverless_is_empty(self) -> None:
        assert build_job_compute(resolve_deployment_target({"compute_mode": "serverless"})) == {}

    def test_classic_one_shared_cluster(self) -> None:
        block = build_job_compute(
            resolve_deployment_target({"compute_mode": "classic", "provider": "aws"})
        )
        clusters = block["job_clusters"]
        assert len(clusters) == 1
        entry = clusters[0]
        assert entry["job_cluster_key"] == "shared"
        assert "i3.xlarge" in entry["new_cluster"]["node_type_id"]
        assert "TODO" in entry["new_cluster"]["node_type_id"]
        assert entry["new_cluster"]["autoscale"] == {"min_workers": 1, "max_workers": 2}
        assert "TODO" in entry["new_cluster"]["spark_version"]


# ---------------------------------------------------------------------------
# F76 S-C — render_spark_job_modules
# ---------------------------------------------------------------------------


class TestRenderSparkJobModules:
    def _job(self, plans: list[dict[str, Any]]) -> FakeJob:
        return FakeJob(migration_plan={"block_plans": plans})

    def test_one_module_per_output_dataset(self) -> None:
        job = self._job([BLOCK_A, BLOCK_B])
        mods = render_spark_job_modules(
            job, {"blk_a": "result = dm", "blk_b": "result = dm_clean"}, []
        )
        assert set(mods.keys()) == {"jobs/pipeline/dm_clean.py", "jobs/pipeline/dm_merged.py"}

    def test_root_input_no_bind_inter_block_bound(self) -> None:
        job = self._job([BLOCK_A, BLOCK_B])
        mods = render_spark_job_modules(
            job, {"blk_a": "result = dm", "blk_b": "result = dm_clean"}, []
        )
        # dm_clean module: dm is a root → no spark.read.table for dm.
        a = mods["jobs/pipeline/dm_clean.py"]
        assert "spark.read.table" not in a
        # dm_merged module: dm_clean is inter-block → bound via spark.read.table.
        b = mods["jobs/pipeline/dm_merged.py"]
        assert 'dm_clean = spark.read.table(f"{CATALOG}.{SCHEMA}.dm_clean")' in b

    def test_savetable_target_and_top_level_code(self) -> None:
        job = self._job([BLOCK_A])
        mods = render_spark_job_modules(job, {"blk_a": "result = dm"}, [])
        src = mods["jobs/pipeline/dm_clean.py"]
        assert 'saveAsTable(f"{CATALOG}.{SCHEMA}.dm_clean")' in src
        assert "result = dm" in src
        assert "SparkSession.builder.getOrCreate()" in src

    def test_no_literal_workspace_data_path(self) -> None:
        job = self._job([BLOCK_A])
        mods = render_spark_job_modules(job, {"blk_a": "result = dm"}, [])
        assert "/workspace/data" not in mods["jobs/pipeline/dm_clean.py"]

    def test_zero_output_block_skipped(self) -> None:
        print_block = {
            "block_id": "blk_print",
            "source_file": "p.sas",
            "start_line": 9,
            "input_datasets": ["WORK.DM_CLEAN"],
            "output_datasets": [],
        }
        job = self._job([BLOCK_A, print_block])
        mods = render_spark_job_modules(
            job, {"blk_a": "result = dm", "blk_print": "PROC PRINT"}, []
        )
        assert set(mods.keys()) == {"jobs/pipeline/dm_clean.py"}

    def test_untranslatable_raises(self) -> None:
        job = self._job([BLOCK_A])
        mods = render_spark_job_modules(job, {"blk_a": "# SAS-UNRECOGNIZED\nx()"}, [])
        src = mods["jobs/pipeline/dm_clean.py"]
        assert "raise NotImplementedError" in src
        assert "saveAsTable" not in src

    def test_multi_output_produces_n_modules(self) -> None:
        multi = {
            "block_id": "blk_multi",
            "source_file": "p.sas",
            "start_line": 1,
            "input_datasets": [],
            "output_datasets": ["WORK.OUT_A", "WORK.OUT_B"],
        }
        job = self._job([multi])
        mods = render_spark_job_modules(job, {"blk_multi": "result = 1"}, [])
        # Documented shared-result caveat: same `result` written to each table.
        assert set(mods.keys()) == {"jobs/p/out_a.py", "jobs/p/out_b.py"}
        assert 'saveAsTable(f"{CATALOG}.{SCHEMA}.out_a")' in mods["jobs/p/out_a.py"]
        assert 'saveAsTable(f"{CATALOG}.{SCHEMA}.out_b")' in mods["jobs/p/out_b.py"]

    def test_each_module_is_syntactically_valid(self) -> None:
        job = self._job([BLOCK_A, BLOCK_B])
        mods = render_spark_job_modules(
            job,
            {
                "blk_a": "result = dm.withColumn('x', F.lit(1))",
                "blk_b": "result = dm_clean.join(ex, 'usubjid')",
            },
            [],
        )
        for src in mods.values():
            ast.parse(src)  # raises SyntaxError on regression

    def test_deterministic(self) -> None:
        job = self._job([BLOCK_A, BLOCK_B])
        code = {"blk_a": "result = dm", "blk_b": "result = dm_clean"}
        assert render_spark_job_modules(job, code, []) == render_spark_job_modules(job, code, [])


# ---------------------------------------------------------------------------
# F76 S-D — render_databricks_yml_spark_job
# ---------------------------------------------------------------------------


class TestRenderDatabricksYmlSparkJob:
    def _job(self) -> FakeJob:
        return FakeJob(
            name="My Test Job",
            migration_plan={"block_plans": [BLOCK_A, BLOCK_B]},
        )

    def _doc(self, target: DeploymentTarget) -> dict[str, Any]:
        job = self._job()
        graph = build_dataset_graph([BLOCK_A, BLOCK_B])
        doc: dict[str, Any] = yaml.safe_load(
            render_databricks_yml_spark_job(job, graph, [], target)
        )
        return doc

    def test_no_pipelines_resource(self) -> None:
        doc = self._doc(resolve_deployment_target(None))
        assert "pipelines" not in doc["resources"]
        assert "jobs" in doc["resources"]

    def test_tasks_and_depends_on_dag(self) -> None:
        doc = self._doc(resolve_deployment_target(None))
        job_res = doc["resources"]["jobs"]["rosetta_my_test_job_job"]
        tasks = {t["task_key"]: t for t in job_res["tasks"]}
        assert set(tasks.keys()) == {"dm_clean", "dm_merged"}
        # dm_merged depends on dm_clean (BLOCK_B consumes BLOCK_A output).
        assert tasks["dm_merged"]["depends_on"] == [{"task_key": "dm_clean"}]
        # dm_clean only depends on a root (dm) → no depends_on.
        assert "depends_on" not in tasks["dm_clean"]

    def test_task_runs_spark_python_file(self) -> None:
        doc = self._doc(resolve_deployment_target(None))
        tasks = doc["resources"]["jobs"]["rosetta_my_test_job_job"]["tasks"]
        t = next(t for t in tasks if t["task_key"] == "dm_clean")
        assert t["spark_python_task"]["python_file"] == "./jobs/pipeline/dm_clean.py"

    def test_classic_shared_cluster_attached(self) -> None:
        doc = self._doc(resolve_deployment_target({"compute_mode": "classic"}))
        job_res = doc["resources"]["jobs"]["rosetta_my_test_job_job"]
        assert "job_clusters" in job_res
        for t in job_res["tasks"]:
            assert t["job_cluster_key"] == "shared"

    def test_serverless_omits_job_cluster_key(self) -> None:
        doc = self._doc(resolve_deployment_target({"compute_mode": "serverless"}))
        job_res = doc["resources"]["jobs"]["rosetta_my_test_job_job"]
        assert "job_clusters" not in job_res
        for t in job_res["tasks"]:
            assert "job_cluster_key" not in t

    def test_classic_node_placeholder_per_provider(self) -> None:
        for provider, node in (("aws", "i3.xlarge"), ("gcp", "n1-standard-4")):
            doc = self._doc(
                resolve_deployment_target({"compute_mode": "classic", "provider": provider})
            )
            cluster = doc["resources"]["jobs"]["rosetta_my_test_job_job"]["job_clusters"][0]
            assert node in cluster["new_cluster"]["node_type_id"]

    def test_job_parameters_carry_env(self) -> None:
        doc = self._doc(resolve_deployment_target(None))
        params = {
            p["name"]: p["default"]
            for p in doc["resources"]["jobs"]["rosetta_my_test_job_job"]["parameters"]
        }
        assert params["ROSETTA_CATALOG"] == "${var.catalog}"
        assert params["ROSETTA_SCHEMA"] == "${var.target_schema}"
        assert params["ROSETTA_DATA_ROOT"] == "${var.rosetta_data_root}"

    def test_deterministic(self) -> None:
        job = self._job()
        graph = build_dataset_graph([BLOCK_A, BLOCK_B])
        target = resolve_deployment_target({"provider": "aws", "compute_mode": "classic"})
        assert render_databricks_yml_spark_job(
            job, graph, [], target
        ) == render_databricks_yml_spark_job(job, graph, [], target)


# ---------------------------------------------------------------------------
# Same-table fold — two writers of adam.adsl (build + in-place rewrite)
# ---------------------------------------------------------------------------

# Mirrors 05_build_adam_adsl.sas: build merge L39-44, in-place column reorder L46-58.
_BLK_BUILD = {
    "block_id": "blk_build",
    "source_file": "05_build_adam_adsl.sas",
    "start_line": 39,
    "input_datasets": ["work.adsl_age", "work.aesum"],
    "output_datasets": ["adam.adsl"],
}
_BLK_SORT = {
    "block_id": "blk_sort",
    "source_file": "05_build_adam_adsl.sas",
    "start_line": 46,
    "input_datasets": ["adam.adsl"],
    "output_datasets": ["adam.adsl"],
}
_PER_BLOCK_2WRITER = {
    "blk_build": "result = adsl_age.merge(aesum, on='usubjid', how='left')",
    "blk_sort": "result = adsl.sort_values('usubjid')",
}


class TestSameTableFold:
    """Two SAS blocks write the same table — fold, not duplicate."""

    # SAS: tests/test_databricks_bundle.py:TestSameTableFold

    def _job(self) -> FakeJob:
        return FakeJob(migration_plan={"block_plans": [_BLK_BUILD, _BLK_SORT]})

    # --- DLT ---

    def test_dlt_exactly_one_table_decorator(self) -> None:
        code = _dlt_code(self._job(), _PER_BLOCK_2WRITER, [])
        assert code.count("@dlt.table(") == 1
        assert code.count('name="adsl"') == 1

    def test_dlt_exactly_one_function_def(self) -> None:
        code = _dlt_code(self._job(), _PER_BLOCK_2WRITER, [])
        assert code.count("def adsl():") == 1

    def test_dlt_ast_valid(self) -> None:
        mods = render_dlt_pipeline(self._job(), _PER_BLOCK_2WRITER, [])
        for path, source in mods.items():
            try:
                ast.parse(source)
            except SyntaxError as exc:
                raise AssertionError(f"DLT fold produced invalid Python in {path}: {exc}") from exc

    def test_dlt_fold_handoff_line_present(self) -> None:
        # blk_build result handed to blk_sort via `adsl = result`.
        code = _dlt_code(self._job(), _PER_BLOCK_2WRITER, [])
        assert "adsl = result" in code

    def test_dlt_no_self_read(self) -> None:
        # blk_sort lists adam.adsl as input; renderer must not emit dlt.read("adsl")
        # inside def adsl() — that would be an invalid self-reference.
        code = _dlt_code(self._job(), _PER_BLOCK_2WRITER, [])
        assert 'dlt.read("adsl")' not in code

    def test_dlt_both_provenance_comments_present(self) -> None:
        # Per-stage # SAS: comments emitted for multi-writer chains.
        code = _dlt_code(self._job(), _PER_BLOCK_2WRITER, [])
        assert "# SAS: 05_build_adam_adsl.sas:39" in code
        assert "# SAS: 05_build_adam_adsl.sas:46" in code

    # --- Fold order (C1): start_line order, not list-position order ---

    def test_dlt_fold_order_by_start_line_not_list_position(self) -> None:
        # Swap list order: blk_sort (L46) first, blk_build (L39) second.
        # Fold must still execute blk_build before blk_sort (source-line order).
        job = FakeJob(migration_plan={"block_plans": [_BLK_SORT, _BLK_BUILD]})
        code = _dlt_code(job, _PER_BLOCK_2WRITER, [])
        build_pos = code.index("result = adsl_age.merge")
        sort_pos = code.index("result = adsl.sort_values")
        assert build_pos < sort_pos, "blk_build (L39) must precede blk_sort (L46)"

    # --- Multi-output-in-chain (C3): ambiguous result → stub ---

    def test_dlt_multi_output_in_chain_emits_stub(self) -> None:
        # blk_flags writes both adsl and adsl_flags; a second writer of adsl exists.
        # result is ambiguous → the adsl table must be a NotImplementedError stub.
        blk_flags = {
            "block_id": "blk_flags",
            "source_file": "x.sas",
            "start_line": 10,
            "input_datasets": [],
            "output_datasets": ["adam.adsl", "adam.adsl_flags"],
        }
        blk_sort2 = {
            "block_id": "blk_sort2",
            "source_file": "x.sas",
            "start_line": 20,
            "input_datasets": ["adam.adsl"],
            "output_datasets": ["adam.adsl"],
        }
        per_block: dict[str, str] = {
            "blk_flags": "result = spark.createDataFrame([])",
            "blk_sort2": "result = adsl.sort_values('x')",
        }
        job = FakeJob(migration_plan={"block_plans": [blk_flags, blk_sort2]})
        code = _dlt_code(job, per_block, [])
        # adsl has a multi-output co-writer → must be stubbed
        fn_start = code.index("def adsl():")
        fn_snippet = code[fn_start : fn_start + 300]
        assert "NotImplementedError" in fn_snippet

    # --- Job modules ---

    def test_job_modules_exactly_one_key(self) -> None:
        job = self._job()
        mods = render_spark_job_modules(job, _PER_BLOCK_2WRITER, [])
        assert "jobs/05_build_adam_adsl/adsl.py" in mods
        # No duplicate under any other key variant.
        assert len([k for k in mods if "adsl" in k]) == 1

    def test_job_module_contains_both_stage_code(self) -> None:
        job = self._job()
        mods = render_spark_job_modules(job, _PER_BLOCK_2WRITER, [])
        src = mods["jobs/05_build_adam_adsl/adsl.py"]
        assert "result = adsl_age.merge" in src
        assert "result = adsl.sort_values" in src

    def test_job_module_single_savetable(self) -> None:
        job = self._job()
        mods = render_spark_job_modules(job, _PER_BLOCK_2WRITER, [])
        src = mods["jobs/05_build_adam_adsl/adsl.py"]
        assert src.count("saveAsTable") == 1

    # --- YAML (Spark Job) ---

    def test_yaml_one_task_adsl(self) -> None:
        job = self._job()
        graph = build_dataset_graph([_BLK_BUILD, _BLK_SORT])
        yml = render_databricks_yml_spark_job(job, graph, [])
        doc: dict[str, Any] = yaml.safe_load(yml)
        tasks = doc["resources"]["jobs"]["rosetta_my_test_job_job"]["tasks"]
        task_keys = [t["task_key"] for t in tasks]
        assert task_keys.count("adsl") == 1

    def test_yaml_adsl_depends_on_non_self_upstreams(self) -> None:
        # adsl task must depend on adsl_age and aesum (its real upstreams),
        # not on itself (self-edge guard via inp != out in build_dataset_graph).
        job = self._job()
        graph = build_dataset_graph([_BLK_BUILD, _BLK_SORT])
        yml = render_databricks_yml_spark_job(job, graph, [])
        doc: dict[str, Any] = yaml.safe_load(yml)
        tasks = doc["resources"]["jobs"]["rosetta_my_test_job_job"]["tasks"]
        adsl_task = next(t for t in tasks if t["task_key"] == "adsl")
        # adsl_age and aesum are roots (not produced by any block) so no depends_on.
        assert "depends_on" not in adsl_task

    # --- build_dataset_graph extensions ---

    def test_ordered_writers_two_entries_in_source_order(self) -> None:
        graph = build_dataset_graph([_BLK_BUILD, _BLK_SORT])
        writers = graph["ordered_writers"]["adsl"]
        assert len(writers) == 2
        assert writers[0]["block_id"] == "blk_build"
        assert writers[1]["block_id"] == "blk_sort"

    def test_ordered_writers_single_writer_one_entry(self) -> None:
        graph = build_dataset_graph([BLOCK_A, BLOCK_B])
        assert len(graph["ordered_writers"]["dm_clean"]) == 1
        assert len(graph["ordered_writers"]["dm_merged"]) == 1

    def test_normalised_plans_exposed(self) -> None:
        graph = build_dataset_graph([_BLK_BUILD, _BLK_SORT])
        plans = graph["normalised_plans"]
        assert len(plans) == 2
        # All dataset names are normalised (libname stripped, lowercase).
        for bp in plans:
            for ds in bp["input_datasets"] + bp["output_datasets"]:
                assert ds == ds.lower()
                assert "." not in ds

    def test_dataset_source_file_returned(self) -> None:
        graph = build_dataset_graph([_BLK_BUILD, _BLK_SORT])
        dsf = graph["dataset_source_file"]
        assert dsf["adsl"] == "05_build_adam_adsl"


# ---------------------------------------------------------------------------
# DLT modularization — one file per SAS source file
# ---------------------------------------------------------------------------

# Two blocks from different SAS files so modularization splits them.
_BLK_FILE_A = {
    "block_id": "blk_fa",
    "source_file": "01_dm_clean.sas",
    "start_line": 10,
    "input_datasets": ["raw_dm"],
    "output_datasets": ["dm_clean"],
}
_BLK_FILE_B = {
    "block_id": "blk_fb",
    "source_file": "02_ae_summary.sas",
    "start_line": 5,
    "input_datasets": ["raw_ae"],
    "output_datasets": ["ae_summary"],
}
_PER_BLOCK_TWO_FILES = {
    "blk_fa": "result = raw_dm.rename(columns={'id': 'usubjid'})",
    "blk_fb": "result = raw_ae.groupby('usubjid').size().reset_index(name='n')",
}


class TestDltModularization:
    """render_dlt_pipeline returns one file per SAS source file."""

    # SAS: tests/test_databricks_bundle.py:TestDltModularization

    def _job(self, plans: list[dict[str, Any]]) -> FakeJob:
        return FakeJob(migration_plan={"block_plans": plans})

    def test_two_source_files_yield_two_keys(self) -> None:
        job = self._job([_BLK_FILE_A, _BLK_FILE_B])
        mods = render_dlt_pipeline(job, _PER_BLOCK_TWO_FILES, [])
        assert "transformations/01_dm_clean_dlt.py" in mods
        assert "transformations/02_ae_summary_dlt.py" in mods
        assert len(mods) == 2

    def test_each_file_contains_only_its_own_tables(self) -> None:
        job = self._job([_BLK_FILE_A, _BLK_FILE_B])
        mods = render_dlt_pipeline(job, _PER_BLOCK_TWO_FILES, [])
        assert 'name="dm_clean"' in mods["transformations/01_dm_clean_dlt.py"]
        assert 'name="ae_summary"' not in mods["transformations/01_dm_clean_dlt.py"]
        assert 'name="ae_summary"' in mods["transformations/02_ae_summary_dlt.py"]
        assert 'name="dm_clean"' not in mods["transformations/02_ae_summary_dlt.py"]

    def test_zero_output_file_not_emitted(self) -> None:
        zero_block = {
            "block_id": "blk_zero",
            "source_file": "03_print.sas",
            "start_line": 1,
            "input_datasets": ["dm_clean"],
            "output_datasets": [],
        }
        job = self._job([_BLK_FILE_A, zero_block])
        mods = render_dlt_pipeline(job, {**_PER_BLOCK_TWO_FILES, "blk_zero": "pass"}, [])
        assert not any("03_print" in k for k in mods)

    def test_single_source_file_yields_one_key_with_stem_path(self) -> None:
        # Regression: single-source job gets the <stem>_dlt.py key, not the old monolithic name.
        job = self._job([BLOCK_A])
        mods = render_dlt_pipeline(job, {"blk_a": "result = dm"}, [])
        assert len(mods) == 1
        key = next(iter(mods))
        assert key == "transformations/pipeline_dlt.py"

    def test_global_emitted_dedupes_across_files(self) -> None:
        # blk_fa emits dm_clean in file_a; blk_dup (also source file_a but via a
        # second block in file_b) would re-emit dm_clean — global emitted must stop it.
        blk_dup = {
            "block_id": "blk_dup",
            "source_file": "02_ae_summary.sas",
            "start_line": 1,
            "input_datasets": [],
            "output_datasets": ["dm_clean"],  # same table, different file
        }
        job = self._job([_BLK_FILE_A, blk_dup])
        per_block = {"blk_fa": "result = raw_dm", "blk_dup": "result = raw_dm"}
        mods = render_dlt_pipeline(job, per_block, [])
        combined = "\n".join(mods.values())
        assert combined.count('name="dm_clean"') == 1

    def test_render_databricks_yml_libraries_from_dict(self) -> None:
        job = FakeJob(name="My Test Job")
        dlt_modules = {
            "transformations/02_ae_summary_dlt.py": "",
            "transformations/01_dm_clean_dlt.py": "",
        }
        doc: dict[str, Any] = yaml.safe_load(render_databricks_yml(job, {}, [], dlt_modules))
        libs = doc["resources"]["pipelines"]["rosetta_my_test_job_pipeline"]["libraries"]
        paths = [lib["file"]["path"] for lib in libs]
        # Sorted for byte-determinism.
        assert paths == [
            "./transformations/01_dm_clean_dlt.py",
            "./transformations/02_ae_summary_dlt.py",
        ]

    def test_render_databricks_yml_empty_modules_falls_back_to_legacy(self) -> None:
        job = FakeJob(name="My Test Job")
        doc: dict[str, Any] = yaml.safe_load(render_databricks_yml(job, {}, [], {}))
        libs = doc["resources"]["pipelines"]["rosetta_my_test_job_pipeline"]["libraries"]
        assert any("rosetta_my_test_job_dlt.py" in str(lib) for lib in libs)

    def test_docstring_names_source_file(self) -> None:
        job = self._job([_BLK_FILE_A])
        mods = render_dlt_pipeline(job, {"blk_fa": "result = raw_dm"}, [])
        src = mods["transformations/01_dm_clean_dlt.py"]
        assert "source: 01_dm_clean.sas" in src

    def test_all_modules_syntactically_valid(self) -> None:
        job = self._job([_BLK_FILE_A, _BLK_FILE_B])
        mods = render_dlt_pipeline(job, _PER_BLOCK_TWO_FILES, [])
        for path, source in mods.items():
            try:
                ast.parse(source)
            except SyntaxError as exc:
                raise AssertionError(
                    f"Modular DLT render produced invalid Python in {path}: {exc}"
                ) from exc


# ---------------------------------------------------------------------------
# Spark Job subfolder modularization — one subdir per SAS source file
# ---------------------------------------------------------------------------

_BLK_STEP_A = {
    "block_id": "blk_step_a",
    "source_file": "step_a.sas",
    "start_line": 1,
    "input_datasets": ["raw_a"],
    "output_datasets": ["out_a"],
}
_BLK_STEP_B = {
    "block_id": "blk_step_b",
    "source_file": "step_b.sas",
    "start_line": 1,
    "input_datasets": ["raw_b"],
    "output_datasets": ["out_b"],
}
_BLK_NO_SOURCE = {
    "block_id": "blk_nosrc",
    "source_file": "",
    "start_line": 1,
    "input_datasets": [],
    "output_datasets": ["anon_out"],
}


class TestSparkJobModularization:
    """render_spark_job_modules uses jobs/<source_stem>/<table>.py keys."""

    # SAS: tests/test_databricks_bundle.py:TestSparkJobModularization

    def _job(self, plans: list[dict[str, Any]]) -> FakeJob:
        return FakeJob(migration_plan={"block_plans": plans})

    def test_two_source_files_produce_different_subdirs(self) -> None:
        job = self._job([_BLK_STEP_A, _BLK_STEP_B])
        mods = render_spark_job_modules(
            job,
            {"blk_step_a": "result = raw_a", "blk_step_b": "result = raw_b"},
            [],
        )
        assert "jobs/step_a/out_a.py" in mods
        assert "jobs/step_b/out_b.py" in mods

    def test_no_source_file_falls_into_misc(self) -> None:
        job = self._job([_BLK_NO_SOURCE])
        mods = render_spark_job_modules(job, {"blk_nosrc": "result = spark.range(1)"}, [])
        assert "jobs/_misc/anon_out.py" in mods

    def test_yaml_python_file_matches_module_key(self) -> None:
        job = self._job([_BLK_STEP_A, _BLK_STEP_B])
        graph = build_dataset_graph([_BLK_STEP_A, _BLK_STEP_B])
        doc: dict[str, Any] = yaml.safe_load(render_databricks_yml_spark_job(job, graph, []))
        job_tasks = doc["resources"]["jobs"]["rosetta_my_test_job_job"]["tasks"]
        tasks = {t["task_key"]: t for t in job_tasks}
        assert tasks["out_a"]["spark_python_task"]["python_file"] == "./jobs/step_a/out_a.py"
        assert tasks["out_b"]["spark_python_task"]["python_file"] == "./jobs/step_b/out_b.py"

    def test_build_dataset_graph_dataset_source_file_two_files(self) -> None:
        graph = build_dataset_graph([_BLK_STEP_A, _BLK_STEP_B])
        dsf = graph["dataset_source_file"]
        assert dsf["out_a"] == "step_a"
        assert dsf["out_b"] == "step_b"

    def test_build_dataset_graph_dataset_source_file_no_source(self) -> None:
        graph = build_dataset_graph([_BLK_NO_SOURCE])
        dsf = graph["dataset_source_file"]
        assert dsf["anon_out"] == "_misc"

    def test_build_dataset_graph_root_datasets_excluded_from_dataset_source_file(self) -> None:
        graph = build_dataset_graph([_BLK_STEP_A])
        dsf = graph["dataset_source_file"]
        assert "raw_a" not in dsf
        assert "out_a" in dsf


# ---------------------------------------------------------------------------
# _format_yaml helper
# ---------------------------------------------------------------------------


class TestFormatYaml:
    """Shared YAML formatter emits blank lines between top-level sections."""

    # SAS: tests/test_databricks_bundle.py:TestFormatYaml

    def _render_yml(self) -> str:
        job = FakeJob(name="My Test Job")
        return render_databricks_yml(job, {}, [])

    def test_blank_line_before_resources_key(self) -> None:
        yml = self._render_yml()
        lines = yml.splitlines()
        resources_idx = next(i for i, ln in enumerate(lines) if ln.startswith("resources:"))
        assert lines[resources_idx - 1] == "", "Expected blank line before 'resources:'"

    def test_blank_line_before_variables_key(self) -> None:
        yml = self._render_yml()
        lines = yml.splitlines()
        variables_idx = next(i for i, ln in enumerate(lines) if ln.startswith("variables:"))
        assert lines[variables_idx - 1] == "", "Expected blank line before 'variables:'"

    def test_calling_twice_is_identical(self) -> None:
        # _format_yaml must be idempotent when called via the renderer.
        yml1 = self._render_yml()
        yml2 = self._render_yml()
        assert yml1 == yml2

    def test_spark_job_yml_has_blank_before_resources(self) -> None:
        job = FakeJob(
            name="My Test Job",
            migration_plan={"block_plans": [BLOCK_A, BLOCK_B]},
        )
        graph = build_dataset_graph([BLOCK_A, BLOCK_B])
        yml = render_databricks_yml_spark_job(job, graph, [])
        lines = yml.splitlines()
        resources_idx = next(i for i, ln in enumerate(lines) if ln.startswith("resources:"))
        assert lines[resources_idx - 1] == "", "Expected blank line before 'resources:'"
