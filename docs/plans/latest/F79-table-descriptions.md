# F79 — Data Table Descriptions

**Phase:** 3
**Area:** Both (Backend / API + Frontend)
**Status:** complete

## Goal

Add a 1–2 sentence natural-language description to every table in the Data Storage tab.
Source table descriptions are derived from SAS column labels (already extracted by
pyreadstat). Output table descriptions are derived from the `BlockPlan.rationale` that the
`MigrationPlannerAgent` already produces — so **no additional LLM calls are needed**.

Descriptions appear as a subtitle in the left-sidebar table rows and in the right-panel
header. They are also embedded in the DDL output as a Databricks-compatible `COMMENT`
clause (`CREATE TABLE ... COMMENT 'description'`), so they flow into Unity Catalog
automatically when the migration bundle is deployed.

Done looks like: every table in the Data tab has a short description visible without
clicking into it; the DDL collapsible shows a `COMMENT` line when a description exists.

## Acceptance Criteria

- [ ] Every `TableSchema` object exposes a non-empty `description` field after `build_job_schema()` runs on a job with a populated migration plan
- [ ] Output table descriptions match the rationale of the block that produces them
- [ ] Source table descriptions reference at least one column label when pyreadstat labels are present
- [ ] `generate_create_table()` appends `COMMENT 'description'` when a description is supplied
- [ ] Description is visible as a subtitle in the Data tab sidebar and right-panel header
- [ ] `make test` exits 0
- [ ] ruff and mypy pass

## Subtasks

### S-A: `derive_table_descriptions()` in schema_utils.py
**File:** `src/backend/api/schema_utils.py`
**Depends on:** none
**Done when:** A `derive_table_descriptions(data_schema, plan)` function exists that returns `dict[str, str]` (keyed by `data_schema` path). Output tables use the rationale of the block whose `output_datasets` includes that table name; source tables use pyreadstat `column_labels` (first 3 informative labels); both fall back to a short template.
- [x] done

### S-B: Wire description into `TableSchema` and `build_job_schema()`
**Files:** `src/backend/api/schemas.py`, `src/backend/api/schema_utils.py`
**Depends on:** S-A
**Done when:** `TableSchema` has `description: str = ""`; `build_job_schema()` calls `derive_table_descriptions()` and sets `t.description` on each table before returning.
- [x] done

### S-C: DDL `COMMENT` clause in `generate_create_table()`
**File:** `src/worker/engine/ddl_generator.py`
**Depends on:** none
**Done when:** `generate_create_table()` accepts an optional `description: str = ""` param; when non-empty the output ends with `COMMENT 'escaped_description'` before the semicolon (Databricks/Spark SQL syntax); single-quotes inside the description are escaped as `''`.
- [x] done

### S-D: Pass description to DDL generator in `build_job_schema()`
**File:** `src/backend/api/schema_utils.py`
**Depends on:** S-B, S-C
**Done when:** Both `generate_create_table()` call sites in `build_job_schema()` pass `description=t.description`.
- [x] done

### S-E: Unit tests
**File:** `tests/test_table_descriptions.py`
**Depends on:** S-A, S-C
**Done when:** Tests cover: (1) output table picks up block rationale, (2) source table picks up column labels, (3) fallback when neither is present, (4) DDL with description contains `COMMENT`, (5) DDL without description has no `COMMENT`.
- [x] done

### S-F: Frontend — TypeScript type + sidebar subtitle + header subtitle
**Files:** `src/frontend/src/api/types.ts`, `src/frontend/src/components/JobDetail/DataStorageTab.tsx`
**Depends on:** S-B
**Done when:** `TableSchema` TS type has `description?: string`; sidebar rows show description as a truncated second line under the dataset name when non-empty; right-panel header shows description as a muted subtitle line below the dataset name.
- [x] done

### S-G: make test exits 0
**File:** n/a (gate)
**Depends on:** S-A through S-F
**Done when:** `make test` exits 0 with all 7 gates green.
- [x] done

## Implementation notes

### `derive_table_descriptions` logic

```python
def derive_table_descriptions(
    data_schema: dict[str, dict[str, Any]],
    plan: dict[str, Any],
) -> dict[str, str]:
    import os

    # Build dataset_name (lower) → block rationale from existing BlockPlan data
    output_to_rationale: dict[str, str] = {}
    for block in plan.get("blocks", []):
        rationale: str = block.get("rationale", "")
        for ds in block.get("output_datasets", []):
            if rationale and ds.lower() not in output_to_rationale:
                output_to_rationale[ds.lower()] = rationale

    result: dict[str, str] = {}
    for path, schema_info in data_schema.items():
        ds_name = os.path.splitext(os.path.basename(path))[0]

        if ds_name.lower() in output_to_rationale:
            result[path] = output_to_rationale[ds_name.lower()]
            continue

        col_labels: dict[str, str] = schema_info.get("column_labels", {})
        row_count: int | None = schema_info.get("row_count")
        informative = [v for v in col_labels.values() if v and len(v) > 3][:3]

        if informative:
            suffix = f" ({row_count:,} rows)" if row_count else ""
            result[path] = f"SAS source dataset. Columns include: {', '.join(informative)}{suffix}."
        else:
            result[path] = f"SAS source dataset{(' — ' + f'{row_count:,} rows') if row_count else ''}."

    return result
```

### DDL COMMENT syntax

Databricks and Spark SQL support inline `COMMENT` on the `CREATE TABLE` statement:
```sql
CREATE TABLE public.dm_raw (
    usubjid TEXT,
    age DOUBLE PRECISION
) COMMENT 'Demographic dataset. Columns include: Subject Identifier, Age at Screening.';
```
Single-quotes inside the description must be escaped as `''`.

### Frontend display

Sidebar row (second line, under dataset name):
```tsx
{table.description && (
  <span className="block text-xs text-muted-foreground/70 font-sans font-normal truncate">
    {table.description}
  </span>
)}
```

Right-panel header (below dataset name `<span>`):
```tsx
{selectedTable.description && (
  <p className="text-xs text-muted-foreground mt-0.5">{selectedTable.description}</p>
)}
```

## Dependencies on other features

- F78 (Data Storage tab polish) — complete, provides the visual context this feature builds on

## Out of scope for this feature

- Column-level descriptions (only table-level)
- New LLM calls — descriptions are derived from existing data only
- Editing descriptions in the UI (read-only display only)
- MS SQL `COMMENT ON TABLE` syntax (separate DDL dialect feature)
