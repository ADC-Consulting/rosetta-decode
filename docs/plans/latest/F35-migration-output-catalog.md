# F35 — Migration Output Catalog

**Phase:** 3  
**Area:** Both (Backend / Worker + Frontend)  
**Status:** complete  
**GitHub issue:** TBD

## Goal

Evolve the Data Storage tab into a full migration output catalog: show both the
source SAS schema and the actual Python execution output side-by-side, drive the
DDL from execution truth, and replace the current simple ReactFlow ERD with two
purpose-built visualisations:

1. **Data Model ERD** (ported from structor canvas) — column-level table diagram
   with PK/FK badges, type annotations, Bezier FK edges, focus highlighting.
2. **Data Flow diagram** — source datasets → transformation blocks → target
   datasets, showing the full pipeline at dataset level.

PK/FK relationships are inferred automatically from naming conventions and
SDTM/ADaM standards, and overrideable by the user via the ERD UI.

## Acceptance Criteria

- [ ] After reconciliation, each output dataset's schema (column names + Python
      dtypes → SQL types) is captured and stored in `MigrationPlan`
- [ ] Schema route exposes `target_columns` (name, sql_type, python_type, is_pk,
      is_fk, fk_ref) and `schema_status` ("migrated" | "changed" | "not_run") per table
- [ ] PKs and FKs are inferred automatically; user can toggle them in the ERD and
      changes persist via `PATCH /jobs/{id}/schema`
- [ ] DDL is generated from target schema when available, source schema as fallback;
      panel labelled accordingly ("Target DDL" vs "Source DDL (estimated)")
- [ ] Data Model ERD: structor-style column-level canvas; FK edges connect child
      column → parent PK column; PK/FK/NN badges visible on columns; clicking a table
      highlights upstream/downstream dependencies
- [ ] Data Flow diagram: source tables left → SAS file blocks centre → target tables
      right; ReactFlow + dagre LR layout; node shows table name + col count
- [ ] ERD panel has `[Data Model]` / `[Data Flow]` segmented toggle
- [ ] Column panel: side-by-side source/target column comparison with STATUS badge
      (✓ unchanged / + added / ✗ dropped / ↷ renamed) and target type
- [ ] Table sidebar: status dot per table (◉ migrated, △ changed, ○ not run)
- [ ] `make test` exits 0

## Architecture Notes

### PK inference rules (applied in order, first match wins)
1. Column named `USUBJID` → PK (SDTM/ADaM universal subject key)
2. Column named `STUDYID` + `USUBJID` together → compound PK (SDTM datasets)
3. Column name ends with `ID` and is `TEXT`/`String` type → PK candidate in its
   "owner" table (smallest table that defines it), FK in all others
4. Column named `*SEQ` (sequence number) alongside `USUBJID` → compound PK
   (SDTM observation datasets: DM has USUBJID; EX/AE/LB have USUBJID+*SEQ)
5. Fallback: no PK inferred — user must set explicitly

### FK inference rules
- If a `TEXT` column name appears as inferred PK in another table → infer FK
- Existing `MigrationPlan.relationships` (MERGE BY / JOIN ON) provide edge hints;
  map source table names to target table names via output_schema keys

### User override persistence
```
PATCH /jobs/{id}/schema
{
  "schema_overrides": {
    "pk_overrides": {
      "sdtm_dm": ["usubjid"],           // explicit PK list
      "sdtm_ex": ["usubjid", "exseq"]
    },
    "fk_overrides": {
      "sdtm_ex.usubjid": "sdtm_dm.usubjid",  // child.col → parent.col
      "adsl.usubjid":    "sdtm_dm.usubjid"
    }
  }
}
```

### structor canvas port strategy
Port as read-only (no edit/create/reconnect interactions in V1).
Remove: drag-to-create edges, reconnect handles, double-click rename.
Keep: zoom/pan, column-level FK edges, focus highlighting, PK/FK/NN badges,
collapse/expand nodes, Bezier SVG paths.

Target location: `src/frontend/src/components/SchemaCanvas/`

Files to port:
- `schema-canvas.tsx` → `SchemaCanvas.tsx`
- `schema-canvas-nodes-layer.tsx` → `SchemaCanvasNodesLayer.tsx`
- `schema-canvas-geometry.ts` → `schemaCanvasGeometry.ts`
- `schema-canvas-focus.ts` → `schemaCanvasFocus.ts`
- `layout-constants.ts` → `layoutConstants.ts`
- `graph-types.ts` + `types.ts` → `types.ts`
- `schema-studio.css` → `SchemaCanvas.css`

New file: `schemaResponseToCanvas.ts` — maps `JobSchemaResponse` →
`{ nodes: GraphNode<TableNodeData>[], edges: GraphEdge<CanvasEdgeData>[] }`

## Phase 1 — Backend: capture execution output schema

### P1-A: Return output schema from ReconciliationService
**File:** `src/worker/validation/reconciliation.py`  
**Depends on:** none  
**Done when:** `ReconciliationResult` (or equivalent return type) includes
`output_schema: dict[str, Any]` populated from `actual_df.dtypes.to_dict()`
(already computed at line 278); column names from `list(actual_df.columns)`;
no change to existing reconciliation logic or return value for callers that
don't use the new field.
- [x] done

### P1-B: Persist output_schema on MigrationPlan
**File:** `src/worker/engine/models.py`, `src/worker/main.py`  
**Depends on:** P1-A  
**Done when:** `MigrationPlan` has
`output_schema: dict[str, list[dict[str, str]]] = Field(default_factory=dict)`
— keyed by dataset name, value is list of `{name, python_type}` dicts;
worker stores schema from each reconciled block's `actual_df` into
`migration_plan.output_schema[dataset_name]` after block execution;
non-reconciled blocks left absent (frontend treats absent = "not run").
- [x] done

### P1-C: Infer PK/FK from output schema
**File:** `src/backend/api/schema_utils.py` (new function `infer_pk_fk`)  
**Depends on:** P1-B  
**Done when:** `infer_pk_fk(tables: list[TableSchema], relationships: list[RelationshipSchema]) -> dict[str, PKFKInfo]`
applies inference rules (see Architecture Notes above); returns per-table
`{pks: list[str], fks: dict[str, str]}` (fks: column → "other_table.column");
user overrides from `job.user_overrides.schema_overrides` applied on top;
unit tests covering each inference rule and override precedence.
- [x] done

### P1-D: Map Python dtypes → SQL types
**File:** `src/backend/api/schema_utils.py`  
**Depends on:** P1-B  
**Done when:** `map_python_dtype_to_sql(dtype: str) -> str` maps pandas dtype
strings to ANSI SQL: `object→TEXT`, `int64/int32→BIGINT`, `float64→DOUBLE PRECISION`,
`datetime64[ns]→TIMESTAMP`, `bool→BOOLEAN`; used when building `target_columns`
in the schema route; unit tests for each mapping.
- [x] done

### P1-E: Extend schema route with target_columns and schema_status
**File:** `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py`  
**Depends on:** P1-C, P1-D  
**Done when:** `ColumnSchema` gains `python_type: str | None`, `is_pk: bool`,
`is_fk: bool`, `fk_ref: str | None` (e.g. `"sdtm_dm.usubjid"`);
`TableSchema` gains `target_columns: list[ColumnSchema]` and
`schema_status: Literal["migrated", "changed", "not_run"]`;
`schema_status` is "migrated" if output_schema present and col count matches
source, "changed" if col count differs, "not_run" if absent;
DDL generated from `target_columns` when present, source columns as fallback;
DDL source flagged: `ddl_source: Literal["target", "source_estimated"]`;
unit tests for status logic and DDL source selection.
- [x] done

### P1-F: PATCH schema accepts pk/fk overrides
**File:** `src/backend/api/routes/jobs.py`  
**Depends on:** P1-E  
**Done when:** `PATCH /jobs/{id}/schema` body accepts `pk_overrides: dict[str, list[str]]`
and `fk_overrides: dict[str, str]` (child_table.col → parent_table.col);
merged into `job.user_overrides.schema_overrides`; schema route re-runs
inference and applies overrides on each GET; unit tests for merge behaviour.
- [x] done

## Phase 2 — Frontend: port structor canvas

### P2-A: Port structor canvas components
**File:** `src/frontend/src/components/SchemaCanvas/` (new directory)  
**Depends on:** none  
**Done when:** All listed structor files ported and adapted to rosetta-decode
(TypeScript strict, Tailwind, shadcn/ui tokens for colours); read-only mode
(no edge-create drag, no rename); components compile with `make test`; CSS
scoped to avoid global leakage.
- [x] done

### P2-B: Adapter — schema response → canvas format
**File:** `src/frontend/src/components/SchemaCanvas/schemaResponseToCanvas.ts`  
**Depends on:** P2-A, P1-E TypeScript types  
**Done when:** `schemaResponseToCanvas(tables, relationships, pkfkOverrides)` returns
`{nodes: GraphNode<TableNodeData>[], edges: GraphEdge<CanvasEdgeData>[]}`;
each table becomes a node with `target_columns` (falling back to `columns`);
each FK relationship becomes an edge from child column handle to parent PK handle;
layout positions tables in schema-grouped columns (RAW left, SDTM centre, ADAM right);
unit tests for FK edge generation and column fallback.
- [x] done

### P2-C: DataModelERD component
**File:** `src/frontend/src/components/JobDetail/DataModelERD.tsx` (new)  
**Depends on:** P2-A, P2-B  
**Done when:** `<DataModelERD tables={} relationships={} onOverride={} />` renders
structor canvas; PK column rows show 🔑 icon; FK columns show chain icon + FK
badge; clicking a column's PK/FK badge fires `onOverride` callback (debounced
PATCH to backend); focus highlight on table click (upstream/downstream path);
empty state when no tables; loading skeleton while data fetches.
- [x] done

### P2-D: DataFlowDiagram component
**File:** `src/frontend/src/components/JobDetail/DataFlowDiagram.tsx` (new)  
**Depends on:** P1-E (for target table metadata)  
**Done when:** Three-column ReactFlow layout (source tables left, SAS file
blocks centre, target tables right); source nodes: table name + col count +
"SAS" badge; block nodes: filename, greyed if not reconciled; target nodes:
table name + col count + schema_status dot; edges: source→block (input) and
block→target (output), derived from `block.input_datasets` /
`block.output_datasets`; dagre LR layout; read-only (no drag).
- [x] done

### P2-E: ERD panel toggle — Data Model / Data Flow
**File:** `src/frontend/src/components/JobDetail/DataStorageTab.tsx`  
**Depends on:** P2-C, P2-D  
**Done when:** When ERD mode is active, a secondary segmented control shows
`[Data Model]` `[Data Flow]`; state persists for the session; `DataModelERD`
rendered for Data Model, `DataFlowDiagram` for Data Flow; existing ERD
(ReactFlow simple graph from P3-F/G) removed and replaced.
- [x] done

## Phase 3 — Column diff panel and sidebar indicators

### P3-A: Source / target column diff table
- [x] done — four-way branch: diff table (+/✗/✓ badges, green/red rows, SAS+SQL types, PK/FK flags) when target_columns present; source-only table as fallback; empty state when not_run

### P3-B: Table sidebar status indicators
- [x] done — coloured dot (green/amber/muted) before dataset_name; legend pinned at sidebar bottom

### P3-C: DDL label reflects source
- [x] done — "Target DDL" / "Source DDL + amber estimated badge" / "DDL" fallback

### P3-D: make test exits 0
- [x] done — all 7 gates green

## Dependencies on other features

- F34 (Data Storage tab Phase 1-3) — complete; schema route, DataStorageTab,
  DataStorageERD all in place; F35 extends and partially replaces them
- structor repo at `/Users/emilielundbyedalsgaard/Repositories/structor` — read-only
  reference for canvas port

## Out of scope (V1)

- Rename detection (source col `SUBJID` → target col `usubjid`): requires
  column-level lineage tracking through generated Python code
- Interactive edge creation in the ERD (user drawing FK relationships by dragging)
- Mermaid export (structor has this; add in V2)
- Column-level lineage (which source column feeds which target column)
- Schema approval workflow per table
