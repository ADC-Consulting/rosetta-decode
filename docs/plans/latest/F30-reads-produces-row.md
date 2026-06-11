# F30 — Reads/Produces Row on Plan Tab

**Phase:** 2
**Area:** Both (Backend / Worker + Frontend)
**Status:** in-progress
**GitHub issue:** #60

## Goal

Expose `input_datasets` and `output_datasets` per block via the plan API and render a "Reads → Produces" context line on the Plan tab. Data already exists in `SASBlock` at parse time — this feature threads it through to the API and frontend.

## Acceptance Criteria

- [ ] `BlockPlan` (worker model) carries `input_datasets` and `output_datasets`
- [ ] `_build_migration_plan()` copies both fields from the parsed `SASBlock`
- [ ] `BlockPlanResponse` (API schema) exposes both fields
- [ ] `BlockPlan` TypeScript interface updated
- [ ] Plan tab renders "Reads: X, Y" and "Produces: A, B" showing only external inputs and final outputs (internal intermediates filtered), with max 4 items shown + "N more" affordance
- [ ] Hidden entirely when both derived lists are empty (graceful empty state)
- [ ] `make test` exits 0

## Subtasks

### S-A: Add fields to BlockPlan worker model
**File:** `src/worker/engine/models.py`
**Depends on:** none
**Done when:** `BlockPlan` has `input_datasets: list[str] = Field(default_factory=list)` and `output_datasets: list[str] = Field(default_factory=list)`
- [ ] done

### S-B: Populate fields in _build_migration_plan()
**File:** `src/worker/engine/agents/migration_planner.py`
**Depends on:** S-A
**Done when:** `_build_migration_plan()` builds a `block_lookup: dict[str, SASBlock]` from the `blocks` argument and copies `input_datasets` and `output_datasets` onto each constructed `BlockPlan`
- [ ] done

### S-C: Add fields to BlockPlanResponse API schema
**File:** `src/backend/api/schemas.py`
**Depends on:** S-A
**Done when:** `BlockPlanResponse` has `input_datasets: list[str] = []` and `output_datasets: list[str] = []`
- [ ] done

### S-D: Update BlockPlan TypeScript type
**File:** `src/frontend/src/api/types.ts`
**Depends on:** S-C
**Done when:** `BlockPlan` interface has `input_datasets: string[]` and `output_datasets: string[]`
- [ ] done

### S-E: Render Reads/Produces row on Plan tab
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-D
**Done when:** A "Reads / Produces" line renders between the description paragraph and the verdict strip; aggregation logic: `allInputs = union(block.input_datasets)`, `allOutputs = union(block.output_datasets)`, `externalInputs = allInputs - allOutputs` (datasets read but never produced = true external sources), `finalOutputs = allOutputs - allInputs` (datasets produced but never consumed = final outputs); max 4 items shown per side with "+ N more" text if list is longer; section hidden entirely when both `externalInputs` and `finalOutputs` are empty after filtering (handles jobs where parser couldn't extract dataset names)
- [ ] done

### S-F: make test exits 0
**Depends on:** S-A through S-E
**Done when:** All 7 gates green
- [ ] done

## Known limitation

Existing jobs in the database do not have `input_datasets`/`output_datasets` in their stored `job.migration_plan` — they will show no Reads/Produces row. Only jobs migrated after this feature ships will have the data.

## Dependencies on other features

- F29 complete — Plan tab layout in place
- Merge before F31 and F32 — all three modify `models.py`, `schemas.py`, `types.ts`

## Out of scope

- Per-block Reads/Produces display in block table (job-level summary only)
- Lineage graph changes
