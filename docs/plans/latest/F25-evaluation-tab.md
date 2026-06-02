# F25 — Evaluation Tab

**Phase:** 3
**Area:** Both (Backend / API + Frontend)
**Status:** complete

## Goal

Add an "Evaluation" tab to `JobDetailPage` that shows, per translated block, the confidence score, a derived criticality rating, and whether human review is required. Includes a summary section (% auto-OK vs requiring review, top-N risky blocks) and a help info dialog explaining the confidence metric. The backend already exposes all necessary data via `GET /jobs/{id}/trust-report`; this feature adds a `criticality` field to that response, fixes the broken `_blast_radius_map` helper (it currently reads a non-existent `source_file` key — cross_file_edges dicts actually use `source_block_id`), and wires the existing (commented-out) `TrustReportTab` into the UI as the new Evaluation tab.

**Data model notes confirmed during planning:**
- `cross_file_edges` in `job.lineage` has dicts with keys `source_block_id`, `target_block_id`, `shared_dataset` — NOT `source_file`
- `BlockPlan` (from `job.migration_plan`) has no `output_datasets`; block-level blast radius is derived directly from cross_file_edges via `source_block_id`
- `_blast_radius_map` currently always returns an empty map (reads wrong key) — all blocks have `blast_radius = None` until fixed

## Acceptance Criteria

- [x] `GET /jobs/{id}/trust-report` response includes `criticality` (`critical` | `high` | `normal` | `low`) and `human_review_required` (bool) on every block
- [x] Criticality is computed from `effective_confidence_band` + `blast_radius` + `strategy` — no DB migration required
- [x] Evaluation tab is visible in `JobDetailPage` for jobs in a reviewable state
- [x] Tab shows: confidence % per block, criticality badge, human-review-required indicator, recon status
- [x] Summary section shows: % auto-OK, % requiring review, top-N risky blocks (sorted by criticality DESC)
- [x] Help link in tab header opens or links to `docs/confidence-metric.md` content
- [x] `make test` exits 0
- [x] ruff and mypy pass

## Subtasks

### S-A: Add `criticality` and `human_review_required` to `TrustReportBlock` schema
**File:** `src/backend/api/schemas.py`
**Depends on:** none
**Done when:** `TrustReportBlock` has `criticality: str = "normal"` and `human_review_required: bool = False` with defaults for backward compatibility
- [x] done

### S-B: Fix `_blast_radius_map` and compute criticality in the trust report route
**File:** `src/backend/api/routes/jobs.py`
**Depends on:** S-A
**Done when:** `_blast_radius_map` uses `source_block_id` as map key (fixes existing bug); `_criticality()` helper exists near `_effective_confidence()`; every `TrustReportBlock` constructed in `get_job_trust_report` sets both new fields using the logic below

**Bug fix:** Change `_blast_radius_map` to key on `source_block_id` instead of `source_file`. The trust report route already passes `block_id` as `plan.block_id` — use that to look up count from the fixed map. Result: `blast_radius` will now be an integer (0 or more) instead of always `None`.

Criticality rules (applied after `effective_confidence_band` is known):
- `critical`: strategy == `"manual"` OR `effective_confidence_band == "very_low"`
- `high`: `effective_confidence_band == "low"` OR `reconciliation_status == "fail"` OR (`blast_radius` is not None AND `blast_radius >= 3`)
- `normal`: `effective_confidence_band == "medium"` OR `effective_confidence_band == "unknown"`
- `low`: `effective_confidence_band == "high"`

`human_review_required = criticality in ("critical", "high")`
- [x] done

### S-C: Tests for criticality computation
**File:** `tests/test_changelog_trust_report.py`
**Depends on:** S-B
**Done when:** test cases assert correct `criticality` and `human_review_required` values for: manual strategy block, very_low confidence block, high blast_radius block, pass+high block
- [x] done

### S-D: Update frontend `TrustReportBlock` type
**File:** `src/frontend/src/api/types.ts`
**Depends on:** S-C (backend must be green first)
**Done when:** `TrustReportBlock` interface has `criticality: "critical" | "high" | "normal" | "low"` and `human_review_required: boolean` as required fields
- [x] done

### S-E: Build `EvaluationTab` component (rename + extend `TrustReportTab`)
**File:** `src/frontend/src/components/JobDetail/EvaluationTab.tsx` (rename from `TrustReportTab.tsx`)
**Depends on:** S-D
**Done when:** component renders:
- Summary bar: overall confidence %, auto-verified count, needs-review count, manual-todo count
- Per-block table with columns: Block / File, Type, Strategy, Confidence %, Criticality badge, Human Review Required indicator, Recon status
- "Top risky blocks" section: `review_queue` sorted by criticality DESC then confidence_score ASC, max 10 rows
- Help icon (ℹ) in the tab section header that opens a `<Dialog>` containing the user-facing section of `docs/confidence-metric.md` verbatim — no new API route required, content is inlined as a string constant in the component
- `blast_radius` column only shown when `lineage_available === true` on the response
- [x] done

### S-F: Wire Evaluation tab into `JobDetailPage`
**File:** `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** S-E
**Done when:** `EvaluationTab` is imported (replacing commented-out `TrustReportTab` import), `TabsTrigger` with `value="evaluation"` is uncommented in position 5 (after Lineage, replacing the old `value="trust"` commented-out trigger), and `TabsContent` renders `<EvaluationTab jobId={id} />`

Tab order after this change: Plan → Editor → Report → Lineage → **Evaluation** → History (History remains commented out)
- [x] done

### S-G: `make test` exits 0
**Depends on:** S-F
**Done when:** full test suite passes; ruff and mypy clean
- [x] done

## Dependencies on other features

- `docs/confidence-metric.md` (PR #38) — already written; help link points to this content. Merge PR #38 before or alongside this feature.

## Out of scope for this feature

- Criticality score stored in DB — computed at read time only
- Editable criticality — read-only derived value
- Criticality on the Plan tab block table — that is a separate UI concern
- `F17` node-graph ETL pipeline view (separate feature, different issue)
- `F19` runbook for high-risk steps (follows naturally after this tab; separate plan)
