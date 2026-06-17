"""Databricks Asset Bundle (DAB) artefact generators for the rosetta-decode backend.

Produces byte-deterministic DLT pipeline Python modules and DAB ``databricks.yml``
manifests from a completed migration job's block plans, generated code, and inferred
schema.  All three public functions are **pure** — no database calls, no side effects.

This module MUST NOT import from ``src.worker``.
"""

# SAS: src/backend/api/databricks_bundle.py:1

import logging
import os
import re
import textwrap
from collections import deque
from typing import TYPE_CHECKING, Any

import yaml
from src.backend.api.schema_utils import map_semantic_to_spark_type

if TYPE_CHECKING:
    from src.backend.api.schemas import ColumnSchema, TableSchema

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_LIBNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.", re.ASCII)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _normalise_ds_name(name: str) -> str:
    """Strip libname prefix and lowercase a dataset name.

    Mirrors the fallback branch of ``_normalise_lineage_ds`` in
    ``src/worker/main.py`` so that dataset names produced by block plans are
    comparable with ``TableSchema.dataset_name`` values.

    Args:
        name: Raw dataset name, possibly ``WORK.MYDS`` or ``myds``.

    Returns:
        Lowercased stem, e.g. ``myds``.
    """
    # SAS: databricks_bundle.py:_normalise_ds_name
    return _LIBNAME_RE.sub("", name).lower()


def _slugify(text: str) -> str:
    """Convert an arbitrary string to a safe identifier (lowercase, underscores).

    Args:
        text: Job name or similar free-form string.

    Returns:
        Lowercased alphanumeric+underscore string.
    """
    # SAS: databricks_bundle.py:_slugify
    return _SLUG_RE.sub("_", text.lower()).strip("_") or "job"


def _resolve_schema_for_dataset(
    dataset_name: str,
    schema: "list[TableSchema]",
) -> "TableSchema | None":
    """Find a TableSchema entry whose dataset_name stem matches *dataset_name*.

    Performs case-insensitive stem comparison so that ``WORK.MYDS`` normalised
    to ``myds`` matches a ``TableSchema`` with ``dataset_name="myds"``.

    Args:
        dataset_name: Normalised (lowercased, prefix-stripped) dataset name.
        schema: List of TableSchema instances to search.

    Returns:
        Matching TableSchema, or ``None`` if not found.
    """
    # SAS: databricks_bundle.py:_resolve_schema_for_dataset
    for ts in schema:
        stem = os.path.splitext(os.path.basename(ts.dataset_name))[0].lower()
        if stem == dataset_name:
            return ts
    return None


def _struct_type_lines(table_schema: "TableSchema") -> list[str]:
    """Build the StructField lines for a DLT schema= argument.

    Uses target_columns when available (post-execution), otherwise falls back
    to the source columns.  Resolves each column's type via
    ``map_semantic_to_spark_type``.

    Args:
        table_schema: TableSchema instance for the output dataset.

    Returns:
        List of StructField strings, one per column.
    """
    # SAS: databricks_bundle.py:_struct_type_lines
    cols: list[ColumnSchema] = table_schema.target_columns or table_schema.columns
    lines: list[str] = []
    for col in cols:
        effective_type = col.override_type or col.semantic_type
        spark_type = map_semantic_to_spark_type(effective_type)
        lines.append(f'        StructField("{col.name}", {spark_type}, nullable=True),')
    return lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_dataset_graph(block_plans: list[dict[str, Any]]) -> dict[str, Any]:
    """Build an ordered dataset dependency graph from a list of block plans.

    Each *block_plan* must expose ``input_datasets`` (list[str]) and
    ``output_datasets`` (list[str]).  Dataset names are normalised by stripping
    libname prefixes and lowercasing so that ``WORK.MYDS`` and ``myds`` are
    treated as the same node.

    The function uses Kahn's algorithm to produce a topological ordering
    (sources first).  If a cycle is detected the original block declaration
    order is used as a fallback.

    Args:
        block_plans: List of block plan dicts, each with at least
            ``input_datasets`` and ``output_datasets`` keys.

    Returns:
        Dict with keys:

        * ``ordered_datasets`` — list[str], topological order (sources first).
        * ``root_datasets`` — set[str], inputs not produced by any block.
        * ``block_outputs`` — set[str], all datasets produced by any block.
        * ``edges`` — list[tuple[str, str]], (producer_dataset, consumer_dataset).
        * ``block_for_output`` — dict[str, dict], dataset → block_plan that produces it.
    """
    # SAS: databricks_bundle.py:build_dataset_graph

    # Normalise all dataset names inside the block plans (non-destructive).
    normalised_plans: list[dict[str, Any]] = []
    for bp in block_plans:
        normalised_plans.append(
            {
                **bp,
                "input_datasets": [_normalise_ds_name(d) for d in bp.get("input_datasets", [])],
                "output_datasets": [_normalise_ds_name(d) for d in bp.get("output_datasets", [])],
            }
        )

    block_outputs: set[str] = set()
    block_for_output: dict[str, dict[str, Any]] = {}
    for bp in normalised_plans:
        for ds in bp["output_datasets"]:
            block_outputs.add(ds)
            block_for_output[ds] = bp

    all_inputs: set[str] = {ds for bp in normalised_plans for ds in bp["input_datasets"]}
    root_datasets: set[str] = all_inputs - block_outputs

    # Build dataset-level DAG.
    # Node = dataset name.  Edge = (producer_ds, consumer_ds) when the
    # producer and consumer are different datasets within the same or
    # different blocks.
    all_datasets: set[str] = block_outputs | root_datasets
    in_degree: dict[str, int] = {ds: 0 for ds in all_datasets}
    adjacency: dict[str, list[str]] = {ds: [] for ds in all_datasets}
    edges: list[tuple[str, str]] = []

    for bp in normalised_plans:
        for inp in bp["input_datasets"]:
            for out in bp["output_datasets"]:
                if inp != out and inp in all_datasets and out not in adjacency[inp]:
                    adjacency[inp].append(out)
                    in_degree[out] += 1
                    edges.append((inp, out))

    # Kahn's algorithm — use a sorted queue for determinism.
    queue: deque[str] = deque(sorted(ds for ds, deg in in_degree.items() if deg == 0))
    ordered: list[str] = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for neighbour in sorted(adjacency[node]):
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    if len(ordered) < len(all_datasets):
        # Cycle detected — fall back to block declaration order.
        logger.warning(
            "build_dataset_graph: cycle detected; falling back to block declaration order."
        )
        seen: set[str] = set()
        fallback: list[str] = []
        for bp in normalised_plans:
            for ds in bp["input_datasets"] + bp["output_datasets"]:
                if ds not in seen:
                    fallback.append(ds)
                    seen.add(ds)
        ordered = fallback

    return {
        "ordered_datasets": ordered,
        "root_datasets": root_datasets,
        "block_outputs": block_outputs,
        "edges": edges,
        "block_for_output": block_for_output,
    }


def render_dlt_pipeline(
    job: Any,
    per_block_code: dict[str, str],
    schema: "list[TableSchema]",
) -> str:
    """Render a Delta Live Tables Python module from a migration job's block plans.

    Produces one ``@dlt.table`` decorated function per (block, output_dataset)
    pair.  Root inputs (not produced by any block) are read via
    ``spark.read.format("delta").load(...)``; inter-block inputs are read via
    ``dlt.read(...)``.

    Zero-output blocks (e.g. PROC PRINT) are silently skipped.
    Untranslatable blocks (``# SAS-UNRECOGNIZED`` marker or empty code) emit a
    ``raise NotImplementedError`` stub so the pipeline is still importable.

    Primary-key columns (``is_pk=True``) on output datasets generate
    ``@dlt.expect_or_fail`` constraints placed immediately before the function
    definition.

    Args:
        job: ORM ``Job`` instance (accessed via ``job.migration_plan`` and
            ``job.id``; ``Any`` to avoid circular imports).
        per_block_code: Mapping of ``block_id`` → generated Python source string.
        schema: List of ``TableSchema`` instances for schema resolution.

    Returns:
        Byte-deterministic Python source string for the DLT pipeline module.
    """
    # SAS: databricks_bundle.py:render_dlt_pipeline

    plan: dict[str, Any] = job.migration_plan or {}
    block_plans: list[dict[str, Any]] = plan.get("block_plans", [])

    graph = build_dataset_graph(block_plans)
    block_outputs: set[str] = graph["block_outputs"]

    # Re-normalise block plans for use below.
    normalised: list[dict[str, Any]] = []
    for bp in block_plans:
        normalised.append(
            {
                **bp,
                "input_datasets": [_normalise_ds_name(d) for d in bp.get("input_datasets", [])],
                "output_datasets": [_normalise_ds_name(d) for d in bp.get("output_datasets", [])],
            }
        )

    lines: list[str] = []

    # Module header
    lines.append('"""DLT pipeline generated by rosetta-decode.')
    lines.append("")
    lines.append("NOTE: Multi-output blocks are repeated once per output dataset.")
    lines.append('"""')
    lines.append("")
    lines.append("# SAS: generated by rosetta-decode")
    lines.append("")
    lines.append("import os")
    lines.append("")
    lines.append("import dlt")
    lines.append("from pyspark.sql import functions as F")
    lines.append("from pyspark.sql.types import *  # noqa: F401,F403")
    lines.append("")
    lines.append(
        "DATABRICKS_DATA_ROOT = os.environ.get("
        '"DATABRICKS_DATA_ROOT", '
        '"abfss://data@<storage>.dfs.core.windows.net/")  # TODO: set storage account'
    )
    lines.append("")

    for bp in normalised:
        block_id: str = bp.get("block_id", "")
        source_file: str = bp.get("source_file", "")
        start_line: int = bp.get("start_line", 0)
        output_datasets: list[str] = bp["output_datasets"]
        input_datasets: list[str] = bp["input_datasets"]

        if not output_datasets:
            # Zero-output block (e.g. PROC PRINT) — skip.
            continue

        python_code: str = per_block_code.get(block_id, "") or ""
        is_untranslatable = not python_code.strip() or "# SAS-UNRECOGNIZED" in python_code

        for output_ds in sorted(output_datasets):
            ts = _resolve_schema_for_dataset(output_ds, schema)

            # Build schema= argument if we have column info.
            schema_lines: list[str] = _struct_type_lines(ts) if ts else []
            has_schema = bool(schema_lines)

            # Resolve PK columns for expect_or_fail constraints.
            pk_cols: list[str] = []
            if ts:
                effective_cols = ts.target_columns or ts.columns
                pk_cols = [c.name for c in effective_cols if c.is_pk]

            target_schema_comment = ts.target_schema if ts else ""

            # @dlt.expect_or_fail constraints (one per PK column).
            for pk_col in sorted(pk_cols):
                lines.append(
                    f'@dlt.expect_or_fail("pk_{pk_col}_not_null", "`{pk_col}` IS NOT NULL")'
                )

            # @dlt.table decorator.
            provenance = f"# SAS: {source_file}:{start_line}"
            if has_schema:
                struct_body = "\n".join(schema_lines)
                decorator = textwrap.dedent(f"""\
                    @dlt.table(
                        name="{output_ds}",
                        comment="{provenance}",
                        schema=StructType([
                    {struct_body}
                        ]),
                    )""")
            else:
                decorator = textwrap.dedent(f"""\
                    @dlt.table(
                        name="{output_ds}",
                        comment="{provenance}",
                    )""")

            if target_schema_comment:
                lines.append(f"# target_schema: {target_schema_comment}")
            lines.append(decorator)
            lines.append(f"def {output_ds}():")

            if is_untranslatable:
                lines.append(
                    "    raise NotImplementedError("
                    '"Untranslatable SAS block — manual migration required")'
                )
            else:
                # Emit reads for inputs.
                for inp in sorted(input_datasets):
                    var_name = re.sub(r"[^a-z0-9_]", "_", inp) + "_df"
                    if inp in block_outputs:
                        lines.append(f'    {var_name} = dlt.read("{inp}")')
                    else:
                        lines.append(
                            f'    {var_name} = spark.read.format("delta").load('
                            f'f"{{DATABRICKS_DATA_ROOT}}/{inp}")  # TODO: confirm path'
                        )

                # Inline block code (indented 4 spaces).
                indented_code = textwrap.indent(python_code.rstrip(), "    ")
                lines.append(indented_code)

            lines.append("")

    return "\n".join(lines)


def render_databricks_yml(
    job: Any,
    datasets: dict[str, Any],
    schema: "list[TableSchema]",
) -> str:
    """Render a Databricks Asset Bundle ``databricks.yml`` manifest.

    Produces a YAML document containing a DLT pipeline resource and a
    scheduling job resource, both referencing the same job slug.

    Args:
        job: ORM ``Job`` instance (accessed via ``job.id`` and ``job.name``
            or ``str(job.id)``; ``Any`` to avoid circular imports).
        datasets: Dataset graph dict as returned by ``build_dataset_graph``.
        schema: List of ``TableSchema`` instances for schema resolution.

    Returns:
        Byte-deterministic YAML string.
    """
    # SAS: databricks_bundle.py:render_databricks_yml

    raw_name: str = getattr(job, "name", None) or str(job.id)
    job_slug = _slugify(raw_name)

    # Determine target_schema default: first non-empty TableSchema.target_schema.
    target_schema_default = job_slug
    for ts in schema:
        if ts.target_schema and ts.target_schema not in ("public", ""):
            target_schema_default = ts.target_schema
            break

    pipeline_name = f"rosetta_{job_slug}_pipeline"
    job_name = f"rosetta_{job_slug}_job"
    dlt_file = f"./transformations/rosetta_{job_slug}_dlt.py"

    bundle_doc: dict[str, Any] = {
        "bundle": {
            "name": f"rosetta_{job_slug}",
        },
        "variables": {
            "catalog": {
                "default": "main",
                "description": "Unity Catalog catalog name",
            },
            "target_schema": {
                "default": target_schema_default,
                "description": "Unity Catalog schema / database name",
            },
            "storage_root": {
                "default": (
                    "abfss://data@<storage>.dfs.core.windows.net/  # TODO: set storage account"
                ),
                "description": "Root ABFSS path for source Delta tables",
            },
        },
        "resources": {
            "pipelines": {
                pipeline_name: {
                    "name": pipeline_name,
                    "catalog": "${var.catalog}",
                    "target": "${var.target_schema}",
                    "serverless": True,
                    "libraries": [
                        {"file": {"path": dlt_file}},
                    ],
                    "configuration": {
                        "DATABRICKS_DATA_ROOT": "${var.storage_root}",
                    },
                },
            },
            "jobs": {
                job_name: {
                    "name": job_name,
                    "tasks": [
                        {
                            "task_key": "run_pipeline",
                            "pipeline_task": {
                                "pipeline_id": (f"${{resources.pipelines.{pipeline_name}.id}}"),
                            },
                        },
                    ],
                    "schedule": {
                        "quartz_cron_expression": ("0 0 6 * * ?  # TODO: confirm schedule"),
                        "timezone_id": "UTC",
                    },
                },
            },
        },
    }

    return yaml.dump(bundle_doc, sort_keys=True, default_flow_style=False, allow_unicode=True)
