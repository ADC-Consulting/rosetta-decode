"""SAS source parser — extracts DATA step and PROC SQL blocks, ordered by dependency.

Uses regex-based extraction (not a full grammar) for the MVP construct set:
- DATA step  (DATA … RUN;)
- PROC SQL   (PROC SQL … QUIT;)

All other PROC types are flagged as UNTRANSLATABLE and preserved as comments.
Multi-file input is dependency-ordered using networkx so that a block that
reads a dataset produced by another block is always translated after it.
"""

import re
from collections.abc import Iterator

import networkx as nx
from src.worker.engine.models import (
    BlockType,
    MacroVar,
    ParseResult,
    SASBlock,
)

# ── Regex patterns ────────────────────────────────────────────────────────────

# DATA step: DATA <name(s)>; … SET <name>; … RUN;
_DATA_STEP_RE = re.compile(
    r"(?i)(DATA\s+\S[^;]*;.*?RUN\s*;)",
    re.DOTALL,
)

# PROC SQL block: PROC SQL; … QUIT;
_PROC_SQL_RE = re.compile(
    r"(?i)(PROC\s+SQL\b.*?QUIT\s*;)",
    re.DOTALL,
)

# Unsupported PROC types that are not PROC SQL
_UNSUPPORTED_PROC_RE = re.compile(
    r"(?i)(PROC\s+(?!SQL\b)\w+\b.*?(?:RUN|QUIT)\s*;)",
    re.DOTALL,
)

# Map PROC name (uppercase) → BlockType; unfamiliar PROCs → PROC_UNKNOWN
_KNOWN_PROCS: dict[str, BlockType] = {
    "SORT": BlockType.PROC_SORT,
    "SQL": BlockType.PROC_SQL,
    "IML": BlockType.PROC_IML,
    "FCMP": BlockType.PROC_FCMP,
    "MEANS": BlockType.PROC_MEANS,
    "SUMMARY": BlockType.PROC_MEANS,  # PROC SUMMARY ≈ PROC MEANS
    "FREQ": BlockType.PROC_FREQ,
    "TRANSPOSE": BlockType.PROC_TRANSPOSE,
    "IMPORT": BlockType.PROC_IMPORT,
    "EXPORT": BlockType.PROC_EXPORT,
    "PRINT": BlockType.PROC_PRINT,
    "CONTENTS": BlockType.PROC_CONTENTS,
    "DATASETS": BlockType.PROC_DATASETS,
    "OPTMODEL": BlockType.PROC_OPTMODEL,
}

# Extract DATA output name(s) from "DATA name1 name2;"
_DATA_OUTPUT_RE = re.compile(r"(?i)DATA\s+([\w\s.]+?)\s*;")

# Extract SET input name(s) from "SET name1 name2;"
_DATA_INPUT_RE = re.compile(r"(?i)\bSET\s+([\w\s.]+?)\s*;")

# Extract FROM / JOIN table references in PROC SQL
_SQL_FROM_RE = re.compile(r"(?i)\b(?:FROM|JOIN)\s+([\w.]+)")

# Extract CREATE TABLE target in PROC SQL
_SQL_CREATE_RE = re.compile(r"(?i)CREATE\s+TABLE\s+([\w.]+)\s+AS")

# PROC SORT block: PROC SORT … RUN;
_PROC_SORT_RE = re.compile(
    r"(?i)(PROC\s+SORT\b.*?RUN\s*;)",
    re.DOTALL,
)

# Extract DATA= dataset name from PROC SORT header
_SORT_DATA_RE = re.compile(r"(?i)\bDATA\s*=\s*(\w[\w.]*)")

# Extract OUT= dataset name from PROC SORT header (optional)
_SORT_OUT_RE = re.compile(r"(?i)\bOUT\s*=\s*(\w[\w.]*)")

# %LET macro variable declaration
_LET_RE = re.compile(r"(?i)%LET\s+(\w+)\s*=\s*([^;]+?)\s*;")


# ── Line-number helpers ───────────────────────────────────────────────────────


def _line_of(text: str, char_offset: int) -> int:
    """Return the 1-based line number for a character offset within *text*."""
    return text[:char_offset].count("\n") + 1


def _extract_names(pattern: re.Pattern[str], text: str) -> list[str]:
    """Return a flat list of lowercased dataset names matched by *pattern*."""
    names: list[str] = []
    for match in pattern.finditer(text):
        names.extend(n.strip().lower() for n in match.group(1).split() if n.strip())
    return names


# ── Block extractors ─────────────────────────────────────────────────────────


def _extract_data_steps(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every DATA step found in *source*."""
    for match in _DATA_STEP_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        outputs = _extract_names(_DATA_OUTPUT_RE, raw)
        inputs = _extract_names(_DATA_INPUT_RE, raw)
        yield SASBlock(
            block_type=BlockType.DATA_STEP,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )


def _extract_proc_sql(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every PROC SQL block found in *source*."""
    for match in _PROC_SQL_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        inputs = _extract_names(_SQL_FROM_RE, raw)
        outputs = _extract_names(_SQL_CREATE_RE, raw)
        yield SASBlock(
            block_type=BlockType.PROC_SQL,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )


def _extract_proc_sort(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every PROC SORT block found in *source*."""
    for match in _PROC_SORT_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        data_match = _SORT_DATA_RE.search(raw)
        out_match = _SORT_OUT_RE.search(raw)
        inputs = [data_match.group(1).lower()] if data_match else []
        outputs = [out_match.group(1).lower()] if out_match else inputs[:]
        yield SASBlock(
            block_type=BlockType.PROC_SORT,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )


def _extract_macro_vars(source: str, filename: str) -> list[MacroVar]:
    """Return a MacroVar for every %LET declaration in *source*."""
    result: list[MacroVar] = []
    for match in _LET_RE.finditer(source):
        result.append(
            MacroVar(
                name=match.group(1),
                raw_value=match.group(2),
                source_file=filename,
                line=_line_of(source, match.start()),
            )
        )
    return result


def _extract_unsupported_procs(
    source: str, filename: str, covered_spans: list[tuple[int, int]]
) -> Iterator[SASBlock]:
    """Yield typed PROC blocks for PROC types other than PROC SQL/SORT.

    Each matched PROC is assigned the most specific BlockType available from
    ``_KNOWN_PROCS``.  Unfamiliar PROCs receive ``BlockType.PROC_UNKNOWN``.
    ``BlockType.UNTRANSLATABLE`` is reserved for genuinely unparsable SAS only.

    Skips any match whose span overlaps an already-covered (DATA/PROC SQL/SORT) span.
    """
    for match in _UNSUPPORTED_PROC_RE.finditer(source):
        span = (match.start(), match.end())
        if any(span[0] < c[1] and span[1] > c[0] for c in covered_spans):
            continue
        raw = match.group(1)
        proc_name_match = re.search(r"(?i)PROC\s+(\w+)", raw)
        proc_name = proc_name_match.group(1).upper() if proc_name_match else "UNKNOWN"
        block_type = _KNOWN_PROCS.get(proc_name, BlockType.PROC_UNKNOWN)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        # Best-effort dataset extraction for known I/O-producing PROCs
        data_match = re.search(r"(?i)\bDATA\s*=\s*(\w[\w.]*)", raw)
        out_match = re.search(r"(?i)\bOUT\s*=\s*(\w[\w.]*)", raw)
        inputs = [data_match.group(1).lower()] if data_match else []
        outputs = [out_match.group(1).lower()] if out_match else []
        yield SASBlock(
            block_type=block_type,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )


# ── Dependency ordering ───────────────────────────────────────────────────────


def _topological_sort(blocks: list[SASBlock]) -> list[SASBlock]:
    """Return *blocks* in dependency order using a DAG on dataset names.

    Blocks without inter-dependencies retain their original relative order.
    Cycles are broken by falling back to the original order (best-effort).
    """
    # Map output dataset → index of the block that produces it
    producer: dict[str, int] = {}
    for idx, block in enumerate(blocks):
        for ds in block.output_datasets:
            producer[ds] = idx

    graph: nx.DiGraph = nx.DiGraph()
    graph.add_nodes_from(range(len(blocks)))

    for idx, block in enumerate(blocks):
        for ds in block.input_datasets:
            if ds in producer and producer[ds] != idx:
                graph.add_edge(producer[ds], idx)  # producer must come first

    try:
        order = list(nx.topological_sort(graph))
    except nx.NetworkXUnfeasible:
        # Cycle detected — fall back to original order
        order = list(range(len(blocks)))

    return [blocks[i] for i in order]


# ── Lineage extraction ────────────────────────────────────────────────────────


def extract_lineage(blocks: list[SASBlock], job_id: str) -> dict:  # type: ignore[type-arg]
    """Build a JSON-serializable lineage graph from parsed SAS blocks.

    Creates one LineageNode per block and one LineageEdge per dataset flowing
    from a producer block to a consumer block.  The returned dict matches the
    ``JobLineageResponse`` schema used by the API.

    Args:
        blocks: Dependency-ordered list of SAS blocks from SASParser.parse().
        job_id: String UUID of the owning job (embedded in the response).

    Returns:
        Plain dict with keys ``job_id``, ``nodes``, and ``edges``, all
        JSON-serializable.
    """
    # Build node list and an index from output dataset name → node id.
    nodes: list[dict[str, str]] = []
    producer_map: dict[str, str] = {}  # dataset name → node id

    for block in blocks:
        node_id = f"{block.source_file}::{block.start_line}"
        label = getattr(block, "name", None) or block.block_type.value
        status = "untranslatable" if block.block_type == BlockType.UNTRANSLATABLE else "migrated"

        nodes.append(
            {
                "id": node_id,
                "label": label,
                "source_file": block.source_file,
                "block_type": block.block_type.value,
                "status": status,
            }
        )
        for ds in block.output_datasets:
            producer_map[ds] = node_id

    # Build edge list from input→output dataset flow.
    edges: list[dict[str, object]] = []
    for block in blocks:
        target_id = f"{block.source_file}::{block.start_line}"
        for ds in block.input_datasets:
            source_id = producer_map.get(ds)
            if source_id is not None and source_id != target_id:
                edges.append(
                    {
                        "source": source_id,
                        "target": target_id,
                        "dataset": ds,
                        "inferred": False,
                    }
                )

    return {"job_id": job_id, "nodes": nodes, "edges": edges}


# ── Public API ────────────────────────────────────────────────────────────────


class SASParser:
    """Extract and dependency-order SAS blocks from one or more source files."""

    def parse(self, files: dict[str, str]) -> ParseResult:
        """Parse SAS source files and return dependency-ordered blocks with macro vars.

        Args:
            files: Mapping of filename to SAS source text.

        Returns:
            ParseResult containing SASBlock list in dependency order and all
            MacroVar declarations found across all files.
        """
        all_blocks: list[SASBlock] = []
        all_macro_vars: list[MacroVar] = []

        for filename, source in files.items():
            covered: list[tuple[int, int]] = []

            for match in _DATA_STEP_RE.finditer(source):
                covered.append((match.start(), match.end()))
            for match in _PROC_SQL_RE.finditer(source):
                covered.append((match.start(), match.end()))
            for match in _PROC_SORT_RE.finditer(source):
                covered.append((match.start(), match.end()))

            all_blocks.extend(_extract_data_steps(source, filename))
            all_blocks.extend(_extract_proc_sql(source, filename))
            all_blocks.extend(_extract_proc_sort(source, filename))
            all_blocks.extend(_extract_unsupported_procs(source, filename, covered))
            all_macro_vars.extend(_extract_macro_vars(source, filename))

        return ParseResult(blocks=_topological_sort(all_blocks), macro_vars=all_macro_vars)
