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
from src.worker.engine.models import BlockType, SASBlock

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

# Extract DATA output name(s) from "DATA name1 name2;"
_DATA_OUTPUT_RE = re.compile(r"(?i)DATA\s+([\w\s.]+?)\s*;")

# Extract SET input name(s) from "SET name1 name2;"
_DATA_INPUT_RE = re.compile(r"(?i)\bSET\s+([\w\s.]+?)\s*;")

# Extract FROM / JOIN table references in PROC SQL
_SQL_FROM_RE = re.compile(r"(?i)\b(?:FROM|JOIN)\s+([\w.]+)")

# Extract CREATE TABLE target in PROC SQL
_SQL_CREATE_RE = re.compile(r"(?i)CREATE\s+TABLE\s+([\w.]+)\s+AS")


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


def _extract_unsupported_procs(
    source: str, filename: str, covered_spans: list[tuple[int, int]]
) -> Iterator[SASBlock]:
    """Yield UNTRANSLATABLE blocks for PROC types other than PROC SQL.

    Skips any match whose span overlaps an already-covered (DATA/PROC SQL) span.
    """
    for match in _UNSUPPORTED_PROC_RE.finditer(source):
        span = (match.start(), match.end())
        if any(span[0] < c[1] and span[1] > c[0] for c in covered_spans):
            continue
        raw = match.group(1)
        proc_name_match = re.search(r"(?i)PROC\s+(\w+)", raw)
        proc_name = proc_name_match.group(1).upper() if proc_name_match else "UNKNOWN"
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        yield SASBlock(
            block_type=BlockType.UNTRANSLATABLE,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            untranslatable_reason=f"PROC {proc_name} has no automated translation rule",
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


# ── Public API ────────────────────────────────────────────────────────────────


class SASParser:
    """Extract and dependency-order SAS blocks from one or more source files."""

    def parse(self, files: dict[str, str]) -> list[SASBlock]:
        """Parse SAS source files and return dependency-ordered blocks.

        Args:
            files: Mapping of filename to SAS source text.

        Returns:
            List of SASBlock in the order they should be translated, with
            blocks that produce datasets appearing before blocks that consume them.
        """
        all_blocks: list[SASBlock] = []

        for filename, source in files.items():
            covered: list[tuple[int, int]] = []

            for match in _DATA_STEP_RE.finditer(source):
                covered.append((match.start(), match.end()))
            for match in _PROC_SQL_RE.finditer(source):
                covered.append((match.start(), match.end()))

            all_blocks.extend(_extract_data_steps(source, filename))
            all_blocks.extend(_extract_proc_sql(source, filename))
            all_blocks.extend(_extract_unsupported_procs(source, filename, covered))

        return _topological_sort(all_blocks)
