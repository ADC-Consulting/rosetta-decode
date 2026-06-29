# F80 — Data Storage tab Source / Migration sidebar toggle

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

The Data Storage tab sidebar currently mixes SAS source tables and migration output tables
in a single list, making it hard for users to distinguish what exists today in the SAS
project from what the migration will produce. This feature restructures the sidebar with a
**Source / Migration toggle** (matching the ETL tab's Source / Target pattern) so the two
concerns are clearly separated.

Intermediate ETL tables (produced and consumed mid-pipeline) remain visible in the
DataFlowDiagram as amber nodes — they have no schema to inspect, so they do not appear in
the sidebar. Clicking an intermediate node in the DataFlow diagram does not navigate the
sidebar; it shows nothing (the node is visual-only lineage information).

Done looks like:
- Source toggle shows SAS source tables grouped by libname, no "SAS: libname" redundancy
- Migration toggle shows output tables only, under an "Output" section header
- DataFlow and Data Model buttons switch to the full-screen diagram view (no change)
- Clicking a DataFlow output node auto-switches sidebar to Migration and selects the entry
- Clicking a DataFlow intermediate node does nothing (no sidebar entry exists)

## Acceptance Criteria

- [ ] Sidebar has a Source / Migration toggle strip matching ETL tab styling
- [ ] Source view groups tables by libname with the libname as a plain group header (no "SAS: libname" sub-label)
- [ ] Migration view shows output tables (`libname === null`) under an "Output" section
- [ ] Clicking an output node in the DataFlow diagram switches sidebar to Migration and selects the table
- [ ] Clicking an intermediate (amber) node in the DataFlow diagram produces no sidebar navigation
- [ ] Right panel content is unchanged for source and output tables
- [ ] `make test` exits 0

## Subtasks

### S-A: Source / Target toggle state + sidebar restructure
**File:** `src/frontend/src/components/JobDetail/DataStorageTab.tsx`
**Depends on:** none
**Done when:** `sidebarView: "source" | "target"` state added; Source view renders the existing libname-grouped table list with plain libname group headers + table count badge; Target view renders output tables under "Output" section; toggle strip with context subtitle matches ETL tab styling; selection persists per view.
- [x] done

### S-B: DataFlow node click routing
**File:** `src/frontend/src/components/JobDetail/DataStorageTab.tsx`
**Depends on:** S-A
**Done when:** `onTableSelect` callback passed to `DataFlowDiagram` switches `sidebarView` to `"target"` before setting `selectedPath`; intermediate node clicks silently ignored.
- [x] done

### S-C: `make test` exits 0
**File:** n/a
**Depends on:** S-A, S-B
**Done when:** `make test` exits 0 with all 7 gates green.
- [x] done

## Dependencies on other features

- none

## Out of scope for this feature

- Intermediate tables in the sidebar (no reliable schema; DataFlowDiagram amber nodes are sufficient)
- Intermediate table schema capture in the worker (deferred — revisit if remote executor path becomes available)
- Changes to the right panel content (source table view, output table diff view, DDL collapsible — all unchanged)
- ERD (Data Model view) changes
- Libname rename (Settings gear) — stays in Source view on the group header
