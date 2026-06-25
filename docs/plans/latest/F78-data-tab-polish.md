# F78 — Data Storage Tab Polish

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

Five targeted polish items for the Data Storage tab that were identified after F35/F43 merged.
All changes are frontend-only. Done looks like: diagrams fit their viewport on first load,
step node labels are fully readable, step nodes show an informative hover tooltip, table status
dots distinguish migrated/not-run states, and the output table header uses a proper badge.

## Acceptance Criteria

- [ ] DataFlowDiagram fits all nodes in viewport on initial render without manual zoom
- [ ] ERD (SchemaCanvas) fits all nodes in viewport on initial render without manual zoom
- [ ] Data flow step node labels are not truncated for typical names (<= 30 chars)
- [ ] Hovering a step node shows a tooltip with the full step name, input datasets, and output datasets
- [ ] Sidebar MIGRATION OUTPUT table dots are green for migrated tables, gray for not-run
- [ ] Output table header "Not run" label uses a coloured badge consistent with other badges in the app
- [ ] `make test` exits 0
- [ ] ruff and mypy pass (no Python changes, but gate must stay green)

## Subtasks

### S-A: fitView on DataFlowDiagram initial render
**File:** `src/frontend/src/components/JobDetail/DataFlowDiagram.tsx`
**Depends on:** none
**Done when:** The `<ReactFlow>` component receives `fitView` prop so nodes fill the viewport on first paint without any manual action.
- [x] done

### S-B: Step node label truncation fix + hover tooltip
**File:** `src/frontend/src/components/JobDetail/DataFlowDiagram.tsx`
**Depends on:** none
**Done when:** `STEP_W` is widened from 180 to 240; `FlowNodeData` gains `inputs?: string[]` and `outputs?: string[]`; graph builder populates them; `StepNode` renders a shadcn `Tooltip` on hover showing the full step name, "Reads: …", and "Produces: …" lines.
- [x] done

### S-C: fitView on DataModelERD (SchemaCanvas) initial render
**File:** `src/frontend/src/components/SchemaCanvas/SchemaCanvas.tsx`
**Depends on:** none
**Done when:** The existing `useEffect(fitToView, [])` is extended with a `ResizeObserver` fallback so that when `viewport.clientWidth === 0` on the first tick the fit fires again as soon as the element receives real dimensions.
- [x] done

### S-D: Sidebar status dots distinguish migrated vs not-run
**File:** `src/frontend/src/components/JobDetail/DataStorageTab.tsx`
**Depends on:** none
**Done when:** `statusDotClass()` explicitly maps `"migrated"` → `bg-green-500`, `"changed"` → `bg-amber-400`, `"not_run"` → `bg-muted-foreground/30`; the SOURCE DATA section dot is styled identically so both sections are consistent; no other behaviour changes.
- [x] done

### S-E: Replace "Not run" plain text with a coloured badge
**File:** `src/frontend/src/components/JobDetail/DataStorageTab.tsx`
**Depends on:** none
**Done when:** The output table header schema-status label uses a `<Badge>` with variant and colour consistent with the existing `schema_status` badge elsewhere in the app (`migrated` → green, `changed` → amber, `not_run` → muted secondary), replacing the current plain-text `"Not run"`.
- [x] done

### S-F: make test exits 0
**File:** n/a (gate)
**Depends on:** S-A, S-B, S-C, S-D, S-E
**Done when:** `make test` exits 0 with all 7 gates green.
- [x] done

## Dependencies on other features

- none (all changes are isolated to existing DataFlowDiagram, SchemaCanvas, and DataStorageTab components)

## Out of scope for this feature

- Cross-tab navigation from step nodes to ETLTab (decided in session 2026-06-24: tooltip is the right interaction, not navigation)
- Updating backend `schema_status` values (status dots use existing API field; no backend changes)
- MS SQL Server DDL dialect (separate backlog item)
- Any ERD layout or node style changes beyond fitView
