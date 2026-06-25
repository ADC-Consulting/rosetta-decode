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
from src.worker.engine.format_catalog import extract_format_catalog
from src.worker.engine.macro_call_expander import expand_macro_calls
from src.worker.engine.models import (
    BlockType,
    FormatDef,
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


def _strip_macro_defs(source: str) -> str:
    """Replace %MACRO … %MEND definition spans with blank lines.

    Macro *definition* bodies must never be extracted as translatable blocks: a
    ``proc sql`` inside an unexpanded ``%macro`` body would otherwise match the
    PROC extractors and emit code referencing unresolved ``&in``/``&out`` params.
    Each definition span is replaced with the same number of newline characters
    it spanned so that downstream ``start_line``/``end_line`` calculations (which
    count newlines in ``source[:m.start()]``) remain accurate.

    Args:
        source: SAS source text (typically already macro-call-expanded).

    Returns:
        Source with every macro-definition body replaced by blank lines.
    """

    def _replace(m: re.Match[str]) -> str:
        return "\n" * m.group(0).count("\n")

    return _MACRO_DEF_RE.sub(_replace, source)


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

# ── Column-schema extraction regexes (LENGTH / FORMAT / ATTRIB) ───────────────

# LENGTH statement: LENGTH col1 $40 col2 8 ...;
# Captures the entire argument list between LENGTH and the terminating semicolon.
_LENGTH_STMT_RE = re.compile(r"\bLENGTH\s+(.*?)\s*;", re.IGNORECASE | re.DOTALL)

# FORMAT statement: FORMAT col1 date9. col2 comma12.2 ...;
_FORMAT_STMT_RE = re.compile(r"\bFORMAT\s+(.*?)\s*;", re.IGNORECASE | re.DOTALL)

# ATTRIB statement: ATTRIB col LENGTH=$40 FORMAT=$CHAR40. LABEL="Patient ID";
# Captures the entire body between ATTRIB and the terminating semicolon.
_ATTRIB_STMT_RE = re.compile(r"\bATTRIB\s+(.*?)\s*;", re.IGNORECASE | re.DOTALL)

# Individual token regexes used to parse the argument bodies above.
# LENGTH token: optional $ prefix followed by optional digits — e.g. $40, $, 8
_LENGTH_TOKEN_RE = re.compile(r"(\$\d*|\d+)$")
# FORMAT value: word chars + optional digits + optional period + optional chars/digits
_FORMAT_VALUE_RE = re.compile(r"^[\w$][\w.]*\.$|^[\w$][\w.]*\.\d+$|^\$\w*\.$|^\$\w*\.\d+$")
# ATTRIB attribute captures: LENGTH=, FORMAT=, LABEL=
_ATTRIB_LENGTH_RE = re.compile(r"\bLENGTH\s*=\s*(\$?\d*|\d+)", re.IGNORECASE)
_ATTRIB_FORMAT_RE = re.compile(r"\bFORMAT\s*=\s*([\w$][\w.]*\.[\w\d]*)", re.IGNORECASE)
_ATTRIB_LABEL_RE = re.compile(r'\bLABEL\s*=\s*"([^"]*)"', re.IGNORECASE)

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

# MERGE BY extraction (DATA step): "BY col1 col2;" following a MERGE statement.
# Captures the column list between the BY keyword and the terminating semicolon.
# SAS: parser.py:_MERGE_BY_RE
_MERGE_BY_RE = re.compile(r"(?i)\bBY\s+([\w\s]+?)\s*;")

# PROC SQL alias map: "FROM table_name alias" or "JOIN table_name alias"
# Captures: table name (group 1) and optional alias (group 2).
# Handles quoted/unquoted names, skips ON/SET/WHERE keywords as aliases.
# SAS: parser.py:_SQL_ALIAS_RE
_SQL_ALIAS_RE = re.compile(
    r"(?i)\b(?:FROM|JOIN)\s+([\w.]+)\s+(?:AS\s+)?(\w+)(?=\s)",
)

# PROC SQL ON clause: "ON alias1.col = alias2.col"
# Captures: left alias (group 1), left col (group 2), right alias (group 3), right col (group 4).
# SAS: parser.py:_SQL_ON_RE
_SQL_ON_RE = re.compile(
    r"(?i)\bON\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)",
)

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

# LENGTH statement body and character-variable token (var $[w])
_LENGTH_STMT_RE = re.compile(r"(?i)\bLENGTH\b(.+?);", re.DOTALL)
_CHAR_VAR_RE = re.compile(r"(?i)\b([A-Za-z_]\w*)\s*\$\s*\d*")


def extract_declared_char_columns(sas_source: str) -> set[str]:
    """Return lowercased names of CHARACTER variables declared via LENGTH var $w statements.

    Scans every ``LENGTH ... ;`` statement in *sas_source* for tokens of the form
    ``name $[w]`` (the ``$`` marks a character variable in SAS; numeric vars have no
    ``$``). Applied job-wide: the union across all source files identifies columns that
    must be read as strings from CSV/TSV to preserve leading zeros.

    This is a conservative text scan — no PROC IMPORT→DATA-step dependency tracing.
    A column declared char anywhere is forced to string in any CSV containing that
    column name. False positives are benign for pharma identifier data.

    Args:
        sas_source: Raw SAS source text.

    Returns:
        Set of lowercased column names declared as character.
    """
    char_cols: set[str] = set()
    for stmt_match in _LENGTH_STMT_RE.finditer(sas_source):
        body = stmt_match.group(1)
        for var_match in _CHAR_VAR_RE.finditer(body):
            char_cols.add(var_match.group(1).lower())
    return char_cols


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


# ── Column-schema helpers ─────────────────────────────────────────────────────


def _parse_length_stmt(body: str) -> dict[str, dict[str, str]]:
    """Parse the argument list of a SAS LENGTH statement.

    Handles multi-column declarations such as ``col $40 age 8``.

    Args:
        body: Text between ``LENGTH`` keyword and the terminating semicolon,
              with leading/trailing whitespace stripped.

    Returns:
        Mapping of lowercased column name to a dict with ``sas_type`` and
        ``sas_format`` keys. Only keys that are derivable are included.
    """  # SAS: parser.py:_parse_length_stmt
    result: dict[str, dict[str, str]] = {}
    tokens = body.split()
    pending_cols: list[str] = []
    for token in tokens:
        # A token is a length specifier if it starts with $ or is a bare integer
        is_char_spec = token.startswith("$")
        is_num_spec = token.isdigit()
        if is_char_spec or is_num_spec:
            sas_type = "character" if is_char_spec else "numeric"
            entry: dict[str, str] = {"sas_type": sas_type, "sas_format": token}
            for col in pending_cols:
                result[col.lower()] = entry.copy()
            pending_cols = []
        else:
            pending_cols.append(token)
    return result


def _parse_format_stmt(body: str) -> dict[str, dict[str, str]]:
    """Parse the argument list of a SAS FORMAT statement.

    Handles multi-pair declarations such as ``col date9. amount comma12.2``.
    Format values are stored as uppercase strings.

    Args:
        body: Text between ``FORMAT`` keyword and the terminating semicolon.

    Returns:
        Mapping of lowercased column name to a dict with a ``sas_format`` key.
    """  # SAS: parser.py:_parse_format_stmt
    result: dict[str, dict[str, str]] = {}
    tokens = body.split()
    pending_cols: list[str] = []
    for token in tokens:
        # A format value ends with a period (possibly followed by digits).
        if "." in token and not token.startswith("."):
            fmt = token.upper()
            for col in pending_cols:
                result[col.lower()] = {"sas_format": fmt}
            pending_cols = []
        else:
            pending_cols.append(token)
    return result


def _parse_attrib_stmt(body: str) -> dict[str, dict[str, str]]:
    """Parse a SAS ATTRIB statement body.

    Each ATTRIB statement declares attributes for a single variable with any
    combination of LENGTH=, FORMAT=, and LABEL= sub-options.

    Args:
        body: Text between the ``ATTRIB`` keyword and the terminating semicolon.

    Returns:
        Mapping of lowercased column name to a dict with any subset of
        ``sas_type``, ``sas_format``, and ``label`` keys.
    """  # SAS: parser.py:_parse_attrib_stmt
    result: dict[str, dict[str, str]] = {}
    # Split on whitespace to get the leading column name
    tokens = body.split()
    if not tokens:
        return result
    col = tokens[0].lower()
    entry: dict[str, str] = {}

    len_m = _ATTRIB_LENGTH_RE.search(body)
    if len_m:
        raw_len = len_m.group(1)
        if raw_len.startswith("$"):
            entry["sas_type"] = "character"
            entry["sas_format"] = raw_len
        elif raw_len.isdigit():
            entry["sas_type"] = "numeric"
            entry["sas_format"] = raw_len

    fmt_m = _ATTRIB_FORMAT_RE.search(body)
    if fmt_m:
        entry["sas_format"] = fmt_m.group(1).upper()

    lbl_m = _ATTRIB_LABEL_RE.search(body)
    if lbl_m:
        entry["label"] = lbl_m.group(1)

    if entry:
        result[col] = entry
    return result


def _extract_column_schema(raw_sas: str) -> dict[str, dict[str, str]]:
    """Extract column declarations from LENGTH, FORMAT, and ATTRIB statements.

    Merges all three statement types, with later statements winning on
    key-level conflicts (not column-level — entries from all statements
    are merged per column).

    Args:
        raw_sas: Raw SAS source text for a single DATA step block.

    Returns:
        Mapping of lowercased column name to a dict with any subset of
        ``sas_type``, ``sas_format``, and ``label`` keys.
    """  # SAS: parser.py:_extract_column_schema
    schema: dict[str, dict[str, str]] = {}

    for m in _LENGTH_STMT_RE.finditer(raw_sas):
        for col, entry in _parse_length_stmt(m.group(1)).items():
            existing = schema.setdefault(col, {})
            existing.update(entry)

    for m in _FORMAT_STMT_RE.finditer(raw_sas):
        for col, entry in _parse_format_stmt(m.group(1)).items():
            existing = schema.setdefault(col, {})
            existing.update(entry)

    for m in _ATTRIB_STMT_RE.finditer(raw_sas):
        for col, entry in _parse_attrib_stmt(m.group(1)).items():
            existing = schema.setdefault(col, {})
            existing.update(entry)

    return schema


# ── Relationship extractors ───────────────────────────────────────────────────


def _extract_merge_by_vars(raw_sas: str) -> list[str]:
    """Extract BY-clause column names from a DATA step MERGE statement.

    Returns column names only when the DATA step body contains a ``MERGE``
    statement. An empty list is returned when no MERGE is present, because
    a bare ``BY`` without MERGE belongs to PROC SORT-style blocks.

    Args:
        raw_sas: Raw SAS source text for a single DATA step block.

    Returns:
        Lowercased column name list from the BY clause, or an empty list.
    """  # SAS: parser.py:_extract_merge_by_vars
    if not re.search(r"(?i)\bMERGE\b", raw_sas):
        return []
    by_vars: list[str] = []
    for match in _MERGE_BY_RE.finditer(raw_sas):
        by_vars.extend(col.strip().lower() for col in match.group(1).split() if col.strip())
    return by_vars


def _build_alias_map(raw_sql: str) -> dict[str, str]:
    """Build a {alias: table_name} mapping from FROM/JOIN clauses in PROC SQL.

    Handles both ``FROM tbl alias`` and ``FROM tbl AS alias`` forms.
    Table names are lowercased; schema-qualified names (``lib.table``) use
    only the member name as the key value for readability.

    Args:
        raw_sql: Raw SAS PROC SQL source text.

    Returns:
        Mapping of alias (lowercase) to table name (lowercase, member-only).
    """  # SAS: parser.py:_build_alias_map
    alias_map: dict[str, str] = {}
    for m in _SQL_ALIAS_RE.finditer(raw_sql):
        table_raw = m.group(1).lower()
        alias = m.group(2).lower()
        # Skip SQL reserved words that can appear after a table name
        reserved = {
            "where",
            "on",
            "set",
            "group",
            "having",
            "order",
            "inner",
            "outer",
            "left",
            "right",
            "full",
            "cross",
            "join",
            "select",
            "from",
            "as",
        }
        if alias in reserved:
            continue
        # Use member name only (strip libref prefix e.g. "work.dm" → "dm")
        table_name = table_raw.split(".")[-1]
        alias_map[alias] = table_name
    return alias_map


def _extract_join_on_keys(raw_sql: str) -> list[dict[str, str]]:
    """Extract JOIN ON predicates from a PROC SQL block, resolving aliases to table names.

    Each ``ON left_alias.col = right_alias.col`` predicate is resolved using
    the alias map built from FROM/JOIN clauses. Predicates whose aliases cannot
    be resolved are skipped.

    Args:
        raw_sql: Raw SAS PROC SQL source text.

    Returns:
        List of dicts with keys ``left_table``, ``right_table``, ``left_col``,
        ``right_col`` (all lowercase). Empty list when no JOIN ON is present.
    """  # SAS: parser.py:_extract_join_on_keys
    alias_map = _build_alias_map(raw_sql)
    result: list[dict[str, str]] = []
    for m in _SQL_ON_RE.finditer(raw_sql):
        left_alias = m.group(1).lower()
        left_col = m.group(2).lower()
        right_alias = m.group(3).lower()
        right_col = m.group(4).lower()
        left_table = alias_map.get(left_alias)
        right_table = alias_map.get(right_alias)
        if left_table is None or right_table is None:
            continue
        result.append(
            {
                "left_table": left_table,
                "right_table": right_table,
                "left_col": left_col,
                "right_col": right_col,
            }
        )
    return result


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
        # Column schema from LENGTH / FORMAT / ATTRIB declarations
        # SAS: parser.py:_extract_data_steps
        block.column_schema = _extract_column_schema(raw)
        # MERGE BY — relationship keys for ERD (F34)
        # SAS: parser.py:_extract_data_steps:merge_by_vars
        block.merge_by_vars = _extract_merge_by_vars(raw)
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
        # JOIN ON keys — relationship predicates for ERD (F34)
        # SAS: parser.py:_extract_proc_sql:join_on_keys
        block.join_on_keys = _extract_join_on_keys(raw)
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
                MacroDef(
                    name=name,
                    params=params,
                    param_str=params_raw,
                    body=body,
                    source_file=filename,
                    line=line,
                )
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
        all_format_defs: dict[str, FormatDef] = {}

        # Pass 1: collect all macro defs across all files (needed for cross-file
        # call resolution).  Last definition of a given name wins for duplicates.
        all_macro_defs_map: dict[str, MacroDef] = {}
        for filename, source in files.items():
            for md in self._extract_macro_defs(source, filename):
                all_macro_defs_map[md.name.upper()] = md

        # Pass 2: expand macro calls, then extract blocks from the expanded source.
        for filename, source in files.items():
            expanded_source = expand_macro_calls(source, all_macro_defs_map)

            # Strip %MACRO … %MEND definition bodies before block extraction so a
            # ``proc sql`` inside an (unexpanded) macro definition is never picked
            # up as a translatable block with unresolved &in/&out params. Newlines
            # are preserved so line numbers stay accurate. Macro-def *metadata* is
            # still captured below from ``expanded_source`` (which keeps the defs).
            defs_stripped = _strip_macro_defs(expanded_source)

            # Strip block comments before regex matching so that PROC keywords
            # inside /* ... */ comments don't produce phantom blocks.
            # The original source is kept for raw_sas capture inside each extractor.
            source_stripped = _strip_block_comments(defs_stripped)
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
            all_macro_vars.extend(_extract_macro_vars(expanded_source, filename))
            all_libnames.update(_extract_libnames(expanded_source))
            all_includes.extend(_extract_includes(expanded_source))
            all_macro_defs.extend(self._extract_macro_defs(expanded_source, filename))
            all_filename_map.update(self._extract_filenames(expanded_source))
            all_format_defs.update(extract_format_catalog(expanded_source))

        result = ParseResult(
            blocks=_topological_sort(all_blocks),
            macro_vars=all_macro_vars,
            libname_map=all_libnames,
            includes=all_includes,
            macro_defs=all_macro_defs,
            filename_map=all_filename_map,
            format_catalog=all_format_defs,
        )
        return result
