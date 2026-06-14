"""SAS source parser — extracts DATA step and PROC blocks, ordered by dependency.

Uses regex-based extraction (not a full grammar) for the supported construct set:
- DATA step      (DATA … RUN;)
- PROC SQL       (PROC SQL … QUIT;)
- PROC SORT      (PROC SORT … RUN;)
- PROC MEANS     (PROC MEANS/SUMMARY … RUN;)
- PROC FREQ      (PROC FREQ … RUN;)
- PROC TRANSPOSE (PROC TRANSPOSE … RUN;)
- PROC IMPORT    (PROC IMPORT … RUN;)
- PROC APPEND    (PROC APPEND … RUN;)
- PROC RANK      (PROC RANK … RUN;)

All other PROC types are flagged as PROC_UNKNOWN/UNTRANSLATABLE and preserved
as comments. Multi-file input is dependency-ordered using networkx so that a
block that reads a dataset produced by another block is always translated
after it.
"""

import heapq
import re
from collections.abc import Iterator

import networkx as nx
from src.worker.engine.models import (
    BlockType,
    MacroDef,
    MacroVar,
    ParseResult,
    SASBlock,
)

# ── Regex patterns ────────────────────────────────────────────────────────────

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_block_comments(source: str) -> str:
    """Replace /* ... */ comments with whitespace, preserving newlines.

    Line numbers in the stripped string match the original so that
    start_line / end_line calculations remain accurate.
    """

    def _replace(m: re.Match[str]) -> str:
        text = m.group(0)
        return re.sub(r"[^\n]", " ", text)

    return _BLOCK_COMMENT_RE.sub(_replace, source)


# DATA step: DATA <name(s)>; … RUN;
_DATA_STEP_RE = re.compile(
    r"(?i)(DATA\s+\S[^;]*;.*?RUN\s*;)",
    re.DOTALL,
)

# PROC SQL block: PROC SQL; … QUIT;
_PROC_SQL_RE = re.compile(
    r"(?i)(PROC\s+SQL\b.*?QUIT\s*;)",
    re.DOTALL,
)

# PROC SORT block: PROC SORT … RUN;
_PROC_SORT_RE = re.compile(
    r"(?i)(PROC\s+SORT\b.*?RUN\s*;)",
    re.DOTALL,
)

# PROC MEANS / SUMMARY
_PROC_MEANS_RE = re.compile(
    r"(?i)(PROC\s+(?:MEANS|SUMMARY)\b.*?RUN\s*;)",
    re.DOTALL,
)

# PROC FREQ
_PROC_FREQ_RE = re.compile(
    r"(?i)(PROC\s+FREQ\b.*?RUN\s*;)",
    re.DOTALL,
)

# PROC TRANSPOSE
_PROC_TRANSPOSE_RE = re.compile(
    r"(?i)(PROC\s+TRANSPOSE\b.*?RUN\s*;)",
    re.DOTALL,
)

# PROC IMPORT (CSV / Excel / delimited)
_PROC_IMPORT_RE = re.compile(
    r"(?i)(PROC\s+IMPORT\b.*?RUN\s*;)",
    re.DOTALL,
)

# PROC APPEND
_PROC_APPEND_RE = re.compile(
    r"(?i)(PROC\s+APPEND\b.*?RUN\s*;)",
    re.DOTALL,
)

# PROC RANK
_PROC_RANK_RE = re.compile(
    r"(?i)(PROC\s+RANK\b.*?RUN\s*;)",
    re.DOTALL,
)

# Macro definitions: %MACRO name(params); … %MEND;
_MACRO_DEF_RE = re.compile(
    r"%MACRO\s+(\w+)\s*(?:\(([^)]*)\))?\s*;(.*?)%MEND\b[^;]*;",
    re.IGNORECASE | re.DOTALL,
)

# FILENAME statements: FILENAME ref 'path';
_FILENAME_RE = re.compile(
    r"FILENAME\s+(\w+)\s+['\"]([^'\"]+)['\"];",
    re.IGNORECASE,
)

# PROC IML block: PROC IML … QUIT;
_PROC_IML_RE = re.compile(
    r"PROC\s+IML\b.*?(?:QUIT|RUN)\s*;",
    re.IGNORECASE | re.DOTALL,
)

# PROC FORMAT block: PROC FORMAT … RUN;
_PROC_FORMAT_RE = re.compile(
    r"PROC\s+FORMAT\b.*?RUN\s*;",
    re.IGNORECASE | re.DOTALL,
)

# DROP / KEEP / WHERE / OUTPUT / ARRAY inside a DATA step
_DROP_RE = re.compile(r"\bDROP\s+([\w\s]+);", re.IGNORECASE)
_KEEP_RE = re.compile(r"\bKEEP\s+([\w\s]+);", re.IGNORECASE)
_WHERE_RE = re.compile(r"\bWHERE\s+(.+?);", re.IGNORECASE | re.DOTALL)
_OUTPUT_RE = re.compile(r"\bOUTPUT\s*(?:(\w+))?\s*;", re.IGNORECASE)
_ARRAY_RE = re.compile(
    r"\bARRAY\s+(\w+)\s*\{(\d+)\}\s*([\w\s]*);",
    re.IGNORECASE,
)

# Unsupported PROC types that are not specifically handled above
_UNSUPPORTED_PROC_RE = re.compile(
    r"(?i)(PROC\s+(?!SQL\b|SORT\b|MEANS\b|SUMMARY\b|FREQ\b|TRANSPOSE\b|IMPORT\b|APPEND\b|RANK\b|IML\b|FORMAT\b)\w+\b.*?(?:RUN|QUIT)\s*;)",
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
    "APPEND": BlockType.PROC_APPEND,
    "RANK": BlockType.PROC_RANK,
    "FORMAT": BlockType.PROC_FORMAT,
}

# Extract DATA output name(s) from "DATA name1 name2;" (datasets may carry
# options like "(drop=x)"; capture up to the terminating ";").
_DATA_OUTPUT_RE = re.compile(r"(?i)\bDATA\s+(.+?)\s*;", re.DOTALL)

# Extract SET input name(s) from "SET name1 name2;" (options stripped later).
_DATA_INPUT_RE = re.compile(r"(?i)\bSET\s+(.+?)\s*;", re.DOTALL)

# Extract MERGE input name(s) from "MERGE name1(in=a) name2(in=b);".
_DATA_MERGE_RE = re.compile(r"(?i)\bMERGE\s+(.+?)\s*;", re.DOTALL)

# RENAME mappings inside a DATA step (RENAME old=new old2=new2;)
_RENAME_RE = re.compile(r"(?i)\bRENAME\s+(.*?)\s*;")
_RENAME_PAIR_RE = re.compile(r"(?i)(\w+)\s*=\s*(\w+)")

# Extract FROM / JOIN table references in PROC SQL
_SQL_FROM_RE = re.compile(r"(?i)\b(?:FROM|JOIN)\s+([\w.]+)")

# Extract CREATE TABLE target in PROC SQL
_SQL_CREATE_RE = re.compile(r"(?i)CREATE\s+TABLE\s+([\w.]+)\s+AS")

# Extract DATA= dataset name (used by SORT, MEANS, FREQ, TRANSPOSE, RANK, …)
_GENERIC_DATA_RE = re.compile(r"(?i)\bDATA\s*=\s*(\w[\w.]*)")

# Extract OUT= dataset name (used by SORT, MEANS, FREQ, TRANSPOSE, IMPORT, RANK, …)
_GENERIC_OUT_RE = re.compile(r"(?i)\bOUT\s*=\s*(\w[\w.]*)")

# PROC MEANS / SUMMARY column-level statements
_MEANS_CLASS_RE = re.compile(r"(?i)\bCLASS\s+([\w\s]+?)\s*;")
_MEANS_VAR_RE = re.compile(r"(?i)\bVAR\s+([\w\s]+?)\s*;")
_MEANS_BY_RE = re.compile(r"(?i)\bBY\s+([\w\s]+?)\s*;")

# PROC FREQ TABLES statement
_FREQ_TABLES_RE = re.compile(r"(?i)\bTABLES\s+(.+?)\s*[/;]")

# PROC TRANSPOSE column-level statements
_TRANS_VAR_RE = re.compile(r"(?i)\bVAR\s+([\w\s]+?)\s*;")
_TRANS_ID_RE = re.compile(r"(?i)\bID\s+([\w\s]+?)\s*;")
_TRANS_BY_RE = re.compile(r"(?i)\bBY\s+([\w\s]+?)\s*;")

# PROC IMPORT statements
_IMPORT_FILE_RE = re.compile(r"""(?i)\bDATAFILE\s*=\s*['"]?([^'";]+)['"]?""")
_IMPORT_DBMS_RE = re.compile(r"(?i)\bDBMS\s*=\s*(\w+)")
_IMPORT_SHEET_RE = re.compile(r"""(?i)\bSHEET\s*=\s*['"]?([^'";]+)['"]?""")

# PROC APPEND statements
_APPEND_BASE_RE = re.compile(r"(?i)\bBASE\s*=\s*(\w[\w.]*)")
_APPEND_DATA_RE = re.compile(r"(?i)\bDATA\s*=\s*(\w[\w.]*)")

# PROC RANK statements
_RANK_VAR_RE = re.compile(r"(?i)\bVAR\s+([\w\s]+?)\s*;")
_RANK_RANKS_RE = re.compile(r"(?i)\bRANKS\s+([\w\s]+?)\s*;")
_RANK_GROUPS_RE = re.compile(r"(?i)\bGROUPS\s*=\s*(\d+)")

# %LET macro variable declaration
_LET_RE = re.compile(r"(?i)%LET\s+(\w+)\s*=\s*([^;]+?)\s*;")

# LIBNAME declarations (libref → path)
_LIBNAME_RE = re.compile(r"""(?i)LIBNAME\s+(\w+)\s+['"]([^'"]+)['"]\s*;""")

# %INCLUDE references
_INCLUDE_RE = re.compile(r"""(?i)%INCLUDE\s+['"]([^'"]+)['"]\s*;""")


# ── Line-number helpers ───────────────────────────────────────────────────────


def _line_of(text: str, char_offset: int) -> int:
    """Return the 1-based line number for a character offset within *text*."""
    return text[:char_offset].count("\n") + 1


def _extract_names(pattern: re.Pattern[str], text: str) -> list[str]:
    """Return a flat list of lowercased dataset names matched by *pattern*.

    Dataset options (e.g. ``(in=indm)``, ``(where=(x>1))``) are stripped so a
    reference like ``sdtm.dm(in=indm)`` yields the clean name ``sdtm.dm``.
    """
    names: list[str] = []
    for match in pattern.finditer(text):
        raw_list = match.group(1)
        # Remove balanced dataset-option parens, innermost-first, to a fixed point.
        prev = ""
        while prev != raw_list:
            prev = raw_list
            raw_list = re.sub(r"\([^()]*\)", "", raw_list)
        names.extend(n.strip().lower() for n in raw_list.split() if n.strip())
    return names


def _extract_renames(raw: str) -> dict[str, str]:
    """Return {old_name: new_name} for RENAME statements inside a DATA step."""
    renames: dict[str, str] = {}
    for match in _RENAME_RE.finditer(raw):
        for pair in _RENAME_PAIR_RE.finditer(match.group(1)):
            renames[pair.group(1).lower()] = pair.group(2).lower()
    return renames


def _extract_libnames(source: str) -> dict[str, str]:
    """Return {libref: path} for all LIBNAME statements in *source*."""
    return {m.group(1).lower(): m.group(2) for m in _LIBNAME_RE.finditer(source)}


def _extract_includes(source: str) -> list[str]:
    """Return list of %INCLUDE'd file paths in *source*."""
    return [m.group(1) for m in _INCLUDE_RE.finditer(source)]


# ── Block extractors ─────────────────────────────────────────────────────────


def _extract_data_steps(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every DATA step found in *source*.

    Captures both SET and MERGE inputs, plus RENAME mappings as a hint
    attribute on the block.
    """
    for match in _DATA_STEP_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        outputs = _extract_names(_DATA_OUTPUT_RE, raw)
        inputs = _extract_names(_DATA_INPUT_RE, raw) + _extract_names(_DATA_MERGE_RE, raw)
        block = SASBlock(
            block_type=BlockType.DATA_STEP,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )
        block.renames = _extract_renames(raw)
        # DROP / KEEP
        drop_m = _DROP_RE.search(raw)
        block.drop_cols = drop_m.group(1).split() if drop_m else []
        keep_m = _KEEP_RE.search(raw)
        block.keep_cols = keep_m.group(1).split() if keep_m else []
        # WHERE
        where_m = _WHERE_RE.search(raw)
        block.where_clause = where_m.group(1).strip() if where_m else None
        # OUTPUT targets
        block.output_targets = [m.group(1) or "" for m in _OUTPUT_RE.finditer(raw)]
        # ARRAYs
        block.arrays = [
            {"name": m.group(1), "size": int(m.group(2)), "columns": m.group(3).split()}
            for m in _ARRAY_RE.finditer(raw)
        ]
        yield block


def _extract_proc_sql(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every PROC SQL block found in *source*."""
    for match in _PROC_SQL_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        inputs = _extract_names(_SQL_FROM_RE, raw)
        outputs = _extract_names(_SQL_CREATE_RE, raw)
        block = SASBlock(
            block_type=BlockType.PROC_SQL,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )
        where_m = _WHERE_RE.search(raw)
        block.where_clause = where_m.group(1).strip() if where_m else None
        yield block


def _extract_proc_sort(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every PROC SORT block found in *source*."""
    for match in _PROC_SORT_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        data_match = _GENERIC_DATA_RE.search(raw)
        out_match = _GENERIC_OUT_RE.search(raw)
        inputs = [data_match.group(1).lower()] if data_match else []
        outputs = [out_match.group(1).lower()] if out_match else inputs[:]
        block = SASBlock(
            block_type=BlockType.PROC_SORT,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )
        where_m = _WHERE_RE.search(raw)
        block.where_clause = where_m.group(1).strip() if where_m else None
        yield block


def _extract_proc_means(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every PROC MEANS / SUMMARY block.

    Attaches CLASS, VAR, and BY column lists as block attributes so the
    LLM prompt builder knows exactly which columns must exist on the
    input DataFrame.
    """
    for match in _PROC_MEANS_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        data_match = _GENERIC_DATA_RE.search(raw)
        out_match = _GENERIC_OUT_RE.search(raw)
        inputs = [data_match.group(1).lower()] if data_match else []
        outputs = [out_match.group(1).lower()] if out_match else []
        block = SASBlock(
            block_type=BlockType.PROC_MEANS,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )
        block.class_vars = _extract_names(_MEANS_CLASS_RE, raw)
        block.var_cols = _extract_names(_MEANS_VAR_RE, raw)
        block.by_vars = _extract_names(_MEANS_BY_RE, raw)
        where_m = _WHERE_RE.search(raw)
        block.where_clause = where_m.group(1).strip() if where_m else None
        yield block


def _extract_proc_freq(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every PROC FREQ block.

    Attaches table_vars (the columns referenced in TABLES) as a hint.
    """
    for match in _PROC_FREQ_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        data_match = _GENERIC_DATA_RE.search(raw)
        out_match = _GENERIC_OUT_RE.search(raw)
        inputs = [data_match.group(1).lower()] if data_match else []
        outputs = [out_match.group(1).lower()] if out_match else []
        block = SASBlock(
            block_type=BlockType.PROC_FREQ,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )
        tables_match = _FREQ_TABLES_RE.search(raw)
        if tables_match:
            block.table_vars = [
                v.strip().lower() for v in re.split(r"[\s*]+", tables_match.group(1)) if v.strip()
            ]
        else:
            block.table_vars = []
        where_m = _WHERE_RE.search(raw)
        block.where_clause = where_m.group(1).strip() if where_m else None
        yield block


def _extract_proc_transpose(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every PROC TRANSPOSE block.

    Attaches VAR / ID / BY column lists as hints.
    """
    for match in _PROC_TRANSPOSE_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        data_match = _GENERIC_DATA_RE.search(raw)
        out_match = _GENERIC_OUT_RE.search(raw)
        inputs = [data_match.group(1).lower()] if data_match else []
        outputs = [out_match.group(1).lower()] if out_match else []
        block = SASBlock(
            block_type=BlockType.PROC_TRANSPOSE,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )
        block.var_cols = _extract_names(_TRANS_VAR_RE, raw)
        block.id_cols = _extract_names(_TRANS_ID_RE, raw)
        block.by_vars = _extract_names(_TRANS_BY_RE, raw)
        where_m = _WHERE_RE.search(raw)
        block.where_clause = where_m.group(1).strip() if where_m else None
        yield block


def _extract_proc_import(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every PROC IMPORT block.

    Attaches file path, DBMS (CSV/XLSX/DLM/…), and Excel sheet name as
    hints so the LLM can pick the correct reader API.
    """
    for match in _PROC_IMPORT_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        out_match = _GENERIC_OUT_RE.search(raw)
        file_match = _IMPORT_FILE_RE.search(raw)
        dbms_match = _IMPORT_DBMS_RE.search(raw)
        sheet_match = _IMPORT_SHEET_RE.search(raw)
        outputs = [out_match.group(1).lower()] if out_match else []
        block = SASBlock(
            block_type=BlockType.PROC_IMPORT,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=[],
            output_datasets=outputs,
        )
        block.file_path = file_match.group(1) if file_match else None
        block.dbms = dbms_match.group(1).upper() if dbms_match else None
        block.sheet = sheet_match.group(1) if sheet_match else None
        yield block


def _extract_proc_append(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every PROC APPEND block.

    BASE= is both an input (read from) and an output (appended to).
    DATA= is an additional input.
    """
    for match in _PROC_APPEND_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        base_match = _APPEND_BASE_RE.search(raw)
        data_match = _APPEND_DATA_RE.search(raw)
        inputs: list[str] = []
        outputs: list[str] = []
        if base_match:
            inputs.append(base_match.group(1).lower())
            outputs.append(base_match.group(1).lower())
        if data_match:
            inputs.append(data_match.group(1).lower())
        yield SASBlock(
            block_type=BlockType.PROC_APPEND,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )


def _extract_proc_rank(source: str, filename: str) -> Iterator[SASBlock]:
    """Yield SASBlock for every PROC RANK block.

    Attaches VAR, RANKS, and GROUPS hints so the LLM can pick the right
    PySpark Window / rank function.
    """
    for match in _PROC_RANK_RE.finditer(source):
        raw = match.group(1)
        start = _line_of(source, match.start())
        end = _line_of(source, match.end() - 1)
        data_match = _GENERIC_DATA_RE.search(raw)
        out_match = _GENERIC_OUT_RE.search(raw)
        groups_match = _RANK_GROUPS_RE.search(raw)
        inputs = [data_match.group(1).lower()] if data_match else []
        outputs = [out_match.group(1).lower()] if out_match else inputs[:]
        block = SASBlock(
            block_type=BlockType.PROC_RANK,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )
        block.var_cols = _extract_names(_RANK_VAR_RE, raw)
        block.rank_cols = _extract_names(_RANK_RANKS_RE, raw)
        block.groups = int(groups_match.group(1)) if groups_match else None
        where_m = _WHERE_RE.search(raw)
        block.where_clause = where_m.group(1).strip() if where_m else None
        yield block


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
    """Yield typed PROC blocks for PROC types not handled by dedicated extractors.

    Each matched PROC is assigned the most specific BlockType available from
    ``_KNOWN_PROCS``. Unfamiliar PROCs receive ``BlockType.PROC_UNKNOWN``.
    ``BlockType.UNTRANSLATABLE`` is reserved for genuinely unparsable SAS only.

    Skips any match whose span overlaps an already-covered span.
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
        data_match = _GENERIC_DATA_RE.search(raw)
        out_match = _GENERIC_OUT_RE.search(raw)
        inputs = [data_match.group(1).lower()] if data_match else []
        outputs = [out_match.group(1).lower()] if out_match else []
        block = SASBlock(
            block_type=block_type,
            source_file=filename,
            start_line=start,
            end_line=end,
            raw_sas=raw,
            input_datasets=inputs,
            output_datasets=outputs,
        )
        where_m = _WHERE_RE.search(raw)
        block.where_clause = where_m.group(1).strip() if where_m else None
        yield block


# ── Dependency ordering ───────────────────────────────────────────────────────


def _topological_sort(blocks: list[SASBlock]) -> list[SASBlock]:
    """Return *blocks* in dependency order using a DAG on dataset names.

    Blocks without inter-dependencies retain their original relative order.
    Cycles are broken by falling back to the original order (best-effort).
    """
    producer: dict[str, int] = {}
    for idx, block in enumerate(blocks):
        for ds in block.output_datasets:
            producer[ds] = idx

    graph: nx.DiGraph = nx.DiGraph()
    graph.add_nodes_from(range(len(blocks)))

    for idx, block in enumerate(blocks):
        for ds in block.input_datasets:
            if ds in producer and producer[ds] != idx:
                graph.add_edge(producer[ds], idx)

    try:
        in_degree = {n: graph.in_degree(n) for n in graph.nodes()}
        heap: list[tuple[str, int, int]] = []
        for n, deg in in_degree.items():
            if deg == 0:
                heapq.heappush(heap, (blocks[n].source_file, blocks[n].start_line, n))
        order: list[int] = []
        while heap:
            _, _, node = heapq.heappop(heap)
            order.append(node)
            for successor in graph.successors(node):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    heapq.heappush(
                        heap,
                        (blocks[successor].source_file, blocks[successor].start_line, successor),
                    )
        if len(order) != len(blocks):
            raise nx.NetworkXUnfeasible("cycle detected")
    except nx.NetworkXUnfeasible:
        order = list(range(len(blocks)))

    return [blocks[i] for i in order]


# ── Lineage extraction ────────────────────────────────────────────────────────


def extract_lineage(blocks: list[SASBlock], job_id: str) -> dict:  # type: ignore[type-arg]
    """Build a JSON-serializable lineage graph from parsed SAS blocks.

    Creates one LineageNode per block and one LineageEdge per dataset flowing
    from a producer block to a consumer block. The returned dict matches the
    ``JobLineageResponse`` schema used by the API.

    Args:
        blocks: Dependency-ordered list of SAS blocks from SASParser.parse().
        job_id: String UUID of the owning job (embedded in the response).

    Returns:
        Plain dict with keys ``job_id``, ``nodes``, and ``edges``, all
        JSON-serializable.
    """
    nodes: list[dict[str, str]] = []
    producer_map: dict[str, str] = {}

    for block in blocks:
        node_id = f"{block.source_file}::{block.start_line}"
        label = getattr(block, "name", None) or block.block_type.value
        status = "unrecognized" if block.block_type == BlockType.UNTRANSLATABLE else "migrated"

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

    def _extract_macro_defs(self, source: str, filename: str) -> list[MacroDef]:
        """Return a MacroDef for every %MACRO … %MEND definition in *source*.

        Args:
            source: Raw SAS source text.
            filename: Source file name (stored on each MacroDef).

        Returns:
            List of MacroDef instances in source order.
        """
        defs: list[MacroDef] = []
        for m in _MACRO_DEF_RE.finditer(source):
            name = m.group(1).upper()
            params_raw = m.group(2) or ""
            params = [p.strip() for p in params_raw.split(",") if p.strip()]
            body = m.group(3).strip()
            line = source[: m.start()].count("\n") + 1
            defs.append(
                MacroDef(name=name, params=params, body=body, source_file=filename, line=line)
            )
        return defs

    def _extract_filenames(self, source: str) -> dict[str, str]:
        """Return {fileref: path} for all FILENAME statements in *source*.

        Args:
            source: Raw SAS source text.

        Returns:
            Mapping of lowercased fileref to path string.
        """
        return {m.group(1).lower(): m.group(2) for m in _FILENAME_RE.finditer(source)}

    def _extract_proc_iml(self, source: str, filename: str) -> list[SASBlock]:
        """Return a SASBlock for every PROC IML … QUIT; block in *source*.

        Uses PROC_SQL as the block_type (generic proc container) so that the
        translator treats IML blocks as opaque pass-through code.

        Args:
            source: Raw SAS source text.
            filename: Source file name.

        Returns:
            List of SASBlock instances.
        """
        blocks: list[SASBlock] = []
        for m in _PROC_IML_RE.finditer(source):
            start_line = source[: m.start()].count("\n") + 1
            end_line = source[: m.end()].count("\n") + 1
            blocks.append(
                SASBlock(
                    block_type=BlockType.PROC_IML,
                    raw_sas=m.group(0),
                    source_file=filename,
                    start_line=start_line,
                    end_line=end_line,
                    input_datasets=[],
                    output_datasets=[],
                )
            )
        return blocks

    def _extract_proc_format(self, source: str, filename: str) -> list[SASBlock]:
        """Return a SASBlock for every PROC FORMAT … RUN; block in *source*.

        Args:
            source: Raw SAS source text.
            filename: Source file name.

        Returns:
            List of SASBlock instances with block_type PROC_FORMAT.
        """
        blocks: list[SASBlock] = []
        for m in _PROC_FORMAT_RE.finditer(source):
            start_line = source[: m.start()].count("\n") + 1
            end_line = source[: m.end()].count("\n") + 1
            blocks.append(
                SASBlock(
                    block_type=BlockType.PROC_FORMAT,
                    raw_sas=m.group(0),
                    source_file=filename,
                    start_line=start_line,
                    end_line=end_line,
                    input_datasets=[],
                    output_datasets=[],
                )
            )
        return blocks

    def parse(self, files: dict[str, str]) -> ParseResult:
        """Parse SAS source files and return dependency-ordered blocks with macro vars.

        Args:
            files: Mapping of filename to SAS source text.

        Returns:
            ParseResult containing SASBlock list in dependency order, all
            MacroVar declarations, and (as attached attributes) LIBNAME,
            %INCLUDE, macro definitions, and FILENAME map found across all files.
        """
        all_blocks: list[SASBlock] = []
        all_macro_vars: list[MacroVar] = []
        all_libnames: dict[str, str] = {}
        all_includes: list[str] = []
        all_macro_defs: list[MacroDef] = []
        all_filename_map: dict[str, str] = {}

        for filename, source in files.items():
            # Strip block comments before regex matching so that PROC keywords
            # inside /* ... */ comments don't produce phantom blocks.
            # The original source is kept for raw_sas capture inside each extractor.
            source_stripped = _strip_block_comments(source)
            covered: list[tuple[int, int]] = []

            for pattern in (
                _DATA_STEP_RE,
                _PROC_SQL_RE,
                _PROC_SORT_RE,
                _PROC_MEANS_RE,
                _PROC_FREQ_RE,
                _PROC_TRANSPOSE_RE,
                _PROC_IMPORT_RE,
                _PROC_APPEND_RE,
                _PROC_RANK_RE,
                _PROC_IML_RE,
                _PROC_FORMAT_RE,
            ):
                for match in pattern.finditer(source_stripped):
                    covered.append((match.start(), match.end()))

            all_blocks.extend(_extract_data_steps(source_stripped, filename))
            all_blocks.extend(_extract_proc_sql(source_stripped, filename))
            all_blocks.extend(_extract_proc_sort(source_stripped, filename))
            all_blocks.extend(_extract_proc_means(source_stripped, filename))
            all_blocks.extend(_extract_proc_freq(source_stripped, filename))
            all_blocks.extend(_extract_proc_transpose(source_stripped, filename))
            all_blocks.extend(_extract_proc_import(source_stripped, filename))
            all_blocks.extend(_extract_proc_append(source_stripped, filename))
            all_blocks.extend(_extract_proc_rank(source_stripped, filename))
            all_blocks.extend(self._extract_proc_iml(source_stripped, filename))
            all_blocks.extend(self._extract_proc_format(source_stripped, filename))
            all_blocks.extend(_extract_unsupported_procs(source_stripped, filename, covered))
            all_macro_vars.extend(_extract_macro_vars(source, filename))
            all_libnames.update(_extract_libnames(source))
            all_includes.extend(_extract_includes(source))
            all_macro_defs.extend(self._extract_macro_defs(source, filename))
            all_filename_map.update(self._extract_filenames(source))

        result = ParseResult(
            blocks=_topological_sort(all_blocks),
            macro_vars=all_macro_vars,
            libname_map=all_libnames,
            includes=all_includes,
            macro_defs=all_macro_defs,
            filename_map=all_filename_map,
        )
        return result
