# F26 — Criticality Column on Plan Tab Block Table

**Phase:** 3
**Area:** Frontend
**Status:** in-progress

## Goal

Surface the `criticality` value (computed by F25 and present in `trustBlocks`) as a badge in the `BlockPlanTable` block rows, so users can see criticality on the Plan tab without switching to the Evaluation tab. No backend change required — `PlanTab` already fetches the trust report and passes `trustBlocks: Record<string, TrustReportBlock>` into `BlockPlanTable`.

## Acceptance Criteria

- [ ] Each row in the Plan tab block table shows a Criticality badge (`critical` / `high` / `normal` / `low`) using the same colour palette as `EvaluationTab`
- [ ] Badge renders `—` when `trustBlocks` has no entry for the block (trust report not yet loaded)
- [ ] `make test` exits 0
- [ ] ruff and mypy pass

## Subtasks

### S-A: Add Criticality column to `BlockPlanTable`
**File:** `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
**Depends on:** none
**Done when:** table header has a `Criticality` column; each row reads `trust?.criticality` and renders a coloured badge (or `—` if absent), positioned between Risk and Confidence
- [ ] done

### S-B: `make test` exits 0
**Depends on:** S-A
**Done when:** ruff, mypy, tsc, frontend-lint, frontend-build all pass
- [ ] done

## Dependencies on other features

- F25 — `criticality` field on `TrustReportBlock` (merged on this branch)

## Out of scope for this feature

- Criticality on the Evaluation tab (already done in F25)
- Criticality stored in DB
- Sorting the Plan tab table by criticality
