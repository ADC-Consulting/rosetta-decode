# F23 — Plan tab PM-readability pass

**Phase:** 2
**Area:** Frontend
**Status:** complete

## Goal

The Plan tab after F22 surfaces correct data but leaves a PM unable to make a confident accept/reject decision: "Risk: Medium" contradicts the green verdict, "Confidence 86%" is uninterpretable, the reference data in the verification sentence is unexplained, accepting has no stated consequence, there is no output scope, and the Blocks table auto-expands to fill the screen with developer content. This feature fixes all six gaps with changes to a single file — no backend work needed.

Done looks like: a PM opening the Plan tab sees the verdict, understands what the metrics mean (tooltip on hover), knows what the pipeline produces, understands what accepting does, and can reach the Accept button with full context.

## Acceptance Criteria

- [x] "Confidence" and "Complexity" bar labels have `cursor-help` tooltips explaining what each metric measures and directing the PM to reconciliation results as the stronger signal
- [x] "Risk" label replaced with "Complexity" everywhere in the plan card stats row
- [x] Green recommendation detail explains reference data and acceptance consequence
- [x] Amber and red detail texts updated to plain-English consequence descriptions
- [x] "Produces" row renders below the summary when `assessmentData.output_datasets` is non-empty
- [x] Blocks default to collapsed in all states (auto-expand removed)
- [x] `make test` exits 0

## Subtasks

### S-A: Rename "Risk" → "Complexity" + tooltip on both metric bar labels
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** "Risk" label is "Complexity" in the stats row; both bar labels are wrapped in `<Tooltip>` with plain-English copy; `planData.risk_explanation` appended to Complexity tooltip when non-empty.
- [x] done

---

### S-B: Rewrite recommendation strip detail texts
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** All three `detail` strings explain the reference data and/or acceptance consequence.
- [x] done

---

### S-C: Add "Produces" output scope row
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** A new card row between summary and callouts shows `assessmentData.output_datasets` joined by ", "; omitted when empty or null.
- [x] done

---

### S-D: Revert Blocks auto-expand
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** `blocksCollapsedManual`/`isGreen` derived state removed; replaced with `useState(true)`; toggle handler simplified.
- [x] done

---

### S-E: `make test` exits 0
**Depends on:** S-A, S-B, S-C, S-D
**Done when:** `make test` green — no tsc, eslint, ruff, or mypy errors.
- [x] done

## Dependencies on other features

- F22 (complete) — plan card structure, AttentionBlocksSummary, recommendation strip, and all data queries already in place

## Out of scope for this feature

- Backend changes
- Renaming "Risk" in the Blocks table (developer-facing, accurate there)
- Linking output dataset names to lineage graph nodes
