"""POST /analyse — stateless pre-migration assessment endpoint.

Accepts the same multipart fields as POST /migrate, runs SASParser
synchronously via asyncio.to_thread, computes structural analysis, and
returns an AnalyseResponse. No DB write; no job created.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import logging
import os
import re
from collections import defaultdict, deque
from collections.abc import Iterable

import networkx as nx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from src.backend.api.schemas import (
    AnalyseResponse,
    AssessedBlock,
    CircularDependency,
    ConfigurationValue,
    MissingDependency,
    OutputCoverage,
    PreviewStats,
    SensitiveDataFinding,
)
from src.backend.core.config import settings
from src.worker.engine.models import BlockType, ParseResult, SASBlock
from src.worker.engine.parser import SASParser

logger = logging.getLogger(__name__)

router = APIRouter()

# ── PII column patterns ───────────────────────────────────────────────────────

_PII_PATTERNS: frozenset[str] = frozenset(
    {
        "SSN",
        "SOCIAL_SECURITY",
        "SIN",
        "DOB",
        "DATE_OF_BIRTH",
        "BIRTH_DATE",
        "PATIENT_ID",
        "MEMBER_ID",
        "BENEFICIARY_ID",
        "NPI",
        "ACCOUNT_NUM",
        "ACCOUNT_NUMBER",
        "ACCT_NO",
        "CREDIT_CARD",
        "CARD_NUMBER",
        "PAN",
        "EMAIL",
        "EMAIL_ADDR",
        "PHONE",
        "PHONE_NUM",
        "MOBILE",
        "PASSPORT",
        "PASSPORT_NUM",
        "PASSWORD",
        "PASSWD",
    }
)

# ── Functional description mapping ────────────────────────────────────────────

_FUNCTIONAL_DESCRIPTIONS: dict[str, str] = {
    BlockType.DATA_STEP: "Data transformation step",
    BlockType.PROC_SQL: "SQL query / join",
    BlockType.PROC_IML: "Matrix / statistical computation",
    BlockType.PROC_FCMP: "Custom function definition",
    BlockType.PROC_SORT: "Data sorting step",
    BlockType.PROC_IMPORT: "File ingestion step",
    BlockType.PROC_EXPORT: "File export step",
    BlockType.PROC_MEANS: "Statistical summary",
    BlockType.PROC_FREQ: "Frequency / cross-tabulation",
    BlockType.PROC_TRANSPOSE: "Data reshape / transpose",
    BlockType.PROC_RANK: "Ranking / quantile assignment",
    BlockType.PROC_APPEND: "Dataset append",
    BlockType.PROC_UNKNOWN: "Custom step (unrecognised type)",
    BlockType.UNTRANSLATABLE: "Unrecognised construct — cannot auto-translate",
}

# ── Importance helpers ────────────────────────────────────────────────────────

_LOW_IMPORTANCE_TYPES: frozenset[str] = frozenset(
    {
        BlockType.PROC_PRINT,
        BlockType.PROC_CONTENTS,
        BlockType.PROC_DATASETS,
    }
)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YEAR_4_RE = re.compile(r"^\d{4}$")
_ENV_NAMES_RE = re.compile(r"\b(PROD|DEV|UAT|TEST|STAGING)\b", re.IGNORECASE)


def _functional_description(block_type: str) -> str:
    """Return a plain-English description for a given block type.

    Args:
        block_type: The SAS block type value string.

    Returns:
        Human-readable description string.
    """
    return _FUNCTIONAL_DESCRIPTIONS.get(block_type, "Processing step")


def _looks_dynamic(value: str) -> bool:
    """Return True when a macro value looks like a configurable runtime value.

    Args:
        value: The raw macro variable value.

    Returns:
        True if the value matches ISO date, env name, file path, or 4-digit year.
    """
    if _ISO_DATE_RE.match(value):
        return True
    if _ENV_NAMES_RE.search(value):
        return True
    if "/" in value or "\\" in value:
        return True
    if _YEAR_4_RE.match(value):
        try:
            year = int(value)
            return year >= 2000
        except ValueError:
            pass
    return False


def _build_dep_graph(blocks: list[SASBlock]) -> nx.DiGraph:
    """Build a directed dataset dependency graph from parsed blocks.

    Nodes are dataset names (lowercase). An edge from A → B means dataset
    A is produced by some block and consumed as input to a block that
    produces B.

    Args:
        blocks: Parsed SAS blocks with input_datasets / output_datasets.

    Returns:
        Directed graph of dataset dependencies.
    """
    graph: nx.DiGraph = nx.DiGraph()
    # dataset → set of output datasets produced by blocks that consume it
    for block in blocks:
        for inp in block.input_datasets:
            for out in block.output_datasets:
                graph.add_edge(inp.lower(), out.lower())
    # Add isolated dataset nodes
    for block in blocks:
        for ds in block.input_datasets + block.output_datasets:
            if not graph.has_node(ds.lower()):
                graph.add_node(ds.lower())
    return graph


def _blast_radius_for_block(block: SASBlock, graph: nx.DiGraph) -> list[str]:
    """Compute datasets affected downstream if this block is wrong.

    Uses BFS forward from each of the block's output datasets.

    Args:
        block: The SAS block whose blast radius to compute.
        graph: Dataset dependency graph.

    Returns:
        Sorted list of downstream dataset names (excluding the block's own outputs).
    """
    frontier: deque[str] = deque()
    visited: set[str] = set()

    for ds in block.output_datasets:
        node = ds.lower()
        if graph.has_node(node):
            frontier.append(node)
            visited.add(node)

    downstream: set[str] = set()
    while frontier:
        current = frontier.popleft()
        for succ in graph.successors(current):
            downstream.add(succ)
            if succ not in visited:
                visited.add(succ)
                frontier.append(succ)

    # Exclude the block's own output datasets from the radius
    own_outputs = {ds.lower() for ds in block.output_datasets}
    return sorted(downstream - own_outputs)


def _compute_structural_importance(
    block: SASBlock,
    terminal_outputs: set[str],
    fanout_map: dict[str, int],
) -> tuple[str, str]:
    """Return (importance_level, reason) for a parsed SAS block.

    Args:
        block: The block to assess.
        terminal_outputs: Set of dataset names that are terminal (not consumed downstream).
        fanout_map: Maps dataset name → number of downstream blocks that read it.

    Returns:
        Tuple of importance level ("low"/"medium"/"high") and reason string.
    """
    bt = block.block_type

    # Hard LOW types
    if bt in _LOW_IMPORTANCE_TYPES:
        return "low", "diagnostic / reporting step"

    # Pipeline entry/exit
    if bt == BlockType.PROC_IMPORT:
        return "high", "pipeline entry"
    if bt == BlockType.PROC_EXPORT:
        return "high", "pipeline exit"

    # Terminal output dataset (not consumed downstream)
    for ds in block.output_datasets:
        if ds.lower() in terminal_outputs:
            return "high", "terminal output"

    # Fan-out based
    max_fanout = max((fanout_map.get(ds.lower(), 0) for ds in block.output_datasets), default=0)
    if max_fanout >= 3:
        return "high", f"feeds {max_fanout} downstream blocks"
    if max_fanout >= 1:
        return "medium", f"feeds {max_fanout} downstream block(s)"

    return "low", "isolated — no downstream consumers"


def _detect_missing_deps(
    parse_result: ParseResult,
    uploaded_filenames: list[str],
    uploaded_data_stems: set[str],
) -> list[MissingDependency]:
    """Find %include references and dataset names not present in uploaded files.

    Args:
        parse_result: Parsed SAS result with includes and block dataset lists.
        uploaded_filenames: Filenames of all uploaded files (SAS + data).
        uploaded_data_stems: Stems of uploaded non-SAS data files.

    Returns:
        List of MissingDependency records.
    """
    missing: list[MissingDependency] = []
    uploaded_set = {f.lower() for f in uploaded_filenames}

    # %include references
    for inc_path in parse_result.includes:
        inc_name = os.path.basename(inc_path).lower()
        if inc_name not in uploaded_set:
            missing.append(
                MissingDependency(
                    name=inc_path,
                    referenced_in=inc_path,
                    dependency_type="file",
                )
            )

    # Dataset references not matched by any uploaded file or already produced block
    produced: set[str] = set()
    for block in parse_result.blocks:
        for ds in block.output_datasets:
            produced.add(ds.lower())

    for block in parse_result.blocks:
        for ds in block.input_datasets:
            ds_lower = ds.lower()
            if ds_lower not in produced and ds_lower not in uploaded_data_stems:
                block_ref = f"{block.source_file}:{block.start_line}"
                missing.append(
                    MissingDependency(
                        name=ds,
                        referenced_in=block_ref,
                        dependency_type="dataset",
                    )
                )

    return missing


def _detect_circular_deps(graph: nx.DiGraph) -> list[CircularDependency]:
    """Detect cycles in the dataset dependency graph.

    Args:
        graph: Directed dataset dependency graph.

    Returns:
        List of CircularDependency records, one per detected cycle.
    """
    try:
        cycle_edges = nx.find_cycle(graph)
        # Extract node names from the cycle edges
        cycle_nodes = [edge[0] for edge in cycle_edges]
        return [CircularDependency(cycle=cycle_nodes)]
    except nx.NetworkXNoCycle:
        return []


def _check_pii_in_columns(col_names: Iterable[str], source: str) -> list[SensitiveDataFinding]:
    """Match a column name list against known PII patterns.

    Args:
        col_names: Column names to check.
        source: Description of where these columns came from (for the finding).

    Returns:
        List of SensitiveDataFinding records for any matched PII columns.
    """
    findings: list[SensitiveDataFinding] = []
    for col in col_names:
        upper = col.upper()
        for pattern in _PII_PATTERNS:
            if pattern in upper:
                findings.append(SensitiveDataFinding(pattern=pattern, found_in=source))
                break
    return findings


def _read_sas7bdat_columns(path: str) -> list[str]:
    """Read column names from a .sas7bdat file using pyreadstat (metadata only).

    Args:
        path: Absolute path to the .sas7bdat file.

    Returns:
        List of column names, or empty list if unreadable.
    """
    try:
        import pyreadstat

        _, meta = pyreadstat.read_sas7bdat(path, metadataonly=True)
        return list(meta.column_names)
    except Exception as exc:
        logger.warning("Could not read sas7bdat metadata from %s: %s", path, exc)
        return []


def _read_csv_columns_and_rows(path: str) -> tuple[list[str], int | None]:
    """Read column names and row count from a CSV file.

    Args:
        path: Absolute path to the CSV file.

    Returns:
        Tuple of (column_names, row_count).
    """
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            cols = list(reader.fieldnames or [])
            rows = sum(1 for _ in reader)
        return cols, rows
    except Exception as exc:
        logger.warning("Could not read CSV metadata from %s: %s", path, exc)
        return [], None


# ── LLM description helper ────────────────────────────────────────────────────


async def _generate_pipeline_description(
    filenames: list[str],
    all_datasets: list[str],
    block_type_counts: dict[str, int],
    largest_sas_content: str,
) -> str | None:
    """Call the LLM for a 2-3 sentence plain-English pipeline description.

    Uses the same LLMClient / model pattern as the worker.

    Args:
        filenames: Names of uploaded SAS files.
        all_datasets: All dataset names seen across all blocks.
        block_type_counts: Mapping of block_type → count.
        largest_sas_content: First 100 lines of the largest SAS file.

    Returns:
        Generated description string, or None on failure.
    """
    from src.worker.engine.llm_client import LLMClient

    counts_text = ", ".join(f"{bt}: {n}" for bt, n in sorted(block_type_counts.items()))
    preview_lines = "\n".join(largest_sas_content.splitlines()[:100])

    prompt = (
        "You are a SAS migration expert. In 2-3 sentences, describe what the following "
        "SAS pipeline does in plain English for a business stakeholder. "
        "Focus on the business purpose, not the technical implementation.\n\n"
        f"Files: {', '.join(filenames)}\n"
        f"Datasets: {', '.join(all_datasets[:20])}\n"
        f"Block types: {counts_text}\n\n"
        f"SAS source preview:\n{preview_lines}"
    )

    client = LLMClient()
    return await client.generate_text(prompt)


# ── Main handler ──────────────────────────────────────────────────────────────


@router.post("/analyse", response_model=AnalyseResponse, status_code=200)
async def analyse(
    sas_files: list[UploadFile] = File(default=[]),
    ref_dataset: UploadFile | None = None,
    zip_file: UploadFile | None = None,
    ref_csv: UploadFile | None = None,
    ref_target_path: str | None = Form(default=None),
) -> AnalyseResponse:
    """Run a stateless pre-migration assessment on uploaded SAS files.

    Accepts the same multipart fields as POST /migrate. Runs SASParser
    synchronously and computes structural analysis. Returns AnalyseResponse.
    No database write is performed; no job is created.

    Args:
        sas_files: One or more .sas files to analyse.
        ref_dataset: Optional .sas7bdat reference dataset.
        zip_file: Optional zip archive (mutually exclusive with sas_files).
        ref_csv: Optional CSV reference dataset.
        ref_target_path: Unused — accepted for interface symmetry with /migrate.

    Returns:
        AnalyseResponse with full assessment data.

    Raises:
        HTTPException: 400 if no SAS files are provided.
    """
    # ── Collect uploaded SAS file contents ────────────────────────────────────
    file_contents: dict[str, str] = {}
    data_file_paths: dict[str, str] = {}  # stem → disk path
    uploaded_filenames: list[str] = []
    hasher = hashlib.sha256()

    if zip_file is not None:
        import io as _io
        import zipfile

        raw = await zip_file.read()
        hasher.update(raw)
        _accepted_zip_exts = {".sas", ".sas7bdat", ".csv"}
        with zipfile.ZipFile(_io.BytesIO(raw)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                norm = info.filename.replace("\\", "/").lstrip("/")
                name = os.path.basename(norm)
                if not name or name.startswith("._") or norm.startswith("__MACOSX/"):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext not in _accepted_zip_exts:
                    continue
                data = zf.read(info.filename)
                if ext == ".sas":
                    file_contents[name] = data.decode("utf-8", errors="replace")
                    uploaded_filenames.append(name)
                else:
                    # write to temp for metadata reading
                    tmp_path = os.path.join(
                        settings.upload_dir, f"analyse_{hasher.hexdigest()[:8]}_{name}"
                    )
                    os.makedirs(settings.upload_dir, exist_ok=True)
                    with open(tmp_path, "wb") as fh:
                        fh.write(data)
                    stem = os.path.splitext(name)[0].lower()
                    data_file_paths[stem] = tmp_path
                    uploaded_filenames.append(name)
    elif sas_files:
        for upload in sas_files:
            filename = upload.filename or "unnamed.sas"
            raw = await upload.read()
            hasher.update(raw)
            if filename.lower().endswith(".sas"):
                file_contents[filename] = raw.decode("utf-8", errors="replace")
                uploaded_filenames.append(filename)
    else:
        raise HTTPException(status_code=400, detail="At least one .sas file is required.")

    if not file_contents:
        raise HTTPException(status_code=400, detail="At least one .sas file is required.")

    # Handle ref_dataset and ref_csv
    if ref_dataset is not None:
        ref_name = ref_dataset.filename or "ref.sas7bdat"
        ref_raw = await ref_dataset.read()
        tmp_dir = settings.upload_dir
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_path = os.path.join(tmp_dir, f"analyse_{hasher.hexdigest()[:8]}_{ref_name}")
        with open(tmp_path, "wb") as fh:
            fh.write(ref_raw)
        stem = os.path.splitext(ref_name)[0].lower()
        data_file_paths[stem] = tmp_path
        uploaded_filenames.append(ref_name)

    if ref_csv is not None:
        csv_name = ref_csv.filename or "reference.csv"
        csv_raw = await ref_csv.read()
        tmp_dir = settings.upload_dir
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_path = os.path.join(tmp_dir, f"analyse_{hasher.hexdigest()[:8]}_{csv_name}")
        with open(tmp_path, "wb") as fh:
            fh.write(csv_raw)
        stem = os.path.splitext(csv_name)[0].lower()
        data_file_paths[stem] = tmp_path
        uploaded_filenames.append(csv_name)

    input_hash = hasher.hexdigest()

    # ── Run parser in thread ──────────────────────────────────────────────────
    parser_warning: str | None = None
    parse_result: ParseResult = ParseResult()

    try:
        parse_result = await asyncio.to_thread(lambda: SASParser().parse(file_contents))
    except Exception as exc:
        logger.warning("SASParser failed: %s", exc)
        parser_warning = f"Parser error: {exc}"
        # Return minimal response on parser failure
        return AnalyseResponse(
            input_hash=input_hash,
            filenames=uploaded_filenames,
            input_sources=[],
            output_datasets=[],
            stats=PreviewStats(
                total_blocks=0,
                needs_manual=0,
                best_effort=0,
                review_recommended=0,
                auto_converts=0,
                macro_var_count=0,
                macro_def_count=0,
                estimated_minutes_low=0,
                estimated_minutes_high=0,
            ),
            blocks=[],
            missing_dependencies=[],
            circular_dependencies=[],
            output_coverage=[],
            configuration_values=[],
            sensitive_data_findings=[],
            parser_warning=parser_warning,
        )

    blocks = parse_result.blocks

    # ── Build dependency graph ────────────────────────────────────────────────
    dep_graph = _build_dep_graph(blocks)

    # Terminal outputs: produced by at least one block, not consumed by any block
    all_produced: set[str] = set()
    all_consumed: set[str] = set()
    for block in blocks:
        for ds in block.output_datasets:
            all_produced.add(ds.lower())
        for ds in block.input_datasets:
            all_consumed.add(ds.lower())
    terminal_outputs = all_produced - all_consumed

    # Fan-out map: dataset → number of blocks that consume it as input
    fanout_map: dict[str, int] = defaultdict(int)
    for block in blocks:
        for ds in block.input_datasets:
            fanout_map[ds.lower()] += 1

    # ── Compute per-block assessments ─────────────────────────────────────────
    assessed_blocks: list[AssessedBlock] = []

    for block in blocks:
        block_id = f"{block.source_file}:{block.start_line}"
        bt = block.block_type

        importance, reason = _compute_structural_importance(block, terminal_outputs, fanout_map)
        blast = _blast_radius_for_block(block, dep_graph)
        snippet = "\n".join(block.raw_sas.splitlines()[:10])

        is_translatable = bt != BlockType.UNTRANSLATABLE
        is_unknown_proc = bt == BlockType.PROC_UNKNOWN

        assessed_blocks.append(
            AssessedBlock(
                block_id=block_id,
                source_file=block.source_file,
                start_line=block.start_line,
                end_line=block.end_line,
                block_type=str(bt),
                functional_description=_functional_description(str(bt)),
                is_translatable=is_translatable,
                is_unknown_proc=is_unknown_proc,
                structural_importance=importance,
                importance_reason=reason,
                input_datasets=block.input_datasets,
                output_datasets=block.output_datasets,
                blast_radius=blast,
                raw_sas_snippet=snippet,
            )
        )

    # ── Stats ─────────────────────────────────────────────────────────────────
    needs_manual = sum(1 for b in assessed_blocks if not b.is_translatable)
    best_effort = sum(1 for b in assessed_blocks if b.is_unknown_proc)
    review_recommended = sum(
        1
        for b in assessed_blocks
        if b.structural_importance == "high" and b.is_translatable and not b.is_unknown_proc
    )
    auto_converts = len(assessed_blocks) - needs_manual - best_effort - review_recommended
    auto_converts = max(0, auto_converts)

    total = len(blocks)
    # Estimate: total_blocks x 45s / 60, +/-30%
    base_minutes = (total * 45) / 60
    est_low = max(0, int(base_minutes * 0.7))
    est_high = int(base_minutes * 1.3) + 1

    stats = PreviewStats(
        total_blocks=total,
        needs_manual=needs_manual,
        best_effort=best_effort,
        review_recommended=review_recommended,
        auto_converts=auto_converts,
        macro_var_count=len(parse_result.macro_vars),
        macro_def_count=len(parse_result.macro_defs),
        estimated_minutes_low=est_low,
        estimated_minutes_high=est_high,
    )

    # ── Missing dependencies ──────────────────────────────────────────────────
    uploaded_data_stems = {os.path.splitext(f)[0].lower() for f in uploaded_filenames}
    missing_deps = _detect_missing_deps(parse_result, uploaded_filenames, uploaded_data_stems)

    # ── Circular dependencies ─────────────────────────────────────────────────
    circular_deps = _detect_circular_deps(dep_graph)

    # ── Sensitive data findings ───────────────────────────────────────────────
    sensitive_findings: list[SensitiveDataFinding] = []

    # From .sas7bdat column metadata
    for _stem, path in data_file_paths.items():
        if path.lower().endswith(".sas7bdat"):
            cols = _read_sas7bdat_columns(path)
            sensitive_findings.extend(_check_pii_in_columns(cols, os.path.basename(path)))

    # From KEEP/DROP/VAR lists in blocks
    for block in blocks:
        all_cols = block.keep_cols + block.drop_cols + block.var_cols
        if all_cols:
            src = f"{block.source_file}:{block.start_line}"
            sensitive_findings.extend(_check_pii_in_columns(all_cols, src))

    # Deduplicate
    seen_findings: set[tuple[str, str]] = set()
    deduped_findings: list[SensitiveDataFinding] = []
    for f in sensitive_findings:
        key = (f.pattern, f.found_in)
        if key not in seen_findings:
            seen_findings.add(key)
            deduped_findings.append(f)
    sensitive_findings = deduped_findings

    # ── Configuration values ──────────────────────────────────────────────────
    config_values: list[ConfigurationValue] = []
    for mv in parse_result.macro_vars:
        config_values.append(
            ConfigurationValue(
                name=f"&{mv.name}",
                value=mv.raw_value,
                looks_dynamic=_looks_dynamic(mv.raw_value),
            )
        )

    # ── Output coverage ───────────────────────────────────────────────────────
    output_coverage: list[OutputCoverage] = []

    # Find terminal output datasets and assess coverage
    terminal_ds_names = sorted(terminal_outputs)
    if not terminal_ds_names and blocks:
        # Fallback: all produced datasets
        terminal_ds_names = sorted(all_produced)

    # importance for terminal datasets: look up from assessed blocks
    ds_importance_map: dict[str, str] = {}
    for ab in assessed_blocks:
        for ds in ab.output_datasets:
            if ds.lower() not in ds_importance_map:
                ds_importance_map[ds.lower()] = ab.structural_importance

    for ds in terminal_ds_names:
        ds_lower = ds.lower()
        ref_file: str | None = None
        row_count: int | None = None
        col_names: list[str] = []
        has_ref = False

        if ds_lower in data_file_paths:
            ref_path = data_file_paths[ds_lower]
            ref_file = os.path.basename(ref_path)
            has_ref = True
            if ref_path.lower().endswith(".sas7bdat"):
                col_names = _read_sas7bdat_columns(ref_path)
            elif ref_path.lower().endswith(".csv"):
                col_names, row_count = _read_csv_columns_and_rows(ref_path)

        output_coverage.append(
            OutputCoverage(
                dataset_name=ds,
                structural_importance=ds_importance_map.get(ds_lower, "low"),
                has_reference=has_ref,
                reference_filename=ref_file,
                row_count=row_count,
                column_names=col_names,
            )
        )

    # ── Input / output dataset summaries ─────────────────────────────────────
    input_sources = sorted(
        {ds for block in blocks for ds in block.input_datasets if ds.lower() not in all_produced}
    )
    output_datasets_list = sorted(terminal_outputs)

    # ── LLM pipeline description ──────────────────────────────────────────────
    pipeline_description: str | None = None
    llm_skipped = False

    # Build block type count map
    bt_counts: dict[str, int] = defaultdict(int)
    for block in blocks:
        bt_counts[str(block.block_type)] += 1

    # Find largest SAS file content
    largest_content = ""
    if file_contents:
        largest_content = max(file_contents.values(), key=len)

    all_datasets = sorted(all_produced | all_consumed)

    try:
        pipeline_description = await _generate_pipeline_description(
            filenames=list(file_contents.keys()),
            all_datasets=all_datasets,
            block_type_counts=dict(bt_counts),
            largest_sas_content=largest_content,
        )
    except Exception as exc:
        logger.warning("LLM pipeline description failed: %s", exc)
        llm_skipped = True

    return AnalyseResponse(
        input_hash=input_hash,
        filenames=uploaded_filenames,
        input_sources=input_sources,
        output_datasets=output_datasets_list,
        stats=stats,
        blocks=assessed_blocks,
        missing_dependencies=missing_deps,
        circular_dependencies=circular_deps,
        output_coverage=output_coverage,
        configuration_values=config_values,
        sensitive_data_findings=sensitive_findings,
        pipeline_description=pipeline_description,
        parser_warning=parser_warning,
        llm_skipped=llm_skipped,
    )
