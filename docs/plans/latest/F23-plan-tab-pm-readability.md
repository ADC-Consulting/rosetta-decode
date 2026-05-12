# F23 — Plan tab PM-readability pass

**Phase:** 2
**Area:** Frontend
**Status:** complete (extended — see Phase 2 subtasks below)

## Goal

The Plan tab after F22 surfaces correct data but leaves a PM unable to make a confident accept/reject decision: "Risk: Medium" contradicts the green verdict, "Confidence 86%" is uninterpretable, the reference data in the verification sentence is unexplained, accepting has no stated consequence, there is no output scope, and the Blocks table auto-expands to fill the screen with developer content. This feature fixes all six gaps with changes to a single file — no backend work needed.

Done looks like: a PM opening the Plan tab sees the verdict, understands what the metrics mean (tooltip on hover), knows what the pipeline produces, understands what accepting does, and can reach the Accept button with full context.

## Acceptance Criteria (Phase 1)

- [x] "Confidence" and "Complexity" bar labels have `cursor-help` tooltips explaining what each metric measures and directing the PM to reconciliation results as the stronger signal
- [x] "Risk" label replaced with "Complexity" everywhere in the plan card stats row
- [x] Green recommendation detail explains reference data and acceptance consequence
- [x] Amber and red detail texts updated to plain-English consequence descriptions
- [x] "Produces" row renders below the summary when `assessmentData.output_datasets` is non-empty
- [x] Blocks default to collapsed in all states (auto-expand removed)
- [x] `make test` exits 0

## Acceptance Criteria (Phase 2 extension)

- [x] Scope summary line in card header: "{n} SAS files · {m} blocks · {k} output datasets"
- [x] Accept button moved to standalone bottom row; accepted state shows confirmation text
- [x] Stats row appears above assessment callouts
- [x] "Reads" row shows `assessmentData.input_sources`
- [x] Attention block cards show "Affects: X, Y" from `AssessedBlock.output_datasets`
- [x] Missing-deps warning elevated to distinct amber bordered card
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

## Phase 2 Subtasks

### S-F: Scope summary line in card header
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** Card header gains a secondary line showing SAS file count, block count, and output dataset count in muted text.
- [x] done

### S-G: Accept button moved to standalone bottom card row
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** Verdict strip is text-only; button is a full-width bottom row; accepted state shows confirmation text.
- [x] done

### S-H: Stats row moved above assessment callouts
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** Stats row (Confidence, Complexity, pills) appears before `<AssessmentCallouts>`.
- [x] done

### S-I: "Reads" input sources row
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** Reads row above Produces shows `assessmentData.input_sources`.
- [x] done

### S-J: Attention blocks "Affects" line
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** Each attention block card shows "Affects: X, Y" from `AssessedBlock.output_datasets`.
- [x] done

### S-K: Missing-deps elevated to amber card
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** Missing-deps warning renders as a distinct bordered amber card.
- [x] done

### S-L: `make test` exits 0
**Depends on:** S-F through S-K
- [x] done

## Out of scope for this feature

- Backend changes
- Renaming "Risk" in the Blocks table (developer-facing, accurate there)
- Linking output dataset names to lineage graph nodes
- `onViewLineage` wiring to tab navigation
