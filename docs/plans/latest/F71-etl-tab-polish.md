# F71 — ETL Tab Polish

**Phase:** 4
**Area:** Frontend
**Status:** complete

## Goal

Polish the ETL tab following the F70 Target sub-views implementation. Six targeted fixes address
dead-end interactions, navigation clarity, and information ambiguity identified in a post-F70
review. No new backend endpoints or data model changes required — all changes are in the frontend
ETL tab component tree.

## Acceptance Criteria

- [x] Clicking a SAS step card in the bridge view opens PipelineStepPanel (same as Source Pipeline)
- [x] Bridge view step cards show a step number badge (#1, #2, …)
- [x] Trust stat counters in the summary bar are labelled "blocks:" to avoid ambiguity in Target view
- [x] BlockDetailPanel back link is visually prominent and reads as a breadcrumb
- [x] `make test` exits 0
- [x] ruff and mypy pass

## Subtasks

### S01: Wire bridge step clicks to PipelineStepPanel
**File:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** none
**Done when:** clicking an amber SAS step card in the bridge view calls `onPipelineStepClick` with
the matching `PipelineStep` object, opening the same step detail panel that Source Pipeline view
uses. Requires adding `onPipelineStepClick?: (step: PipelineStep) => void` prop to `TargetGraph`
and `TargetGraphInner`, passing it through from ETLTab, and adding a click branch for
`bridgeStepNode` in `handleNodeClick`.
- [x] done

### S02: Step number badge on bridge step cards
**File:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** none
**Done when:** `BridgeStepNodeData` includes `stepNumber: number` (1-based index from the
`pipelineSteps` array position), and `BridgeStepNode` renders it as a small badge in the
top-right corner of the card — e.g. `#3` in a muted rounded pill.
- [x] done

### S03: Label trust stats "blocks:" in summary bar
**File:** `src/frontend/src/components/JobDetail/ETLTab.tsx`
**Depends on:** none
**Done when:** the three trust stat spans (✓ verified, ⚠ review, ✗ manual) are prefixed with a
`blocks:` label so they read "blocks: ✓ N ⚠ N ✗ N", making clear these counts refer to SAS
block analysis regardless of which view (Source/Target) is active.
- [x] done

### S04: Promote BlockDetailPanel back link to breadcrumb
**File:** `src/frontend/src/components/JobDetail/BlockDetailPanel.tsx`
**Depends on:** none
**Done when:** the `← {parentPyFile}` back link at the top of BlockDetailPanel is styled
prominently enough to read as a breadcrumb — larger font weight, visible chevron, and a clear
visual separation from the panel body — so users understand their navigation depth without a
full breadcrumb bar.
- [x] done

### S05: run `make test` and confirm green
**File:** n/a
**Depends on:** S01, S02, S03, S04
**Done when:** all seven gates pass (ruff-check, ruff-format, mypy, pytest+coverage, tsc,
frontend-lint, frontend-build).
- [x] done

## Out of scope for this feature

- Merging Target Blocks view into Target Files (deferred — the inline block rows provide
  a useful overview; decision to merge or keep as separate views needs a UX review session)
- Source/Target toggle state preservation (deferred — the reset-on-toggle is intentional to
  avoid stale cross-view panel state; a smarter mapping would require SAS↔Python file
  correlation that may not always be 1:1)
- Any backend changes

## Dependencies on other features

- F70 (Target ETL sub-views) — complete; bridge view and panel components are in place
