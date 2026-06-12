# F34 — Data Storage Tab: Full Data Model View

**Phase:** 3
**Area:** Both (Backend / Worker + Frontend)
**Status:** in-progress
**GitHub issue:** #43

## Goal

Build a full data catalog and schema view for the Data Storage tab. Users (data architects, data engineers, governance leads) can see the complete data model of the SAS migration: all datasets grouped by LIBNAME, column definitions with SAS types and formats mapped to semantic target types, entity relationships derived from the SAS code, and target-agnostic DDL (ANSI SQL `CREATE TABLE` statements) for review and export.

Three internal development phases:
- **Phase 1:** Schema hierarchy tree (LIBNAME groupings) + table/column browser + editable LIBNAME→target schema name mapping
- **Phase 2:** Column types, labels, and formats extracted from `.sas7bdat` via pyreadstat + SAS format → semantic type mapping
- **Phase 3:** Relationship extraction (MERGE BY keys + PROC SQL JOIN ON) + ERD visualisation + DDL generation

## Acceptance Criteria

- [ ] All datasets grouped by LIBNAME in a tree; `work.*` flagged as temporary
- [ ] Clicking a table opens a column schema panel: column name, SAS type, SAS format, semantic type, label
- [ ] LIBNAME → target schema name is editable inline and persisted
- [ ] Column types extracted from `.sas7bdat` files via pyreadstat
- [ ] SAS format → semantic type mapping: character→String, date format→Date, datetime format→Timestamp, numeric→Number
- [ ] Relationships (MERGE BY keys, PROC SQL JOIN ON) visualised as an ERD using ReactFlow
- [ ] `CREATE TABLE` DDL rendered per table (ANSI SQL, target-agnostic)
- [ ] `make test` exits 0

## Phase 1 Subtasks

### P1-A: Extend _sniff_file and DataFileInfo with column metadata
**File:** `src/worker/main.py`, `src/worker/engine/models.py`
**Depends on:** none
**Done when:** `_sniff_file` returns a 5-tuple `(columns, row_count, column_types, column_labels, column_formats)` for `.sas7bdat` files (using `pyreadstat.read_sas7bdat` with `metadataonly=True`); `DataFileInfo` carries `column_types: dict[str, str]`, `column_labels: dict[str, str]`, `column_formats: dict[str, str]` all with `default_factory=dict`; the single call site in `main.py` updated to unpack the 5-tuple
- [x] done

### P1-B: Persist libname_map and data_schema in MigrationPlan
**File:** `src/worker/engine/models.py`, `src/worker/main.py`
**Depends on:** P1-A
**Done when:** `MigrationPlan` has `libname_map: dict[str, str] = Field(default_factory=dict)` and `data_schema: dict[str, dict] = Field(default_factory=dict)`; worker pipeline populates both after parse step (step 7a); `data_schema` keyed by normalised file path, value is `{columns, column_types, column_labels, column_formats, row_count}`; no Alembic migration needed (stored in existing `job.migration_plan` JSON column)
- [x] done

### P1-C: Add GET /jobs/{id}/schema backend route
**Files:** `src/backend/api/schemas.py`, `src/backend/api/routes/jobs.py`
**Depends on:** P1-B
**Done when:** New Pydantic schemas `ColumnSchema`, `TableSchema`, `JobSchemaResponse`; `GET /jobs/{id}/schema` route reads `job.migration_plan.data_schema` and `job.migration_plan.libname_map` plus `job.user_overrides.schema_overrides` (if present), assembles `JobSchemaResponse`; Phase 2 semantic_type derived at serve time from `sas_type` + `sas_format`; `ddl` field is empty string for now (Phase 3); `relationships` is empty list (Phase 3); unit tests for the route
- [x] done

### P1-D: Add PATCH /jobs/{id}/schema for user overrides
**Files:** `src/backend/api/schemas.py`, `src/backend/api/routes/jobs.py`
**Depends on:** P1-C
**Done when:** `PATCH /jobs/{id}/schema` accepts `{libname_overrides: dict[str, str], column_type_overrides: dict[str, dict[str, str]]}` and merges into `job.user_overrides` under a `schema_overrides` key; returns updated `JobSchemaResponse`
- [x] done

### P1-E: Add getJobSchema API client function
**Files:** `src/frontend/src/api/jobs.ts`, `src/frontend/src/api/types.ts`
**Depends on:** P1-C
**Done when:** `getJobSchema(jobId)` function added; `JobSchemaResponse`, `TableSchema`, `ColumnSchema` TypeScript types added; `patchJobSchema(jobId, overrides)` function added
- [x] done

### P1-F: Build DataStorageTab component — table browser + schema panel
**File:** `src/frontend/src/components/JobDetail/DataStorageTab.tsx` (new)
**Depends on:** P1-E
**Done when:** Left panel: LIBNAME tree grouping all datasets; each LIBNAME shows editable target schema name inline; `work.*` datasets shown in a muted "Temporary (not migrated)" group; clicking a dataset opens the schema panel; Right/main area: column table showing `name`, `sas_type`, `sas_format`, `semantic_type`, `label`; "—" shown for missing fields with an info note "Full metadata available for uploaded .sas7bdat files only"; derived datasets without column data show "Schema not yet extracted"; Phase 2 columns populated once P1-A data flows through
- [x] done

### P1-G: Wire DataStorageTab into JobDetailPage
**File:** `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** P1-F
**Done when:** `data-storage` TabsContent replaced with `<DataStorageTab>`; `getJobSchema` query added at page level (enabled when `isReviewable`); "Coming soon" placeholder removed
- [x] done

## Phase 2 Subtasks

### P2-A: Semantic type mapping function
**File:** `src/backend/api/routes/jobs.py` (or a new `src/backend/api/schema_utils.py`)
**Depends on:** P1-C
**Done when:** A pure function `map_sas_to_semantic_type(sas_type: str, sas_format: str) -> str` implements: `character` → `"String"`; `double` + format matching `DATE*` → `"Date"`; `double` + format matching `DATETIME*|DT*|DTDATE*` → `"Timestamp"`; `double` + format matching `COMMA*|DOLLAR*|E*|F*.` with decimals → `"Decimal"`; `double` otherwise → `"Number"`; function called in `GET /jobs/{id}/schema` when building `ColumnSchema.semantic_type`; unit tests for the mapping rules
- [ ] done

## Phase 3 Subtasks

### P3-A: Add merge_by_vars and join_on_keys to SASBlock
**File:** `src/worker/engine/models.py`
**Depends on:** none
**Done when:** `SASBlock` has `merge_by_vars: list[str] = Field(default_factory=list)` and `join_on_keys: list[dict[str, str]] = Field(default_factory=list)` (each entry: `{left_table, right_table, left_col, right_col}`)
- [ ] done

### P3-B: Extract MERGE BY keys and PROC SQL JOIN ON keys in parser
**File:** `src/worker/engine/parser.py`
**Depends on:** P3-A
**Done when:** In `_extract_data_steps`, when a DATA step contains MERGE, a regex extracts the BY clause column names into `block.merge_by_vars`; in `_extract_proc_sql`, a regex extracts `ON left.col = right.col` predicates into `block.join_on_keys`; unit tests covering MERGE BY extraction and simple JOIN ON extraction
- [ ] done

### P3-C: Build relationships list and persist to MigrationPlan
**File:** `src/worker/engine/models.py`, `src/worker/main.py`
**Depends on:** P3-A, P3-B
**Done when:** `MigrationPlan` has `relationships: list[dict[str, str]] = Field(default_factory=list)`; worker pipeline aggregates all non-empty `merge_by_vars` and `join_on_keys` from all blocks after planning and stores them on `migration_plan.relationships`; each entry: `{left_table, right_table, key_column, via_block_id, relationship_type: "merge" | "join"}`
- [ ] done

### P3-D: DDL generation module
**File:** `src/worker/engine/ddl_generator.py` (new)
**Depends on:** P2-A
**Done when:** `generate_create_table(table_name: str, target_schema: str, columns: list[ColumnSchema]) -> str` generates ANSI SQL `CREATE TABLE schema.table (col TYPE)` using semantic_type → SQL type mapping: `String→TEXT`, `Date→DATE`, `Timestamp→TIMESTAMP`, `Decimal→DECIMAL`, `Number→DOUBLE PRECISION`, `Integer→BIGINT`; unit tests covering each type mapping and full DDL output
- [ ] done

### P3-E: Surface relationships and DDL in GET /jobs/{id}/schema
**File:** `src/backend/api/routes/jobs.py`
**Depends on:** P3-C, P3-D
**Done when:** `JobSchemaResponse.relationships` populated from `migration_plan.relationships`; `TableSchema.ddl` populated by calling `generate_create_table` at serve time; TypeScript types updated
- [ ] done

### P3-F: Build DataStorageERD component
**File:** `src/frontend/src/components/JobDetail/DataStorageERD.tsx` (new)
**Depends on:** P3-E
**Done when:** ReactFlow graph with dagre auto-layout; each node is a table entity box showing table name + column count; edges connect related tables (from `relationships`), labelled with the join/merge key column; clicking a node selects it in the schema panel; `initialView` similar to LineageGraph pattern
- [ ] done

### P3-G: Add DDL panel and ERD tab toggle to DataStorageTab
**File:** `src/frontend/src/components/JobDetail/DataStorageTab.tsx`
**Depends on:** P3-D, P3-F
**Done when:** Schema panel shows a "DDL" button that expands a syntax-highlighted code block with the `CREATE TABLE` statement (use `MonacoEditor` read-only, `language="sql"`); a "Schema / ERD" toggle at the top of the main area switches between the table browser and the ERD; relationships shown on the ERD component
- [ ] done

### P3-H: make test exits 0
**Depends on:** all subtasks
**Done when:** All 7 gates green
- [ ] done

## Dependencies on other features

- F28 (chevron tab shell) — complete; `?tab=data-storage` routing in place
- F33 (ETL tab) — complete
- pyreadstat already in dependencies (used for `.sas7bdat` reading)
- ReactFlow + dagre already installed

## Out of scope

- User-selectable DDL target platform (Databricks Delta, Snowflake, etc.) — tracked in backlog
- Column-level lineage (which column flows from which source column)
- PROC FORMAT value label mappings (Tier 2 #39 gap)
- Row count for derived datasets (not computed until reconciliation runs)
- Schema approval workflow (approve per table before accepting migration)
