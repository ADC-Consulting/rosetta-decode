# F3 — Proposed Status + Plan Interaction UX

**Phase:** 2
**Area:** Worker / Backend / Frontend
**Status:** complete
**Branch:** feat/F2-agentic-workflow

## Goal

Replace the current binary `done` status with a human-in-the-loop review cycle:
once the worker finishes, jobs are `proposed` (machine done, awaiting human review).
The Plan tab becomes an interactive review surface where the user can see the
reconciliation result, accept the migration, or annotate/override individual blocks.
`done` is retired — `proposed` and `accepted` replace it.

Done looks like: worker writes `proposed`; Plan tab shows a reconciliation summary
card + "Accept migration" CTA; user can edit per-block strategy/risk and add notes;
accepting the job writes `accepted` + timestamps in `user_overrides`; `make test`
exits 0.

---

## Status model

| Status | Meaning |
|---|---|
| `queued` | Waiting to run |
| `running` | Worker executing |
| `proposed` | Worker done — awaiting human review |
| `accepted` | Human reviewed and accepted |
| `failed` | Worker error |

`done` is **removed**. Existing `done` rows in the DB are migrated → `accepted`
(they were implicitly accepted by the absence of a review step).

---

## Subtasks

### T-1: Alembic migration 008 — rename done→accepted in existing rows
**File:** `alembic/versions/008_rename_done_to_accepted.py`
**Depends on:** none
**Done when:** migration runs; existing `done` rows become `accepted`; no schema change needed (status is TEXT).

SQL: `UPDATE jobs SET status = 'accepted' WHERE status = 'done';`

- [x] done

---

### T-2: ORM + worker — write `proposed` instead of `done`
**Files:** `src/backend/db/models.py` (comment only, no schema change), `src/worker/main.py`
**Depends on:** T-1
**Done when:** `JobOrchestrator._execute()` writes `status="proposed"` in both persist calls; existing `status="done"` strings removed from worker.

- [x] done

---

### T-3: Backend schemas + two new routes
**Files:** `src/backend/api/schemas.py`, `src/backend/api/routes/jobs.py`
**Depends on:** T-2
**Done when:** `POST /jobs/{id}/accept` writes `status="accepted"` + stores `user_overrides`; `PATCH /jobs/{id}/plan` persists per-block overrides; both return 200 with updated job summary.

New schemas:
```python
class AcceptJobRequest(BaseModel):
    notes: str | None = None   # optional top-level acceptance note

class BlockOverride(BaseModel):
    block_id: str
    strategy: str | None = None   # override agent strategy
    risk: str | None = None       # override agent risk
    note: str | None = None       # reviewer annotation

class PatchPlanRequest(BaseModel):
    block_overrides: list[BlockOverride] = []
```

New columns on Job ORM: `user_overrides: JSON | None`, `accepted_at: DateTime | None`
(added in same migration 008).

Routes:
- `POST /jobs/{job_id}/accept` — sets `status="accepted"`, `accepted_at=now()`, persists `AcceptJobRequest.notes` into `user_overrides["acceptance_note"]`
- `PATCH /jobs/{job_id}/plan` — merges `PatchPlanRequest.block_overrides` into `user_overrides["block_overrides"]`; job must be in `proposed` or `accepted` state

- [x] done

---

### T-4: Backend tests for new routes
**Files:** `tests/test_api_routes.py` (extend) or new `tests/test_plan_routes.py`
**Depends on:** T-3
**Done when:** accept endpoint and patch-plan endpoint each have ≥2 tests (happy path + bad state).

- [x] done

---

### T-5: Frontend types + API client functions
**Files:** `src/frontend/src/api/types.ts`, `src/frontend/src/api/jobs.ts`
**Depends on:** T-3
**Done when:**
- `JobStatusValue` extended with `"proposed" | "accepted"` (remove `"done"`)
- `UserOverride`, `BlockOverride`, `AcceptJobRequest`, `PatchPlanRequest` TS types added
- `acceptJob(jobId)` and `patchJobPlan(jobId, overrides)` API functions added

- [x] done

---

### T-6: Status labels + colors for proposed/accepted
**Files:** `src/frontend/src/pages/JobDetailPage.tsx` (`STATUS_LABEL`, `StatusBadge`, `STATUS_PILL_CLASS`), `src/frontend/src/pages/JobsPage.tsx` (`TableStatus`), `src/frontend/src/components/JobResult.tsx`, `src/frontend/src/pages/UploadPage.tsx`
**Depends on:** T-5
**Done when:** all status display components handle `proposed` (amber shimmer — "Under Review") and `accepted` (emerald, no shimmer — "Accepted"); `done` removed; polling continues for `queued | running | proposed` (proposed may auto-advance in future).

Status display:
- `queued` → grey shimmer "Queued"
- `running` → blue shimmer "Running"
- `proposed` → amber shimmer "Under Review" (slow, 4s)
- `accepted` → emerald static "Accepted"
- `failed` → red static "Failed"

- [x] done

---

### T-7: Plan tab — reconciliation summary card + Accept CTA
**File:** `src/frontend/src/pages/JobDetailPage.tsx` (PlanTab component)
**Depends on:** T-5, T-6
**Done when:** PlanTab shows:
1. Reconciliation summary card at top (pass/fail badge, check count, diff_summary if failed) — derived from `job.report`
2. "Accept migration" primary button (only when `status === "proposed"`) — calls `acceptJob()`; on success invalidates job query
3. `isDone` gate replaced with `isProposed || isAccepted` gate so Plan tab is accessible in both states

- [x] done

---

### T-8: Plan tab — inline block overrides + notes
**File:** `src/frontend/src/pages/JobDetailPage.tsx` (PlanTab block table)
**Depends on:** T-7
**Done when:** each block row in the plan table has:
- Inline `<select>` for strategy (translate/stub/skip) — pre-filled with agent value; user changes auto-save via `patchJobPlan()` with 500ms debounce
- Inline `<select>` for risk (low/medium/high)
- Inline `<input type="text">` for note
- Pending save state shown as "Saving…" on row
- Only editable when `status === "proposed"` (read-only when `accepted`)

- [x] done

---

### T-9: Update POLLING_STATUSES everywhere
**Files:** All files that reference `POLLING_STATUSES` or check `status === "done"`
**Depends on:** T-5
**Done when:** polling includes `proposed`; `isDone` checks replaced with `isProposed || isAccepted`; `ReportTab` and `LineageTab` load for `proposed` and `accepted`; no stale `"done"` string literals remain.

- [x] done

---

## Files touched (expected)

| File | Change |
|---|---|
| `alembic/versions/008_rename_done_to_accepted.py` | New migration |
| `src/backend/db/models.py` | `user_overrides`, `accepted_at` columns |
| `src/backend/api/schemas.py` | New request/response schemas |
| `src/backend/api/routes/jobs.py` | Two new routes |
| `src/worker/main.py` | `"done"` → `"proposed"` |
| `src/frontend/src/api/types.ts` | Status type, new interfaces |
| `src/frontend/src/api/jobs.ts` | `acceptJob`, `patchJobPlan` |
| `src/frontend/src/pages/JobDetailPage.tsx` | PlanTab overhaul |
| `src/frontend/src/pages/JobsPage.tsx` | `TableStatus` new statuses |
| `src/frontend/src/components/JobResult.tsx` | Status labels |
| `src/frontend/src/pages/UploadPage.tsx` | Status labels |

## Decisions

- `done` removed from status enum; existing `done` rows migrated to `accepted` (008 migration)
- `proposed` polls at same interval as `running` — future: auto-accept after N days
- `user_overrides` is a free-form JSON blob on the Job row; no separate table needed at this scale
- Block overrides are merged (not replaced) on each PATCH so concurrent edits don't clobber each other
