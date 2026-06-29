"""Utilities for mapping SAS data types and formats to semantic target types."""

# SAS: src/backend/api/schema_utils.py:1

import os
import re
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.backend.api.schemas import TableSchema
    from src.backend.db.models import Job

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


# SAS: schema_utils.py:map_semantic_to_spark_type
# Maps semantic type names (as produced by map_sas_to_semantic_type) to PySpark DDL type strings.
_SEMANTIC_TO_SPARK: dict[str, str] = {
    "String": "StringType()",
    "Date": "DateType()",
    "Timestamp": "TimestampType()",
    "Decimal": "DecimalType(18, 4)",
    "Integer": "LongType()",
    "Number": "DoubleType()",
}


def map_semantic_to_spark_type(semantic_type: str) -> str:
    """Map a semantic type name to a PySpark DDL type string.

    Args:
        semantic_type: One of "String", "Date", "Timestamp", "Decimal", "Integer", "Number".

    Returns:
        PySpark type string e.g. "StringType()", "DateType()". Defaults to "StringType()".
    """
    return _SEMANTIC_TO_SPARK.get(semantic_type, "StringType()")


# SAS: schema_utils.py:derive_table_descriptions


def derive_table_descriptions(
    data_schema: dict[str, dict[str, Any]],
    plan: dict[str, Any],
    lineage: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Return {path: description} derived from existing migration plan and lineage data.

    Priority for output tables:
    1. lineage.dataset_summaries — business-facing summaries written by the planner
    2. lineage.pipeline_steps — description of the step that produces the table
    3. block_plans rationale — fallback (migration-focused, less user-friendly)

    Source tables use pyreadstat column_labels when available.
    No LLM calls.

    Args:
        data_schema: Keyed by file path; each entry has columns/column_types/
            column_labels/row_count.
        plan: The migration_plan dict — has "block_plans" list, each with "rationale"
            and "output_datasets" (libname-prefixed names like "outdir.foo" are handled).
        lineage: Optional lineage dict — may contain "dataset_summaries" and
            "pipeline_steps" with richer, business-facing descriptions.

    Returns:
        Dict keyed by path with a short description string.
    """
    import os as _os

    lin: dict[str, Any] = lineage or {}

    # Priority 1: lineage.dataset_summaries — bare name (strip libname prefix) → description
    dataset_summaries: dict[str, str] = {}
    for ds_key, summary in lin.get("dataset_summaries", {}).items():
        bare = ds_key.split(".")[-1].lower()
        if summary and bare not in dataset_summaries:
            dataset_summaries[bare] = summary

    # Priority 2: pipeline step description — for each table in step.outputs, use step.description
    step_descriptions: dict[str, str] = {}
    for step in lin.get("pipeline_steps", []):
        step_desc: str = step.get("description", "")
        if not step_desc:
            continue
        for ds in step.get("outputs", []):
            bare = ds.split(".")[-1].lower()
            if bare not in step_descriptions:
                step_descriptions[bare] = step_desc

    # Priority 3: block rationale — skip source-library datasets (rawdir.* etc.)
    source_libnames: set[str] = {k.lower() for k in plan.get("libname_map", {})}
    output_to_rationale: dict[str, str] = {}
    for block in plan.get("block_plans", []):
        rationale: str = block.get("rationale", "")
        for ds in block.get("output_datasets", []):
            parts = ds.lower().split(".", 1)
            if len(parts) == 2 and parts[0] in source_libnames:
                continue
            bare = parts[-1]
            if rationale and bare not in output_to_rationale:
                output_to_rationale[bare] = rationale

    result: dict[str, str] = {}
    for path, schema_info in data_schema.items():
        ds_name = _os.path.splitext(_os.path.basename(path))[0].lower()

        # Output table: try each priority level
        if ds_name in dataset_summaries:
            result[path] = dataset_summaries[ds_name]
            continue
        if ds_name in step_descriptions:
            result[path] = step_descriptions[ds_name]
            continue
        if ds_name in output_to_rationale:
            result[path] = output_to_rationale[ds_name]
            continue

        # Source table: derive from pyreadstat column_labels
        col_labels: dict[str, str] = schema_info.get("column_labels", {})
        row_count: int | None = schema_info.get("row_count")
        informative = [v for v in col_labels.values() if v and len(v) > 3][:3]

        if informative:
            suffix = f" ({row_count:,} rows)" if row_count else ""
            result[path] = f"SAS source dataset. Columns include: {', '.join(informative)}{suffix}."
        else:
            row_str = f" — {row_count:,} rows" if row_count else ""
            result[path] = f"SAS source dataset{row_str}."

    return result


# SAS: schema_utils.py:build_job_schema


async def build_job_schema(job: "Job", db: AsyncSession) -> "list[TableSchema]":
    """Assemble the list of TableSchema objects for a job from its migration plan and overrides.

    Applies ``user_overrides["schema_overrides"]`` (per-path column type overrides,
    target_schema overrides, pk/fk overrides) in exactly the same order as the
    ``GET /jobs/{id}/schema`` route.

    Args:
        job: ORM Job instance with ``migration_plan``, ``user_overrides``, and ``lineage``.
        db: Async SQLAlchemy session (reserved for future use; not queried directly here).

    Returns:
        List of TableSchema instances ready to be returned in JobSchemaResponse.tables.
    """
    from src.backend.api.schemas import ColumnSchema, RelationshipSchema, TableSchema
    from src.worker.engine.ddl_generator import generate_create_table

    plan: dict[str, Any] = job.migration_plan or {}
    overrides: dict[str, Any] = (job.user_overrides or {}).get("schema_overrides", {})

    libname_map: dict[str, str] = plan.get("libname_map", {})
    data_schema: dict[str, dict[str, Any]] = plan.get("data_schema", {})
    relationships_raw: list[dict[str, Any]] = plan.get("relationships", [])
    output_schema: dict[str, list[dict[str, str]]] = plan.get("output_schema", {})

    tables: list[TableSchema] = []
    for path, schema_info in data_schema.items():
        columns_raw: list[str] = schema_info.get("columns", [])
        col_types: dict[str, str] = schema_info.get("column_types", {})
        col_labels: dict[str, str] = schema_info.get("column_labels", {})
        col_formats: dict[str, str] = schema_info.get("column_formats", {})
        row_count: int | None = schema_info.get("row_count")

        libname: str | None = None
        norm_path = path.lstrip("./")
        for lib_name, lib_path in libname_map.items():
            norm_lib = lib_path.lstrip("./").rstrip("/")
            if norm_path.startswith(norm_lib + "/") or norm_lib in norm_path:
                libname = lib_name
                break

        path_overrides: dict[str, Any] = overrides.get(path, {})
        libname_key = f"__libname__{libname}" if libname else None
        libname_override_entry: dict[str, Any] = (
            overrides.get(libname_key, {}) if libname_key else {}
        )
        default_schema = libname_override_entry.get("target_schema") or libname or "public"
        target_schema: str = path_overrides.get("target_schema", default_schema)

        col_type_overrides: dict[str, str] = path_overrides.get("column_type_overrides", {})
        columns: list[ColumnSchema] = []
        for col_name in columns_raw:
            sas_type = col_types.get(col_name, "")
            sas_format: str | None = col_formats.get(col_name)
            label: str | None = col_labels.get(col_name)
            semantic_type = map_sas_to_semantic_type(sas_type, sas_format)
            override_type: str | None = col_type_overrides.get(col_name)
            columns.append(
                ColumnSchema(
                    name=col_name,
                    sas_type=sas_type,
                    sas_format=sas_format,
                    label=label,
                    semantic_type=semantic_type,
                    override_type=override_type,
                )
            )

        dataset_name = os.path.splitext(os.path.basename(path))[0]
        tables.append(
            TableSchema(
                path=path,
                dataset_name=dataset_name,
                libname=libname,
                target_schema=target_schema,
                columns=columns,
                row_count=row_count,
                ddl="",
            )
        )

    lineage_raw: dict[str, Any] = job.lineage or {}
    pipeline_steps: list[dict[str, Any]] = lineage_raw.get("pipeline_steps", [])
    if pipeline_steps:
        all_inputs: set[str] = {
            ds.lower() for step in pipeline_steps for ds in step.get("inputs", [])
        }
        all_outputs: set[str] = {ds for step in pipeline_steps for ds in step.get("outputs", [])}
        pure_outputs: set[str] = {ds for ds in all_outputs if ds.lower() not in all_inputs}
        existing_names: set[str] = {t.dataset_name.lower() for t in tables}
        for ds_name in sorted(pure_outputs):
            if ds_name.lower() in existing_names:
                continue
            tables.append(
                TableSchema(
                    path=f"output/{ds_name}",
                    dataset_name=ds_name,
                    libname=None,
                    target_schema="public",
                    columns=[],
                    target_columns=[],
                    row_count=None,
                    ddl="",
                    ddl_source="source_estimated",
                    schema_status="not_run",
                )
            )

    relationships: list[RelationshipSchema] = [
        RelationshipSchema(**r)
        for r in relationships_raw
        if all(
            k in r
            for k in (
                "left_table",
                "right_table",
                "key_column",
                "via_block_id",
                "relationship_type",
            )
        )
    ]

    tables_for_inference = [
        {
            "dataset_name": t.dataset_name,
            "columns": [c.name for c in t.target_columns] or [c.name for c in t.columns],
            "column_types": {c.name: (c.python_type or "") for c in t.target_columns},
            "target_columns": [],
        }
        for t in tables
    ]
    pk_fk = infer_pk_fk(
        tables_for_inference,
        [r.model_dump() for r in relationships],
        user_pk_overrides=overrides.get("pk_overrides", {}),
        user_fk_overrides=overrides.get("fk_overrides", {}),
    )

    for t in tables:
        raw_target_cols: list[dict[str, str]] = output_schema.get(t.dataset_name, [])
        pk_fk_entry = pk_fk.get(t.dataset_name, {"pks": [], "fks": {}})
        pks: list[str] = pk_fk_entry.get("pks", [])
        fks: dict[str, str] = pk_fk_entry.get("fks", {})

        if raw_target_cols:
            target_columns: list[ColumnSchema] = [
                ColumnSchema(
                    name=col_info["name"],
                    sas_type="",
                    python_type=col_info.get("python_type"),
                    sql_type=map_python_dtype_to_sql(col_info.get("python_type", "object")),
                    is_pk=col_info["name"].lower() in pks,
                    is_fk=col_info["name"].lower() in fks,
                    fk_ref=fks.get(col_info["name"].lower()),
                )
                for col_info in raw_target_cols
            ]
            t.target_columns = target_columns

            if len(target_columns) == len(t.columns):
                t.schema_status = "migrated"
            else:
                t.schema_status = "changed"
            t.ddl_source = "target"

            ddl_columns = [
                {"name": c.name, "semantic_type": c.sql_type or "TEXT"} for c in target_columns
            ]
            t.ddl = generate_create_table(t.dataset_name, t.target_schema, ddl_columns)
        else:
            t.schema_status = "not_run"
            t.ddl_source = "source_estimated"
            for col in t.columns:  # SAS: src/backend/api/schema_utils.py:499
                col.is_pk = col.name.lower() in pks
                col.is_fk = col.name.lower() in fks
                col.fk_ref = fks.get(col.name.lower())
            ddl_columns = [{"name": c.name, "semantic_type": c.semantic_type} for c in t.columns]
            t.ddl = generate_create_table(t.dataset_name, t.target_schema, ddl_columns)

    # Stamp descriptions and regenerate DDL with COMMENT clause
    descriptions = derive_table_descriptions(data_schema, plan, lineage=lineage_raw)
    for t in tables:
        t.description = descriptions.get(t.path, "")
        if t.ddl:
            ddl_cols = (
                [{"name": c.name, "semantic_type": c.sql_type or "TEXT"} for c in t.target_columns]
                if t.target_columns
                else [{"name": c.name, "semantic_type": c.semantic_type} for c in t.columns]
            )
            t.ddl = generate_create_table(
                t.dataset_name, t.target_schema, ddl_cols, description=t.description
            )

    return tables
