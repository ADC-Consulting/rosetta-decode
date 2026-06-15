"""Utilities for mapping SAS data types and formats to semantic target types."""

# SAS: src/backend/api/schema_utils.py:1

import re
from typing import Any

# Date/Datetime format patterns
_DATE_FORMATS = re.compile(
    r"^(DATE|DDMMYY|MMDDYY|YYMMDD|JULIAN|WEEKDATE|WORDDATE|DTDATE|YEAR|QTR|MONNAME|DAYNAME|"
    r"EURDFDD|EURDFDE|EURDFDN|EURDFDT|EURDFWK|NLDATE|ISO8601DA)",
    re.IGNORECASE,
)
_DATETIME_FORMATS = re.compile(
    r"^(DATETIME|DTTIME|TOD|HHMM|HOUR|MMSS|TIME|TIMEAMPM|E8601DT|NLTIMAP|NLTIME)",
    re.IGNORECASE,
)
_DECIMAL_FORMATS = re.compile(
    r"^(COMMA|DOLLAR|EURO|POUND|FRANC|DM|YEN|F|E|BEST|NUMX)",
    re.IGNORECASE,
)


def map_sas_to_semantic_type(sas_type: str, sas_format: str | None) -> str:
    """Map a SAS storage type and display format to a semantic target type.

    Args:
        sas_type: "character"/"string" (SAS7BDAT/XPORT) or "double" (from readstat_variable_types)
        sas_format: SAS format name e.g. "DATE9.", "$40.", "DATETIME20." (may be empty/None)

    Returns:
        One of: "String", "Date", "Timestamp", "Decimal", "Number", "Integer", "Unknown"
    """
    if not sas_type:
        return "Unknown"
    fmt = (sas_format or "").strip().lstrip("$").rstrip(".")
    if sas_type in {"character", "string"}:
        return "String"
    # numeric — check format for semantic hint
    # Datetime must be tested before date: DATETIME... starts with DATE...
    if _DATETIME_FORMATS.match(fmt):
        return "Timestamp"
    if _DATE_FORMATS.match(fmt):
        return "Date"
    if _DECIMAL_FORMATS.match(fmt) and "." in (sas_format or ""):
        return "Decimal"
    return "Number"


# SAS: schema_utils.py:infer_pk_fk


def infer_pk_fk(
    tables: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    user_pk_overrides: dict[str, list[str]] | None = None,
    user_fk_overrides: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Infer primary and foreign keys for each table from column patterns and relationships.

    Applies SDTM-aware heuristics in priority order:
    1. USUBJID → PK in dm table, FK elsewhere
    2. STUDYID + USUBJID compound PK
    3. *ID object column → PK in smallest table, FK in others
    4. *SEQ + USUBJID → compound PK in observation tables
    5. Relationship hints → FK from relationship entries
    6. Fallback: no PK

    User overrides take precedence over inferred values.

    Args:
        tables: Each entry has dataset_name, columns, column_types, target_columns.
        relationships: Each entry has left_table, right_table, key_column, relationship_type.
        user_pk_overrides: {dataset_name: [col, ...]} — replace inferred PKs.
        user_fk_overrides: {"table.col": "other_table.col"} — replace/add inferred FKs.

    Returns:
        {dataset_name: {"pks": list[str], "fks": dict[str, str]}}
    """
    result: dict[str, dict[str, Any]] = {t["dataset_name"]: {"pks": [], "fks": {}} for t in tables}

    # Build column → set of dataset_names lookup for ID column rules
    col_to_tables: dict[str, list[str]] = {}
    for t in tables:
        for col in t.get("columns", []):
            col_to_tables.setdefault(col.lower(), []).append(t["dataset_name"])

    # Identify the "smallest" table per unique-col-name (fewest columns heuristic)
    col_fewest_table: dict[str, str] = {}
    for col_lower, owners in col_to_tables.items():
        if len(owners) > 1:
            # Proxy for uniqueness: fewest columns → most likely the owner/PK table
            def _col_count(dn: str) -> int:
                return len(next((t["columns"] for t in tables if t["dataset_name"] == dn), []))

            col_fewest_table[col_lower] = min(owners, key=_col_count)

    for t in tables:
        name = t["dataset_name"]
        cols_lower = [c.lower() for c in t.get("columns", [])]
        col_types: dict[str, str] = {k.lower(): v for k, v in t.get("column_types", {}).items()}
        pks: list[str] = []
        fks: dict[str, str] = {}

        has_usubjid = "usubjid" in cols_lower
        has_studyid = "studyid" in cols_lower

        # Rule 2: STUDYID + USUBJID compound PK
        if has_usubjid and has_studyid:
            pks = ["STUDYID", "USUBJID"]
        elif has_usubjid:
            # Rule 1: USUBJID → PK in dm table, FK elsewhere
            is_dm = name.lower() == "dm" or name.lower().startswith("dm")
            if is_dm:
                pks = ["USUBJID"]
            else:
                fks["USUBJID"] = "dm.USUBJID"

        # Rule 4: *SEQ + USUBJID → compound PK (observation datasets)
        seq_cols = [c for c in t.get("columns", []) if c.upper().endswith("SEQ")]
        if has_usubjid and seq_cols and not pks:
            pks = ["USUBJID", seq_cols[0]]
        elif has_usubjid and seq_cols and pks == ["USUBJID"]:
            # Extend existing USUBJID PK with SEQ
            pks = ["USUBJID", seq_cols[0]]

        # Rule 3: *ID object column → PK in fewest-column table, FK elsewhere
        id_cols = [
            c
            for c in t.get("columns", [])
            if c.upper().endswith("ID") and col_types.get(c.lower(), "") == "object"
        ]
        for id_col in id_cols:
            if id_col.lower() in col_fewest_table:
                owner = col_fewest_table[id_col.lower()]
                if owner == name and id_col not in pks:
                    pks.append(id_col)
                elif owner != name and id_col not in fks:
                    fks[id_col] = f"{owner}.{id_col}"

        # Rule 5: Relationship hints
        for rel in relationships:
            if rel.get("left_table") == name:
                key_col = rel.get("key_column", "")
                right_table = rel.get("right_table", "")
                if key_col and right_table and key_col not in fks:
                    fks[key_col] = f"{right_table}.{key_col}"

        # Normalise to lowercase so they match the lowercase column names from pandas output
        result[name] = {
            "pks": [p.lower() for p in pks],
            "fks": {k.lower(): v.lower() for k, v in fks.items()},
        }

    # Apply user overrides (highest precedence)
    for tname, pk_list in (user_pk_overrides or {}).items():
        if tname in result:
            result[tname]["pks"] = [p.lower() for p in pk_list]

    for fk_key, fk_target in (user_fk_overrides or {}).items():
        parts = fk_key.split(".", 1)
        if len(parts) == 2:
            tname, col = parts
            if tname in result:
                result[tname]["fks"][col.lower()] = fk_target.lower()

    return result


# SAS: schema_utils.py:map_python_dtype_to_sql

_PYTHON_DTYPE_TO_SQL: dict[str, str] = {
    "object": "TEXT",
    "string": "TEXT",
    "int64": "BIGINT",
    "int32": "BIGINT",
    "int16": "BIGINT",
    "int8": "BIGINT",
    "float64": "DOUBLE PRECISION",
    "float32": "DOUBLE PRECISION",
    "bool": "BOOLEAN",
}


def map_python_dtype_to_sql(dtype: str) -> str:
    """Map a pandas dtype string to an ANSI SQL type.

    Args:
        dtype: Pandas dtype string e.g. "object", "int64", "datetime64[ns]".

    Returns:
        ANSI SQL type string e.g. "TEXT", "BIGINT", "TIMESTAMP".
    """
    # datetime64 variants e.g. "datetime64[ns]", "datetime64[us]"
    if dtype.startswith("datetime64"):
        return "TIMESTAMP"
    return _PYTHON_DTYPE_TO_SQL.get(dtype, "TEXT")
