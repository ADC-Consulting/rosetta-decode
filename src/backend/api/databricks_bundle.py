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


def _fold_chain_body(
    target_ds: str,
    chain: list[dict[str, Any]],
    block_outputs: set[str],
    per_block_code: dict[str, str],
    mode: Literal["dlt", "job"],
) -> list[str]:
    """Build the ordered code lines that produce *target_ds* from a writer chain.

    Each element of *chain* is a normalised block plan that writes *target_ds*.
    Self-reads (``target_ds`` appearing in a block's own inputs) are filtered
    before calling ``bind_inter_block_inputs`` so no invalid ``dlt.read("<self>")``
    or ``spark.read.table(...)`` is emitted for the in-place rewrite pattern.

    Args:
        target_ds: Normalised dataset stem being built.
        chain: Writer block plans sorted by ``(source_file, start_line)``.
        block_outputs: Set of all block-produced dataset stems (for bind logic).
        per_block_code: Mapping of block_id → portable Python source.
        mode: ``"dlt"`` or ``"job"`` — selects the inter-block read expression.

    Returns:
        Ordered code lines (no indentation) ending with ``result`` bound to the
        final value of *target_ds*.
    """
    # SAS: databricks_bundle.py:_fold_chain_body
    body: list[str] = []
    for i, bp in enumerate(chain):
        # Drop self-read: in-place rewrite blocks list the dataset as both
        # input and output; emitting a bind for it would create an invalid
        # self-reference (dlt.read inside its own def, or circular table read).
        inputs = [d for d in bp.get("input_datasets", []) if d != target_ds]
        body.extend(bind_inter_block_inputs(inputs, block_outputs, mode))
        # Per-stage provenance only for multi-writer chains; single-writer stays
        # byte-identical to the pre-fold output (no extra comment).
        if len(chain) > 1:
            sf = bp.get("source_file", "")
            sl = bp.get("start_line", 0)
            body.append(f"# SAS: {sf}:{sl}")
        body.append(per_block_code.get(bp.get("block_id", ""), "").rstrip())
        # Hand the running result to the next writer; last writer keeps `result`
        # so the caller can return/save it without an extra assignment.
        if i < len(chain) - 1:
            body.append(f"{target_ds} = result")
    return body


def _format_yaml(doc: dict[str, Any]) -> str:
    """Serialise *doc* to YAML with blank lines between top-level sections.

    Both YAML renderers share this helper so the blank-line structure is
    deterministic and identical across delivery formats.

    Args:
        doc: Bundle document dict to serialise.

    Returns:
        YAML string with a trailing newline and blank lines separating each
        top-level key after the first.
    """
    # SAS: databricks_bundle.py:_format_yaml
    raw = yaml.dump(doc, sort_keys=True, default_flow_style=False, allow_unicode=True)
    lines = raw.splitlines()
    out: list[str] = []
    top_key_seen = False
    for line in lines:
        if line and not line.startswith(" ") and ":" in line:
            if top_key_seen:
                out.append("")
            top_key_seen = True
        out.append(line)
    return "\n".join(out) + "\n"


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
        * ``block_for_output`` — dict[str, dict], dataset → block_plan (last writer).
        * ``normalised_plans`` — list[dict], block plans with normalised dataset names.
        * ``ordered_writers`` — dict[str, list[dict]], dataset stem → writer block plans
          sorted by ``(source_file, start_line)`` (SAS execution order).
        * ``dataset_source_file`` — dict[str, str], normalised dataset stem → slugified
          source-file stem (first writer's source file).  Root datasets are excluded.
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
    # Build ordered_writers while iterating normalised_plans so renderers share
    # one normalisation source rather than re-normalising independently.
    ordered_writers: dict[str, list[dict[str, Any]]] = {}
    for bp in normalised_plans:
        for ds in bp["output_datasets"]:
            block_outputs.add(ds)
            block_for_output[ds] = bp
            ordered_writers.setdefault(ds, []).append(bp)

    # Sort each writer list by (source_file, start_line) so fold order matches
    # SAS sequential execution — topo sort adds no edge between co-writers of
    # the same table, making positional list order an unsafe ordering signal.
    for ds in ordered_writers:
        ordered_writers[ds].sort(key=lambda b: (b.get("source_file", ""), b.get("start_line", 0)))

    dataset_source_file: dict[str, str] = {}
    for ds, writers_list in ordered_writers.items():
        raw_sf = writers_list[0].get("source_file", "") if writers_list else ""
        stem = raw_sf.rsplit(".", 1)[0] if raw_sf else ""
        dataset_source_file[ds] = _slugify(stem) if stem else "_misc"

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
        "normalised_plans": normalised_plans,
        "ordered_writers": ordered_writers,
        "dataset_source_file": dataset_source_file,
    }


def _dlt_is_stub(chain: list[dict[str, Any]], per_block_code: dict[str, str]) -> bool:
    """Return True when the writer chain cannot be safely folded into one DLT table.

    Guards against two ambiguous cases:
    - Any chain block writes more than one output dataset (shared ``result`` is
      ambiguous when another block also writes the same dataset).
    - Any chain block is untranslatable (empty code or ``# SAS-UNRECOGNIZED``).

    Single-writer chains bypass this: multi-output single-writer is fine and
    already works (each output gets its own ``def``).

    Args:
        chain: Writer block plans for the target dataset.
        per_block_code: Mapping of block_id → portable Python source.

    Returns:
        True if the table should emit a ``NotImplementedError`` stub.
    """
    # SAS: databricks_bundle.py:_dlt_is_stub
    is_multi_writer = len(chain) > 1
    for bp in chain:
        code = per_block_code.get(bp.get("block_id", ""), "") or ""
        if not code.strip() or "# SAS-UNRECOGNIZED" in code:
            return True
        if is_multi_writer and len(bp.get("output_datasets", [])) > 1:
            # result is ambiguous: this block writes multiple datasets; we cannot
            # reliably hand the correct result to the next writer.
            return True
    return False


def _dlt_module_header(source_stem: str, storage_root: str) -> list[str]:
    """Build the standard module header lines for one DLT pipeline file.

    Args:
        source_stem: SAS source filename (used in the docstring).
        storage_root: Resolved storage root URI for the DATABRICKS_DATA_ROOT literal.

    Returns:
        List of header source lines (no trailing newline on each).
    """
    # SAS: databricks_bundle.py:_dlt_module_header
    lines: list[str] = []
    lines.append(f'"""DLT pipeline generated by rosetta-decode — source: {source_stem}."""')
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
        f'"{storage_root}")  # TODO: set storage account'
    )
    lines.append("")
    return lines


def _emit_dlt_table(
    output_ds: str,
    chain: list[dict[str, Any]],
    block_outputs: set[str],
    per_block_code: dict[str, str],
    schema: "list[TableSchema]",
) -> list[str]:
    """Build the source lines for one ``@dlt.table`` function.

    Args:
        output_ds: Normalised output dataset stem.
        chain: Writer block plans sorted by ``(source_file, start_line)``.
        block_outputs: Set of all block-produced dataset stems.
        per_block_code: Mapping of block_id → portable Python source.
        schema: List of TableSchema instances for schema resolution.

    Returns:
        List of source lines for this table's decorator + function body.
    """
    # SAS: databricks_bundle.py:_emit_dlt_table
    lines: list[str] = []
    is_stub = _dlt_is_stub(chain, per_block_code)

    first_bp = chain[0]
    source_file: str = first_bp.get("source_file", "")
    start_line: int = first_bp.get("start_line", 0)

    ts = _resolve_schema_for_dataset(output_ds, schema)

    schema_lines: list[str] = _struct_type_lines(ts) if ts else []
    has_schema = bool(schema_lines)

    pk_cols: list[str] = []
    if ts:
        effective_cols = ts.target_columns or ts.columns
        pk_cols = [c.name for c in effective_cols if c.is_pk]

    target_schema_comment = ts.target_schema if ts else ""

    for pk_col in sorted(pk_cols):
        lines.append(f'@dlt.expect_or_fail("pk_{pk_col}_not_null", "`{pk_col}` IS NOT NULL")')

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

    if is_stub:
        for chain_bp in chain:
            bp_code = per_block_code.get(chain_bp.get("block_id", ""), "") or ""
            if not bp_code.strip() or "# SAS-UNRECOGNIZED" in bp_code:
                sf = chain_bp.get("source_file", "")
                sl = chain_bp.get("start_line", 0)
                lines.append(f"    # MANUAL: {sf}:{sl} — untranslatable")
        lines.append(
            '    raise NotImplementedError("Untranslatable SAS block — manual migration required")'
        )
    else:
        body_lines = _fold_chain_body(output_ds, chain, block_outputs, per_block_code, "dlt")
        for body_line in body_lines:
            lines.append(f"    {body_line}")
        lines.append("    return result")

    lines.append("")
    return lines


def render_dlt_pipeline(
    job: Any,
    per_block_code: dict[str, str],
    schema: "list[TableSchema]",
    target: DeploymentTarget | None = None,
) -> "dict[str, str]":
    """Render Delta Live Tables Python modules split by SAS source file.

    Produces one file per SAS source file, keyed as
    ``transformations/<source_stem>_dlt.py``. Blocks with no ``source_file``
    are grouped under ``_misc``. Each file contains one ``@dlt.table``
    decorated function per output dataset from that source file's blocks.

    Multiple blocks writing the same dataset are folded into one function body
    in ``(source_file, start_line)`` order via :func:`_fold_chain_body`. The
    global ``emitted`` set spans all files so cross-file table duplicates are
    still deduped correctly.

    Files with no tables to emit (all blocks zero-output or already emitted)
    are omitted from the returned dict.

    Args:
        job: ORM ``Job`` instance (accessed via ``job.migration_plan`` and
            ``job.id``; ``Any`` to avoid circular imports).
        per_block_code: Mapping of ``block_id`` → generated Python source string.
        schema: List of ``TableSchema`` instances for schema resolution.
        target: Resolved deployment target. Defaults to azure/serverless (the F74
            default), which keeps the storage-root literal byte-identical.

    Returns:
        Dict mapping ``transformations/<source_stem>_dlt.py`` → module source.
        Empty when there are no block plans.
    """
    # SAS: databricks_bundle.py:render_dlt_pipeline

    resolved_target = target or _DEFAULT_TARGET
    plan: dict[str, Any] = job.migration_plan or {}
    block_plans: list[dict[str, Any]] = plan.get("block_plans", [])

    graph = build_dataset_graph(block_plans)
    block_outputs: set[str] = graph["block_outputs"]
    normalised: list[dict[str, Any]] = graph["normalised_plans"]
    ordered_writers: dict[str, list[dict[str, Any]]] = graph["ordered_writers"]

    # Group normalised plans by source_file; preserve insertion order for determinism.
    groups: dict[str, list[dict[str, Any]]] = {}
    for bp in normalised:
        source_file: str = bp.get("source_file", "") or ""
        group_key = source_file if source_file else "_misc"
        groups.setdefault(group_key, []).append(bp)

    # Global emitted set so a table produced in file A is not repeated in file B.
    emitted: set[str] = set()
    result_modules: dict[str, str] = {}

    for group_key in sorted(groups):
        group_plans = groups[group_key]
        file_lines: list[str] = []
        has_content = False

        # Determine the source stem for the module path and docstring.
        # group_key is either a SAS filename (e.g. "05_build_adam_adsl.sas") or "_misc".
        source_stem = os.path.basename(group_key) if group_key != "_misc" else "_misc"

        for bp in group_plans:
            output_datasets: list[str] = bp["output_datasets"]
            if not output_datasets:
                continue

            for output_ds in sorted(output_datasets):
                if output_ds in emitted:
                    continue
                emitted.add(output_ds)

                chain = ordered_writers.get(output_ds, [bp])
                table_lines = _emit_dlt_table(
                    output_ds, chain, block_outputs, per_block_code, schema
                )
                if not has_content:
                    file_lines.extend(_dlt_module_header(source_stem, resolved_target.storage_root))
                    has_content = True
                file_lines.extend(table_lines)

        if not has_content:
            continue

        module_path = f"transformations/{_slugify(os.path.splitext(source_stem)[0])}_dlt.py"
        result_modules[module_path] = "\n".join(file_lines)

    return result_modules


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
    dlt_modules: "dict[str, str] | None" = None,
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
        dlt_modules: Dict of ``transformations/<stem>_dlt.py`` → source produced
            by :func:`render_dlt_pipeline`. Keys are used to build the
            ``libraries`` list (sorted for byte-determinism). Pass ``None`` or
            ``{}`` to fall back to the legacy single-file path
            ``transformations/rosetta_<job_slug>_dlt.py``.
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

    # Build libraries list from the modular dict when provided; fall back to the
    # legacy single-file path so callers that pass no modules stay byte-identical.
    if dlt_modules:
        libraries = [{"file": {"path": f"./{path}"}} for path in sorted(dlt_modules)]
    else:
        libraries = [{"file": {"path": f"./transformations/rosetta_{job_slug}_dlt.py"}}]

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
                    "libraries": libraries,
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

    return _format_yaml(bundle_doc)


# ---------------------------------------------------------------------------
# F76 — Classic Spark Job delivery format
# ---------------------------------------------------------------------------


def _spark_job_module_folded(
    output_ds: str,
    first_bp: dict[str, Any],
    body_lines: list[str],
    is_stub: bool,
    stub_manual_lines: list[str],
) -> str:
    """Render one ``jobs/<task_key>.py`` module for a single output dataset.

    Accepts a pre-built body (from ``_fold_chain_body`` or an empty list for
    stubs) so the caller controls folding logic while this function handles
    the module scaffold (imports, CATALOG/SCHEMA, saveAsTable footer).

    Args:
        output_ds: Normalised output dataset stem (the Delta table name).
        first_bp: First writer's block plan (for provenance comment).
        body_lines: Pre-built code lines from ``_fold_chain_body``, or ``[]``.
        is_stub: If True, emit ``raise NotImplementedError`` instead of body.
        stub_manual_lines: ``# MANUAL:`` comment lines to emit before the stub.

    Returns:
        Byte-deterministic Python source string for the task module.
    """
    # SAS: databricks_bundle.py:_spark_job_module_folded
    source_file: str = first_bp.get("source_file", "")
    start_line: int = first_bp.get("start_line", 0)
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

    if is_stub:
        for manual_line in stub_manual_lines:
            lines.append(manual_line)
        lines.append(
            'raise NotImplementedError("Untranslatable SAS block — manual migration required")'
        )
        lines.append("")
        return "\n".join(lines)

    lines.append('CATALOG = os.environ.get("ROSETTA_CATALOG", "main")')
    lines.append('SCHEMA = os.environ.get("ROSETTA_SCHEMA", "default")')
    lines.append("")
    if body_lines:
        lines.extend(body_lines)
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

    When multiple blocks write the same dataset (build + in-place rewrite
    pattern) they are folded into one module body in ``(source_file,
    start_line)`` order via :func:`_fold_chain_body`, producing exactly one
    ``jobs/<task_key>.py`` per dataset (no silent last-writer-wins overwrite).

    Zero-output blocks are skipped. Untranslatable or ambiguous multi-output-in-
    chain blocks emit a ``raise NotImplementedError`` module.

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
    normalised: list[dict[str, Any]] = graph["normalised_plans"]
    ordered_writers: dict[str, list[dict[str, Any]]] = graph["ordered_writers"]

    modules: dict[str, str] = {}
    emitted: set[str] = set()

    for bp in normalised:
        output_datasets: list[str] = bp["output_datasets"]
        if not output_datasets:
            continue

        for output_ds in sorted(output_datasets):
            if output_ds in emitted:
                continue
            emitted.add(output_ds)

            chain = ordered_writers.get(output_ds, [bp])
            is_stub = _dlt_is_stub(chain, per_block_code)
            stub_manual_lines: list[str] = []

            if is_stub:
                for chain_bp in chain:
                    bp_code = per_block_code.get(chain_bp.get("block_id", ""), "") or ""
                    if not bp_code.strip() or "# SAS-UNRECOGNIZED" in bp_code:
                        sf = chain_bp.get("source_file", "")
                        sl = chain_bp.get("start_line", 0)
                        stub_manual_lines.append(f"# MANUAL: {sf}:{sl} — untranslatable")
                body_lines: list[str] = []
            else:
                body_lines = _fold_chain_body(
                    output_ds, chain, block_outputs, per_block_code, "job"
                )

            task_key = _slugify(output_ds)
            first_writer = ordered_writers.get(output_ds, [bp])[0]
            raw_sf: str = first_writer.get("source_file", "")
            source_stem = _slugify(raw_sf.rsplit(".", 1)[0]) if raw_sf else "_misc"
            modules[f"jobs/{source_stem}/{task_key}.py"] = _spark_job_module_folded(
                output_ds, chain[0], body_lines, is_stub, stub_manual_lines
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
        source_stem = datasets.get("dataset_source_file", {}).get(ds, "_misc")
        task: dict[str, Any] = {
            "task_key": task_key,
            "spark_python_task": {"python_file": f"./jobs/{source_stem}/{task_key}.py"},
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

    return _format_yaml(bundle_doc)
