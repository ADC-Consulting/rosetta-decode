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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

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

# ---------------------------------------------------------------------------
# F75 — deployment-target resolver (pure, unit-testable, no I/O)
# ---------------------------------------------------------------------------

# Default provider/compute when the questionnaire is absent or unanswered.
# THIS IS THE REPRODUCIBILITY CONTRACT: the default resolution (azure / serverless
# / catalog "main" / schema from the Data tab) MUST reproduce the F74 bytes exactly.
_DEFAULT_PROVIDER = "azure"
_DEFAULT_INGESTION = "historical"
_DEFAULT_COMPUTE = "serverless"
_DEFAULT_CATALOG = "main"

# Delivery format: DLT pipeline (default) vs a classic multi-task Spark Job.
_DEFAULT_DELIVERY_FORMAT = "dlt"
_DELIVERY_FORMATS = ("dlt", "spark_job")

# Shared classic-cluster spark_version placeholder (Job + pipeline classic compute).
_CLASSIC_SPARK_VERSION = "15.4.x-scala2.12  # TODO: confirm Databricks Runtime version"

# Per-provider storage scheme + default storage_root + example auth host.
# The azure storage_root is byte-identical to the F74 literal so that the
# default path reproduces today's bundle exactly.
_PROVIDER_PROFILES: dict[str, dict[str, str]] = {
    "azure": {
        "scheme": "abfss",
        # storage_root + storage_desc are byte-identical to the F74 literals so the
        # azure-default path reproduces today's bundle exactly.
        "storage_root": "abfss://data@<storage>.dfs.core.windows.net/",
        "storage_desc": "Root ABFSS path for source Delta tables",
        "auth_host": "https://<workspace>.azuredatabricks.net",
        "node_type_id": "Standard_DS3_v2",
    },
    "aws": {
        "scheme": "s3",
        "storage_root": "s3://<bucket>/",
        "storage_desc": "Root S3 path for source Delta tables",
        "auth_host": "https://<workspace>.cloud.databricks.com",
        "node_type_id": "i3.xlarge",
    },
    "gcp": {
        "scheme": "gs",
        "storage_root": "gs://<bucket>/",
        "storage_desc": "Root GCS path for source Delta tables",
        "auth_host": "https://<workspace>.gcp.databricks.com",
        "node_type_id": "n1-standard-4",
    },
}


@dataclass(frozen=True)
class DeploymentTarget:
    """Fully-defaulted internal view of the accept-time questionnaire answers.

    Unlike the API-layer ``schemas.DeploymentTarget`` (all fields optional), this
    dataclass is *resolved*: every field carries its effective value. Build it via
    :func:`resolve_deployment_target`, never directly, so defaults stay centralised.

    Attributes:
        provider: One of ``azure`` / ``aws`` / ``gcp``.
        ingestion_approach: One of ``historical`` / ``staging`` (guide prose only).
        compute_mode: One of ``serverless`` / ``classic``.
        catalog: Unity Catalog catalog name (default ``main``).
        schema: Unity Catalog schema, or ``None`` to fall back to the Data-tab
            ``target_schema`` logic in the generators.
        delivery_format: One of ``dlt`` (Lakeflow DLT pipeline, default) or
            ``spark_job`` (classic multi-task Lakeflow Job).
    """

    # SAS: databricks_bundle.py:DeploymentTarget
    provider: str = _DEFAULT_PROVIDER
    ingestion_approach: str = _DEFAULT_INGESTION
    compute_mode: str = _DEFAULT_COMPUTE
    catalog: str = _DEFAULT_CATALOG
    schema: str | None = None
    delivery_format: str = _DEFAULT_DELIVERY_FORMAT

    @property
    def scheme(self) -> str:
        """Storage URI scheme for the provider (``abfss`` / ``s3`` / ``gs``)."""
        return _PROVIDER_PROFILES[self.provider]["scheme"]

    @property
    def storage_root(self) -> str:
        """Default storage root URI for the provider (with TODO placeholders)."""
        return _PROVIDER_PROFILES[self.provider]["storage_root"]

    @property
    def auth_host(self) -> str:
        """Example workspace auth host for the provider's deployment guide."""
        return _PROVIDER_PROFILES[self.provider]["auth_host"]

    @property
    def storage_desc(self) -> str:
        """Description of the storage-root bundle variable for the provider."""
        return _PROVIDER_PROFILES[self.provider]["storage_desc"]

    @property
    def node_type_id(self) -> str:
        """Placeholder classic-cluster node type for the provider."""
        return _PROVIDER_PROFILES[self.provider]["node_type_id"]


# Default resolved target — used by direct callers that pass no questionnaire.
_DEFAULT_TARGET = DeploymentTarget()


def resolve_deployment_target(raw: dict[str, Any] | None) -> DeploymentTarget:
    """Normalise raw questionnaire answers into a fully-defaulted DeploymentTarget.

    Accepts the dict persisted at ``user_overrides["deployment_target"]`` (where
    unanswered questions are simply absent) or ``None`` for jobs accepted before
    F75. Any missing or ``None`` field falls back to its documented default, so a
    ``None`` / empty input yields azure / historical / serverless / catalog
    ``main`` / schema fallback — byte-identical to the F74 bundle.

    Args:
        raw: Raw answer dict (JSON key ``schema``), or ``None``.

    Returns:
        A resolved :class:`DeploymentTarget`.
    """
    # SAS: databricks_bundle.py:resolve_deployment_target
    data = raw or {}

    provider = data.get("provider") or _DEFAULT_PROVIDER
    if provider not in _PROVIDER_PROFILES:
        logger.warning("resolve_deployment_target: unknown provider %r; using azure.", provider)
        provider = _DEFAULT_PROVIDER

    ingestion = data.get("ingestion_approach") or _DEFAULT_INGESTION
    compute = data.get("compute_mode") or _DEFAULT_COMPUTE
    catalog = data.get("catalog") or _DEFAULT_CATALOG
    schema = data.get("schema") or None

    delivery_format = data.get("delivery_format") or _DEFAULT_DELIVERY_FORMAT
    if delivery_format not in _DELIVERY_FORMATS:
        logger.warning(
            "resolve_deployment_target: unknown delivery_format %r; using dlt.",
            delivery_format,
        )
        delivery_format = _DEFAULT_DELIVERY_FORMAT

    return DeploymentTarget(
        provider=provider,
        ingestion_approach=ingestion,
        compute_mode=compute,
        catalog=catalog,
        schema=schema,
        delivery_format=delivery_format,
    )


def build_pipeline_compute(target: DeploymentTarget) -> dict[str, Any]:
    """Map a resolved target's compute mode to a DLT pipeline compute fragment.

    Serverless yields ``{"serverless": True}`` (the F74 default). Classic yields a
    cluster block with a provider-appropriate **placeholder** ``node_type_id`` and a
    loud ``# TODO`` plus ``autoscale`` 1-2 workers, explicitly not deploy-ready.

    Args:
        target: Resolved deployment target.

    Returns:
        A dict to splice into the pipeline resource (sorted-key safe).
    """
    # SAS: databricks_bundle.py:build_pipeline_compute
    if target.compute_mode == "serverless":
        return {"serverless": True}

    node_type = f"{target.node_type_id}  # TODO: confirm node type for {target.provider}"
    return {
        "clusters": [
            {
                "label": "default",
                "node_type_id": node_type,
                "autoscale": {"min_workers": 1, "max_workers": 2},
            }
        ]
    }


def build_job_compute(target: DeploymentTarget) -> dict[str, Any]:
    """Map a resolved target's compute mode to a *Job* compute fragment.

    Unlike :func:`build_pipeline_compute` (DLT-pipeline-only), this builds the
    ``job_clusters`` entry shared by every task of a classic Spark Job.

    * Serverless → ``{}`` (tasks omit ``job_cluster_key`` → serverless compute).
    * Classic → a single shared ``job_clusters`` entry with a provider-appropriate
      **placeholder** ``node_type_id`` (loud ``# TODO``), a shared ``spark_version``
      placeholder, and ``autoscale`` 1-2 workers — explicitly not deploy-ready.

    Args:
        target: Resolved deployment target.

    Returns:
        A dict to splice into the job resource (sorted-key safe).
    """
    # SAS: databricks_bundle.py:build_job_compute
    if target.compute_mode == "serverless":
        return {}

    node_type = f"{target.node_type_id}  # TODO: confirm node type for {target.provider}"
    return {
        "job_clusters": [
            {
                "job_cluster_key": "shared",
                "new_cluster": {
                    "spark_version": _CLASSIC_SPARK_VERSION,
                    "node_type_id": node_type,
                    "autoscale": {"min_workers": 1, "max_workers": 2},
                },
            }
        ]
    }


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


def bind_inter_block_inputs(
    input_datasets: list[str],
    block_outputs: set[str],
    mode: Literal["dlt", "job"],
    catalog_expr: str = "CATALOG",
    schema_expr: str = "SCHEMA",
) -> list[str]:
    """Build the binding lines a block needs for its inter-block inputs.

    The portable, codegen-produced block code references each upstream dataset by
    its bare normalised stem (e.g. ``dm_clean``). Inputs that are produced by
    another block (inter-block) must be bound to that stem before the block code
    runs, in a way appropriate to the delivery format:

    * ``dlt`` → ``<stem> = dlt.read("<stem>")``
    * ``job`` → ``<stem> = spark.read.table(f"{CATALOG}.{SCHEMA}.<stem>")``

    Inputs that are *not* in ``block_outputs`` (root / external sources) get **no**
    binding: the portable block code reads them itself via its ``DATA_ROOT``
    constant. Bindings are emitted in sorted stem order for determinism.

    Args:
        input_datasets: Raw input dataset names for the block.
        block_outputs: Set of all dataset stems produced by some block.
        mode: ``"dlt"`` or ``"job"`` — selects the read expression.
        catalog_expr: Identifier to interpolate for the catalog (job mode).
        schema_expr: Identifier to interpolate for the schema (job mode).

    Returns:
        List of Python source lines (no indentation), one per inter-block input.
    """
    # SAS: databricks_bundle.py:bind_inter_block_inputs
    lines: list[str] = []
    stems = sorted({_normalise_ds_name(inp) for inp in input_datasets})
    for stem in stems:
        if stem not in block_outputs:
            continue
        if mode == "dlt":
            lines.append(f'{stem} = dlt.read("{stem}")')
        else:
            lines.append(
                f'{stem} = spark.read.table(f"{{{catalog_expr}}}.{{{schema_expr}}}.{stem}")'
            )
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
    target: DeploymentTarget | None = None,
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
        target: Resolved deployment target. Defaults to azure/serverless (the F74
            default), which keeps the storage-root literal byte-identical.

    Returns:
        Byte-deterministic Python source string for the DLT pipeline module.
    """
    # SAS: databricks_bundle.py:render_dlt_pipeline

    resolved_target = target or _DEFAULT_TARGET
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
        f'"{resolved_target.storage_root}")  # TODO: set storage account'
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
                # Bind inter-block inputs to the bare stems the portable code uses.
                # Root / external inputs are read by the block itself via DATA_ROOT.
                for bind_line in bind_inter_block_inputs(input_datasets, block_outputs, "dlt"):
                    lines.append(f"    {bind_line}")

                # Inline block code (indented 4 spaces). It is portable (DATA_ROOT)
                # and guaranteed to bind ``result`` (Workstream 1 codegen contract).
                indented_code = textwrap.indent(python_code.rstrip(), "    ")
                lines.append(indented_code)
                lines.append("    return result")

            lines.append("")

    return "\n".join(lines)


def _resolve_target_schema_default(
    job_slug: str,
    schema: "list[TableSchema]",
    target: DeploymentTarget,
) -> str:
    """Resolve the effective ``target_schema`` default for a bundle.

    The answered schema wins; otherwise the first non-empty
    ``TableSchema.target_schema`` (Data-tab logic); otherwise the job slug.

    Args:
        job_slug: Slugified job name (final fallback).
        schema: List of TableSchema instances.
        target: Resolved deployment target.

    Returns:
        Effective schema name string.
    """
    # SAS: databricks_bundle.py:_resolve_target_schema_default
    target_schema_default = job_slug
    for ts in schema:
        if ts.target_schema and ts.target_schema not in ("public", ""):
            target_schema_default = ts.target_schema
            break
    if target.schema:
        target_schema_default = target.schema
    return target_schema_default


def _bundle_variables(
    target: DeploymentTarget,
    schema: "list[TableSchema]",
    job_slug: str,
) -> dict[str, dict[str, str]]:
    """Build the shared ``variables`` block for either bundle YAML renderer.

    Produces catalog / target_schema / storage_root (carried over from F74/F75)
    plus a ``rosetta_data_root`` variable that drives the portable ``DATA_ROOT``
    the generated code resolves via ``ROSETTA_DATA_ROOT``. Both YAML renderers use
    this so the variable surface stays identical across delivery formats.

    Args:
        target: Resolved deployment target.
        schema: List of TableSchema instances for schema resolution.
        job_slug: Slugified job name (schema fallback).

    Returns:
        Mapping suitable for the ``variables`` key (sorted-key safe).
    """
    # SAS: databricks_bundle.py:_bundle_variables
    target_schema_default = _resolve_target_schema_default(job_slug, schema, target)
    storage_root_default = f"{target.storage_root}  # TODO: set storage account"
    # Default landing root: a Unity Catalog Volume under the resolved catalog/schema.
    data_root_default = (
        f"/Volumes/{target.catalog}/{target_schema_default}/landing"
        "  # TODO: confirm UC Volume path for source files"
    )
    return {
        "catalog": {
            "default": target.catalog,
            "description": "Unity Catalog catalog name",
        },
        "target_schema": {
            "default": target_schema_default,
            "description": "Unity Catalog schema / database name",
        },
        "storage_root": {
            "default": storage_root_default,
            "description": target.storage_desc,
        },
        "rosetta_data_root": {
            "default": data_root_default,
            "description": "Root path for source files (ROSETTA_DATA_ROOT)",
        },
    }


def render_databricks_yml(
    job: Any,
    datasets: dict[str, Any],
    schema: "list[TableSchema]",
    target: DeploymentTarget | None = None,
) -> str:
    """Render a Databricks Asset Bundle ``databricks.yml`` manifest.

    Produces a YAML document containing a DLT pipeline resource and a
    scheduling job resource, both referencing the same job slug.

    Args:
        job: ORM ``Job`` instance (accessed via ``job.id`` and ``job.name``
            or ``str(job.id)``; ``Any`` to avoid circular imports).
        datasets: Dataset graph dict as returned by ``build_dataset_graph``.
        schema: List of ``TableSchema`` instances for schema resolution.
        target: Resolved deployment target. Defaults to azure/serverless/catalog
            ``main`` (the F74 default), keeping the storage-root + serverless
            bytes identical for jobs with no questionnaire answers.

    Returns:
        Byte-deterministic YAML string.
    """
    # SAS: databricks_bundle.py:render_databricks_yml

    resolved_target = target or _DEFAULT_TARGET
    raw_name: str = getattr(job, "name", None) or str(job.id)
    job_slug = _slugify(raw_name)

    variables = _bundle_variables(resolved_target, schema, job_slug)
    compute_block = build_pipeline_compute(resolved_target)

    pipeline_name = f"rosetta_{job_slug}_pipeline"
    job_name = f"rosetta_{job_slug}_job"
    dlt_file = f"./transformations/rosetta_{job_slug}_dlt.py"

    bundle_doc: dict[str, Any] = {
        "bundle": {
            "name": f"rosetta_{job_slug}",
        },
        "variables": variables,
        "resources": {
            "pipelines": {
                pipeline_name: {
                    "name": pipeline_name,
                    "catalog": "${var.catalog}",
                    "target": "${var.target_schema}",
                    **compute_block,
                    "libraries": [
                        {"file": {"path": dlt_file}},
                    ],
                    "configuration": {
                        "DATABRICKS_DATA_ROOT": "${var.storage_root}",
                        "ROSETTA_DATA_ROOT": "${var.rosetta_data_root}",
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


# ---------------------------------------------------------------------------
# F76 — Classic Spark Job delivery format
# ---------------------------------------------------------------------------


def _spark_job_module(
    output_ds: str,
    bp: dict[str, Any],
    python_code: str,
    block_outputs: set[str],
    is_untranslatable: bool,
) -> str:
    """Render one ``jobs/<task_key>.py`` module for a single output dataset.

    Args:
        output_ds: Normalised output dataset stem (the Delta table name).
        bp: Normalised block plan dict (input_datasets / source_file / start_line).
        python_code: Portable block source (already DATA_ROOT-based, result-bound).
        block_outputs: Set of all block-produced dataset stems.
        is_untranslatable: Whether the block could not be translated.

    Returns:
        Byte-deterministic Python source string for the task module.
    """
    # SAS: databricks_bundle.py:_spark_job_module
    source_file: str = bp.get("source_file", "")
    start_line: int = bp.get("start_line", 0)
    lines: list[str] = []
    lines.append(f'"""Spark Job task generated by rosetta-decode — writes `{output_ds}`.')
    lines.append('"""')
    lines.append("")
    lines.append(f"# SAS: {source_file}:{start_line}")
    lines.append("")
    lines.append("import os")
    lines.append("")
    lines.append("from pyspark.sql import SparkSession, functions as F  # noqa: F401")
    lines.append("from pyspark.sql.types import *  # noqa: F401,F403")
    lines.append("")
    lines.append("spark = SparkSession.builder.getOrCreate()")
    lines.append("")

    if is_untranslatable:
        lines.append(
            'raise NotImplementedError("Untranslatable SAS block — manual migration required")'
        )
        lines.append("")
        return "\n".join(lines)

    lines.append('CATALOG = os.environ.get("ROSETTA_CATALOG", "main")')
    lines.append('SCHEMA = os.environ.get("ROSETTA_SCHEMA", "default")')
    lines.append("")
    # Bind inter-block inputs to the bare stems the portable code uses. Root /
    # external inputs are read by the block itself via DATA_ROOT.
    binds = bind_inter_block_inputs(bp.get("input_datasets", []), block_outputs, "job")
    if binds:
        lines.extend(binds)
        lines.append("")
    # Portable block code verbatim at module top level (DATA_ROOT-based and
    # ``result``-guaranteed by Workstream 1 codegen).
    lines.append(python_code.rstrip())
    lines.append("")
    lines.append(
        'result.write.format("delta").mode("overwrite").saveAsTable('
        f'f"{{CATALOG}}.{{SCHEMA}}.{output_ds}")'
    )
    lines.append("")
    return "\n".join(lines)


def render_spark_job_modules(
    job: Any,
    per_block_code: dict[str, str],
    schema: "list[TableSchema]",
    target: DeploymentTarget | None = None,
) -> dict[str, str]:
    """Render one PySpark module per output dataset for the classic Job format.

    Mirrors :func:`render_dlt_pipeline`'s block/output handling: zero-output blocks
    are skipped, untranslatable blocks emit a ``raise NotImplementedError`` module,
    and multi-output blocks produce one module per output dataset (each writing the
    block's single ``result`` to its own Delta table — the documented shared-result
    caveat carried over from the DLT renderer).

    Args:
        job: ORM ``Job`` instance (accessed via ``job.migration_plan``).
        per_block_code: Mapping of ``block_id`` → portable Python source.
        schema: List of ``TableSchema`` instances (unused here; kept for parity).
        target: Resolved deployment target. Defaults to azure/serverless/dlt.

    Returns:
        Mapping of ``jobs/<task_key>.py`` → byte-deterministic module source.
    """
    # SAS: databricks_bundle.py:render_spark_job_modules
    plan: dict[str, Any] = job.migration_plan or {}
    block_plans: list[dict[str, Any]] = plan.get("block_plans", [])

    graph = build_dataset_graph(block_plans)
    block_outputs: set[str] = graph["block_outputs"]

    normalised: list[dict[str, Any]] = []
    for bp in block_plans:
        normalised.append(
            {
                **bp,
                "input_datasets": [_normalise_ds_name(d) for d in bp.get("input_datasets", [])],
                "output_datasets": [_normalise_ds_name(d) for d in bp.get("output_datasets", [])],
            }
        )

    modules: dict[str, str] = {}
    for bp in normalised:
        block_id: str = bp.get("block_id", "")
        output_datasets: list[str] = bp["output_datasets"]
        if not output_datasets:
            continue

        python_code: str = per_block_code.get(block_id, "") or ""
        is_untranslatable = not python_code.strip() or "# SAS-UNRECOGNIZED" in python_code

        for output_ds in sorted(output_datasets):
            task_key = _slugify(output_ds)
            modules[f"jobs/{task_key}.py"] = _spark_job_module(
                output_ds, bp, python_code, block_outputs, is_untranslatable
            )
    return modules


def render_databricks_yml_spark_job(
    job: Any,
    datasets: dict[str, Any],
    schema: "list[TableSchema]",
    target: DeploymentTarget | None = None,
) -> str:
    """Render a ``databricks.yml`` for the classic multi-task Spark Job format.

    Emits ``resources.jobs`` only (no ``resources.pipelines``). Each block-output
    dataset becomes one task running ``./jobs/<task_key>.py`` via
    ``spark_python_task``; ``depends_on`` is derived from the dataset DAG (producer
    block-outputs only; root datasets are excluded). Classic compute attaches a
    shared ``job_cluster_key``; serverless omits it. CATALOG / SCHEMA /
    ROSETTA_DATA_ROOT are passed to every task via job-level environment.

    Args:
        job: ORM ``Job`` instance (accessed via ``job.migration_plan`` / name).
        datasets: Dataset graph dict as returned by ``build_dataset_graph``.
        schema: List of ``TableSchema`` instances for schema resolution.
        target: Resolved deployment target. Defaults to azure/serverless.

    Returns:
        Byte-deterministic YAML string.
    """
    # SAS: databricks_bundle.py:render_databricks_yml_spark_job
    resolved_target = target or _DEFAULT_TARGET
    raw_name: str = getattr(job, "name", None) or str(job.id)
    job_slug = _slugify(raw_name)

    variables = _bundle_variables(resolved_target, schema, job_slug)
    compute_block = build_job_compute(resolved_target)
    is_classic = resolved_target.compute_mode == "classic"

    ordered: list[str] = datasets.get("ordered_datasets", [])
    block_outputs: set[str] = datasets.get("block_outputs", set())
    edges: list[tuple[str, str]] = datasets.get("edges", [])

    # producer block-output stems for each consumer dataset (roots excluded).
    producers: dict[str, list[str]] = {}
    for producer, consumer in edges:
        if producer in block_outputs:
            producers.setdefault(consumer, []).append(producer)

    job_name = f"rosetta_{job_slug}_job"
    tasks: list[dict[str, Any]] = []
    for ds in ordered:
        if ds not in block_outputs:
            continue
        task_key = _slugify(ds)
        task: dict[str, Any] = {
            "task_key": task_key,
            "spark_python_task": {"python_file": f"./jobs/{task_key}.py"},
        }
        if is_classic:
            task["job_cluster_key"] = "shared"
        depends = sorted({_slugify(p) for p in producers.get(ds, [])})
        if depends:
            task["depends_on"] = [{"task_key": d} for d in depends]
        tasks.append(task)

    job_resource: dict[str, Any] = {
        "name": job_name,
        **compute_block,
        "tasks": tasks,
        "parameters": [
            {"name": "ROSETTA_CATALOG", "default": "${var.catalog}"},
            {"name": "ROSETTA_SCHEMA", "default": "${var.target_schema}"},
            {"name": "ROSETTA_DATA_ROOT", "default": "${var.rosetta_data_root}"},
        ],
        "schedule": {
            "quartz_cron_expression": "0 0 6 * * ?  # TODO: confirm schedule",
            "timezone_id": "UTC",
        },
    }

    bundle_doc: dict[str, Any] = {
        "bundle": {"name": f"rosetta_{job_slug}"},
        "variables": variables,
        "resources": {"jobs": {job_name: job_resource}},
    }

    return yaml.dump(bundle_doc, sort_keys=True, default_flow_style=False, allow_unicode=True)
