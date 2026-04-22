# F4 — Graded Confidence-Aware Translation Flow with Refine Loop & Change History

**Status:** in-progress  
**Branch:** feat/F4-confidence-refine-history  
**Created:** 2026-04-21

---

## Goal

Move from binary "translate vs manual" to a graded, confidence-aware translation flow with a real per-block refine loop and full append-only change history surfaced to the client.

---

## Subtasks

- [x] S1 — Fix confidence capture in translation agents
- [x] S2 — Planner-driven routing
- [x] S3 — Reconciliation overrides confidence + risk propagation
- [x] S4 — Block-level revision table (DB migration)
- [x] S5 — Block-level refine + revision API endpoints
- [x] S6 — Job-level changelog API
- [x] S7 — Tiered trust report API
- [x] S8 — Frontend types + API client
- [x] S9 — Frontend: PlanTab prioritized review queue
- [x] S10 — Frontend: per-block refine dialog + revision history drawer
- [x] S11 — Frontend: TrustReportTab + ChangelogFeed
- [ ] S12 — Tests (backend) — unit tests added per subtask; reconciliation integration tests deferred

---

## Subtask Detail

### S1 — Fix confidence capture in translation agents (backend-only)
Add `confidence: str` and `uncertainty_notes: list[str]` to `DataStepResult` and `ProcResult`. Update agent system prompts to always return these fields. Update `DataStepAgent.translate()` and `ProcAgent.translate()` to pass through to `GeneratedBlock`.

**Files:** `src/worker/engine/agents/data_step.py`, `src/worker/engine/agents/proc.py`

---

### S2 — Planner-driven routing (backend-only)
Update `TranslationRouter.route()` to accept optional `block_plan: BlockPlan | None`. Use `block_plan.strategy` to modulate routing:
- `translate` → current path
- `translate_with_review` → current path + cap `confidence` at "medium"
- `translate_best_effort` → current path + set `confidence="low"`, add uncertainty note
- `manual` / `manual_ingestion` → route to stub (no LLM), flag for manual
- `skip` → emit empty stub

Pass block_plan lookup into `_translate_blocks()` in orchestrator.

**Files:** `src/worker/engine/router.py`, `src/worker/main.py`

---

### S3 — Reconciliation overrides confidence + risk propagation (backend-only)
After final reconciliation in `_execute()`:
- For each `GeneratedBlock`: if block_id in `report.affected_block_ids` → set `verified_confidence="verified_low"` + add failure note
- If reconciliation passed → set `verified_confidence="verified_high"` for `translate_with_review` blocks
- Risk propagation: mark downstream blocks (via `enriched_lineage.cross_file_edges`) as at most `confidence="low"` with note "downstream of failed block X"
- Add `verified_confidence: str | None = None` field to `GeneratedBlock`

**Files:** `src/worker/engine/models.py`, `src/worker/main.py`

---

### S4 — Block-level revision table (backend + DB migration)
New `block_revisions` table:
- `id` UUID PK
- `job_id` FK → jobs (cascade delete)
- `block_id` str — basename-only format `"file.sas:12"`
- `revision_number` int (1-based, per block_id within job chain)
- `python_code` text
- `strategy` str
- `confidence` str
- `uncertainty_notes` JSON
- `reconciliation_status` str nullable ("pass"/"fail")
- `trigger` str ("agent"/"human-refine"/"auto-retry")
- `notes` text nullable — verbatim user instructions that drove this revision
- `hint` text nullable — auto-generated structured hint (secondary)
- `diff_vs_previous` text nullable — unified diff vs previous revision's python_code
- `created_at` datetime

Next Alembic migration number after existing ones.

**Files:** `src/backend/db/models.py`, `alembic/versions/NNN_add_block_revisions.py`

---

### S5 — Block-level refine + revision API (backend-only)
New endpoints:

**`POST /jobs/{job_id}/blocks/{block_id}/refine`**
- Request: `{ "notes": str | None, "hint": str | None }` — `notes` is primary (user instructions, injected first into LLM prompt); `hint` is secondary
- Guard: 409 Conflict if `job.accepted_at IS NOT NULL`
- Re-translates that block only; assembles full output; re-runs reconciliation
- Inserts `block_revision` with `diff_vs_previous` computed via `difflib.unified_diff`
- Response: `{ "block_id", "revision_number", "confidence", "reconciliation_status" }`

**`GET /jobs/{job_id}/blocks/{block_id}/revisions`**
- Returns full revision history newest-first

**`POST /jobs/{job_id}/blocks/{block_id}/revisions/{revision_id}/restore`**
- Restores prior revision's `python_code` into the assembled output

Also patch existing **`POST /jobs/{job_id}/refine`** (whole-job): add 409 guard for `accepted_at IS NOT NULL`.

**Files:** `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py`

---

### S6 — Job-level changelog API (backend-only)
**`GET /jobs/{job_id}/changelog`**
- All block revisions across all blocks for this job, newest-first
- Fields: block_id, revision_number, trigger, strategy, confidence, reconciliation_status, created_at, notes, hint, diff_vs_previous

**Files:** `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py`

---

### S7 — Tiered trust report API (backend-only)
**`GET /jobs/{job_id}/trust-report`**
- Project-level: overall_confidence (weighted avg), total_blocks, auto_verified, needs_review, manual_todo, failed_reconciliation counts, `lineage_available: bool`
- File-level: per source_file same metrics
- Block-level: strategy, self_confidence, verified_confidence, reconciliation_status, needs_attention, blast_radius (null if no lineage)
- Review queue: blocks sorted by (reconciliation_fail DESC, confidence ASC, blast_radius DESC, estimated_effort ASC)

**Files:** `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py`

---

### S8 — Frontend types + API client (frontend-only)
New TS interfaces: `BlockRevision`, `BlockRevisionHistory`, `JobChangelog`, `TrustReport`, `TrustReportBlock`, `BlockRefineRequest`, `BlockRefineResponse`

New API functions: `refineBlock()`, `getBlockRevisions()`, `restoreBlockRevision()`, `getJobChangelog()`, `getJobTrustReport()`

**Files:** `src/frontend/src/api/types.ts`, `src/frontend/src/api/jobs.ts`

---

### S9 — Frontend: PlanTab prioritized review queue (frontend-only)
- Replace flat `BlockPlanTable` with review queue sorted by needs_attention
- Add columns: self_confidence badge, verified_confidence badge, reconciliation status (pass/fail/unknown), blast_radius indicator

**Files:** `src/frontend/src/components/JobDetail/PlanTab.tsx`, `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`

---

### S10 — Frontend: per-block refine dialog + revision history (frontend-only)
- Refine button per row in BlockPlanTable (hidden/disabled if `accepted_at` set)
- `BlockRefineDialog`: notes textarea (primary, pre-filled from existing block note) + hint field (secondary)
- `BlockRevisionDrawer`: revision list with trigger icon (robot=agent, person=human), confidence, recon status, diff toggle, Restore button
- Submit → `POST /jobs/{job_id}/blocks/{block_id}/refine`

**Files:** `src/frontend/src/components/JobDetail/PlanTab.tsx`, `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`, new `BlockRevisionDrawer.tsx`, new `BlockRefineDialog.tsx`

---

### S11 — Frontend: TrustReportTab + ChangelogFeed (frontend-only)
- New "Trust Report" tab in JobDetailPage
- Summary cards: auto-verified / needs-review / manual-todo
- Prioritized review queue table
- Changelog feed: block_id, trigger icon, confidence, recon badge, notes/hint, diff expand

**Files:** new `src/frontend/src/components/JobDetail/TrustReportTab.tsx`, new `src/frontend/src/components/JobDetail/ChangelogFeed.tsx`, `src/frontend/src/pages/JobDetailPage.tsx`

---

### S12 — Tests (backend)
- Unit: confidence capture in DataStepAgent, ProcAgent
- Unit: planner-driven routing (strategy → translator)
- Unit: confidence override from reconciliation
- Unit: risk propagation for downstream blocks
- Integration: block-level refine endpoint (mock LLM)
- Integration: trust report endpoint (mock data)

**Files:** `tests/test_data_step_agent.py`, `tests/test_proc_agent.py`, `tests/test_translation_router.py`, new `tests/test_block_revisions.py`, new `tests/test_trust_report.py`

---

## Interface Contracts

| Decision | Resolution |
|---|---|
| block_id format | Basename-only `"etl.sas:12"`. Client `encodeURIComponent()` before URL use. |
| Per-block reconciliation | Reassemble flat code with substituted block, re-run full reconciliation, populate `affected_block_ids`. No new interface needed. |
| Initial block_revision rows | Created **only on explicit refine**. Revision 1 = prior code, revision 2 = new code. Initial output captured by `job_versions[editor]`. |
| Trust report + missing lineage | 200 with `blast_radius: null` + `lineage_available: false`. No 202. |
| Accepted job guard | 409 Conflict for both whole-job and block-level refine when `accepted_at IS NOT NULL`. |
| diff_vs_previous | Computed in FastAPI route handler via `difflib.unified_diff`. |
| Refine UI placement | PlanTab block row "Refine" button. Notes = primary (user instructions). Hint = secondary. EditorTab read-only in V1. |
| TrustReport sequencing | 200 immediately after `status="done"`. Relies on existing status polling. |

---

## Files to Create/Modify

| File | Change |
|---|---|
| `src/worker/engine/models.py` | `verified_confidence` on GeneratedBlock; `confidence`/`uncertainty_notes` on DataStepResult/ProcResult |
| `src/worker/engine/agents/data_step.py` | Capture confidence + uncertainty_notes |
| `src/worker/engine/agents/proc.py` | Capture confidence + uncertainty_notes |
| `src/worker/engine/router.py` | Planner-driven routing |
| `src/worker/main.py` | Block plans → router; post-reconcile confidence override; risk propagation |
| `src/backend/db/models.py` | `BlockRevision` ORM model |
| `alembic/versions/NNN_add_block_revisions.py` | DB migration |
| `src/backend/api/schemas.py` | New response/request schemas |
| `src/backend/api/routes/jobs.py` | 5 new endpoints + 409 patch on existing refine |
| `src/frontend/src/api/types.ts` | New TS types |
| `src/frontend/src/api/jobs.ts` | New API functions |
| `src/frontend/src/components/JobDetail/PlanTab.tsx` | Prioritized queue + Refine button wiring |
| `src/frontend/src/components/JobDetail/BlockPlanTable.tsx` | Confidence + recon columns |
| `src/frontend/src/components/JobDetail/BlockRefineDialog.tsx` | New |
| `src/frontend/src/components/JobDetail/BlockRevisionDrawer.tsx` | New |
| `src/frontend/src/components/JobDetail/TrustReportTab.tsx` | New |
| `src/frontend/src/components/JobDetail/ChangelogFeed.tsx` | New |
| `src/frontend/src/pages/JobDetailPage.tsx` | Add Trust Report tab |
