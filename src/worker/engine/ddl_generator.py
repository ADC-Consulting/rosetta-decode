"""DDL generator — produces ANSI SQL CREATE TABLE statements from column schema data.

This module is intentionally free of backend imports. It accepts column metadata as plain
dicts so it can be called from both the worker pipeline and the backend API layer without
creating a cross-service import dependency.

Each column dict is expected to carry the key ``"semantic_type"`` (string). Unrecognised
or missing values are treated as ``TEXT`` — a safe, lossless default.

Example::

    from src.worker.engine.ddl_generator import generate_create_table

    columns = [
        {"name": "patient_id", "semantic_type": "String"},
        {"name": "visit_date", "semantic_type": "Date"},
        {"name": "weight_kg",  "semantic_type": "Number"},
    ]
    ddl = generate_create_table("patients", "clinical", columns)
    # CREATE TABLE clinical.patients (
    #     patient_id TEXT,
    #     visit_date DATE,
    #     weight_kg DOUBLE PRECISION
    # );
"""

# SAS: src/worker/engine/ddl_generator.py:1

import logging

logger = logging.getLogger(__name__)

# Mapping from semantic type names (as produced by map_sas_to_semantic_type)
# to ANSI SQL column types.  Any unrecognised value falls through to TEXT.
_SEMANTIC_TO_SQL: dict[str, str] = {
    "String": "TEXT",
    "Date": "DATE",
    "Timestamp": "TIMESTAMP",
    "Decimal": "DECIMAL",
    "Number": "DOUBLE PRECISION",
    "Integer": "BIGINT",
    # Raw SQL types passed through directly (used by F35 target-column DDL generation)
    "TEXT": "TEXT",
    "BIGINT": "BIGINT",
    "DOUBLE PRECISION": "DOUBLE PRECISION",
    "TIMESTAMP": "TIMESTAMP",
    "BOOLEAN": "BOOLEAN",
}

_FALLBACK_SQL_TYPE = "TEXT"
_INDENT = "    "


def _semantic_to_sql_type(semantic_type: str) -> str:
    """Return the ANSI SQL type for a semantic type string.

    Unknown or empty values default to TEXT (safe, lossless).

    Args:
        semantic_type: One of the known semantic type strings, or an arbitrary value.

    Returns:
        An ANSI SQL type string such as ``"TEXT"`` or ``"DOUBLE PRECISION"``.
    """
    # SAS: src/worker/engine/ddl_generator.py:_semantic_to_sql_type
    return _SEMANTIC_TO_SQL.get(semantic_type, _FALLBACK_SQL_TYPE)


def generate_create_table(
    table_name: str,
    target_schema: str,
    columns: list[dict[str, str]],
) -> str:
    r"""Generate an ANSI SQL ``CREATE TABLE`` statement from column metadata dicts.

    Each dict in *columns* must contain at minimum the key ``"name"`` (column name) and
    ``"semantic_type"`` (one of ``"String"``, ``"Date"``, ``"Timestamp"``, ``"Decimal"``,
    ``"Number"``, ``"Integer"``).  Any other semantic type value — including ``"Unknown"``
    or an empty string — maps to ``TEXT``.

    Column names are lowercased in the output.

    Args:
        table_name: Unqualified table name (e.g. ``"dm_raw"``).
        target_schema: Target schema name (e.g. ``"public"`` or ``"clinical"``).
        columns: Ordered list of column metadata dicts.  Required keys per entry:
            ``"name"`` (str) — column identifier;
            ``"semantic_type"`` (str) — semantic type string used for SQL type mapping.

    Returns:
        A complete, semicolon-terminated ANSI SQL ``CREATE TABLE`` statement.
    """
    # SAS: src/worker/engine/ddl_generator.py:generate_create_table
    qualified_name = f"{target_schema}.{table_name}"

    if not columns:
        logger.debug("generate_create_table: no columns for %s — emitting stub DDL", qualified_name)
        return f"CREATE TABLE {qualified_name} (\n{_INDENT}-- no columns extracted\n);"

    col_lines: list[str] = []
    last_index = len(columns) - 1
    for idx, col in enumerate(columns):
        col_name = col.get("name", "").lower()
        semantic_type = col.get("semantic_type", "")
        sql_type = _semantic_to_sql_type(semantic_type)
        trailing_comma = "," if idx < last_index else ""
        col_lines.append(f"{_INDENT}{col_name} {sql_type}{trailing_comma}")

    body = "\n".join(col_lines)
    return f"CREATE TABLE {qualified_name} (\n{body}\n);"
