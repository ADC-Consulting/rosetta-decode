# F28 — 5-tab Chevron Shell Scaffold

**Phase:** 3
**Area:** Frontend
**Status:** in-progress

## Goal

Replace the current tab bar in `JobDetailPage` (Plan / Editor / Report / Lineage / Evaluation) with a 5-tab chevron-style pipeline shell keyed to migration stages: Plan → ETL → Data Storage → BI → AI. Existing components are redistributed into the new tab slots. URL routing is synced on every tab change. The chevron visual shape is implemented now using CSS clip-path — final colour, sizing, and spacing will be tuned when the wireframe is attached to issue #40. Legacy tab bar is hidden, not deleted (#46).

## Acceptance Criteria

- [ ] ChevronTabBar renders with 5 steps: Plan, ETL, Data Storage, BI, AI
- [ ] Active, visited, and unvisited states are visually distinct
- [ ] URL reflects active tab on every change; direct linking to a tab works
- [ ] `plan` tab shows PlanTab + EvaluationTab
- [ ] `etl` tab shows EditorTab + LineageTab
- [ ] `data-storage`, `bi`, `ai` tabs show a placeholder empty state
- [ ] Legacy TabsList is hidden (not deleted)
- [ ] `make test` exits 0
- [ ] ruff and mypy pass (no backend changes — frontend tsc + lint only)

## Subtasks

### S-A: URL-synced routing + new tab keys
**File:** `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** none
**Done when:** `setSearchParams({ tab: v })` is called on every tab change; old tab key references (`editor`, `report`, `lineage`, `evaluation`) replaced with new keys (`etl`, `data-storage`, `bi`, `ai`) throughout; `saveVersionMutation` branching updated to match new keys

- [ ] done

### S-B: ChevronTabBar component
**File:** `src/frontend/src/components/JobDetail/ChevronTabBar.tsx`
**Depends on:** S-A
**Done when:** component renders 5 `TabsTrigger` items inside a `TabsList` with chevron arrow shapes via CSS clip-path; active tab uses primary fill, visited uses muted, unvisited uses grey; component slots into `JobDetailPage` in place of the old `TabsList`

- [ ] done

### S-C: Wire existing components into new tab slots
**File:** `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** S-A, S-B
**Done when:**
- `plan` `TabsContent` renders PlanTab followed by EvaluationTab
- `etl` `TabsContent` renders EditorTab (top) and LineageTab (below) in a flex-col layout
- `data-storage`, `bi`, `ai` each render a centred placeholder ("Coming soon")
- ReportTab is commented out (restored in #41)
- Old `TabsList` is commented out

- [ ] done

### S-D: `make test` exits 0
**Depends on:** S-A, S-B, S-C
**Done when:** tsc, ESLint, frontend build, and pytest all pass with exit code 0

- [ ] done

## Dependencies on other features

- F25 (EvaluationTab), F26 (BlockPlanTable Criticality column) — both complete; components available
- #41 (Plan tab content refinement) — depends on this feature + wireframe
- #42 (ETL tab slide-in panel) — depends on this feature + wireframe

## Out of scope for this feature

- Chevron final sizing, colour palette, and spacing (wireframe will specify)
- Plan tab content merge — collapsible Report + History panels (#41)
- ETL tab slide-in panel — Lineage as primary canvas, Editor as click-through (#42)
- Data Storage tab content (#43)
- Legacy component deletion (#46)
