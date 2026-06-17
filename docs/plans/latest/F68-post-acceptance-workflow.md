# F68 — Post-acceptance workflow: export package, acceptance record, read-only delivered state

**Phase:** 2
**Area:** Both (Backend / API + Frontend)
**Status:** complete
**Issue:** #68
**Branch:** `feat/F68-post-acceptance-workflow`

## Goal

"Accept migration" currently only flips a status field and re-stamps `accepted_at` on
every call. This feature makes acceptance a real, immutable delivery event and turns
`GET /jobs/{id}/download` into a deployment-ready package. On accept: status →
`accepted`, `accepted_at` + new `accepted_by` ("anonymous" stub) written once and locked
(subsequent accepts rejected). The download produces a zip with `src/` (mirroring the SAS
tree), `requirements.txt`, `reconciliation_report.json`, `audit.json`, and
`migration_summary.md`. The UI shifts an accepted job into a read-only delivered mode: a
locked "Accepted" badge with timestamp, read-only editors, a prominent "Download migration
package" CTA, and an accepted treatment on the Plan-tab verdict strip. Done = all
acceptance criteria checked and `make test` exits 0.

## Acceptance Criteria

- [ ] `job.accepted_by` column added via Alembic migration `020` (chains from `019`); `accepted_at` already exists
- [ ] Accepting a job writes `accepted_at` + `accepted_by="anonymous"`; a second accept on an already-accepted job returns **409** (immutable, no re-stamp)
- [ ] `GET /jobs/{id}/download` returns a zip containing `src/` (all generated `.py` files, SAS tree structure), `requirements.txt`, `reconciliation_report.json`, `audit.json`, `migration_summary.md`
- [ ] `audit.json` contains: job id, input hash(es), LLM model, acceptance timestamp, accepting user, per-block verification status
- [ ] Post-acceptance UI: Accept button replaced by locked "Accepted" badge + timestamp; code editors read-only; prominent "Download migration package" CTA; verdict strip reflects accepted state
- [ ] `make test` exits 0
- [ ] ruff and mypy pass

## Subtasks

### S-A: Alembic migration 020 — add `accepted_by`
**File:** `alembic/versions/020_add_accepted_by.py`
**Depends on:** none
**Done when:** migration with `revision="020"`, `down_revision="019"` adds nullable `accepted_by` Text column to `jobs` (upgrade + downgrade).
- [x] done

### S-B: Job model — `accepted_by` column
**File:** `src/backend/db/models.py`
**Depends on:** S-A
**Done when:** `Job` has `accepted_by: Mapped[str | None]` (Text, nullable) alongside the existing `accepted_at`.
- [x] done

### S-C: Migration-package builder (pure function)
**File:** `src/backend/api/packaging.py` (new)
**Depends on:** S-B
**Done when:** `build_migration_package(job) -> bytes` returns a zip with:
- `src/<path>.py` for each entry in `job.generated_files` (keys are already SAS-tree-relative paths); falls back to a single `src/pipeline.py` from `job.python_code` when `generated_files` is empty
- `requirements.txt` from a deterministic dependency-inference helper (S-D)
- `reconciliation_report.json` ← `job.report`
- `audit.json` ← job id, `input_hash`, `llm_model`, `accepted_at`, `accepted_by`, and per-block verification status derived from `effective_migration_plan(job)` / `report`
- `migration_summary.md` ← `job.doc` or `report["non_technical_doc"]` (human-readable summary)
- [x] done

### S-D: Requirements inference helper
**File:** `src/backend/api/packaging.py`
**Depends on:** none
**Done when:** `infer_requirements(generated_code: str) -> list[str]` returns a deterministic, sorted requirements list by scanning generated code imports (pyspark vs pandas + common libs); reproducible for identical input.
- [x] done

### S-E: Rewrite `download_job` route to use the package builder
**File:** `src/backend/api/routes/jobs.py` (`download_job`, ~L360-408)
**Depends on:** S-C
**Done when:** route delegates to `build_migration_package(job)`; existing 404/409 status guards preserved; zip filename keeps job id + timestamp.
- [x] done

### S-F: Make acceptance immutable in `accept_job`
**File:** `src/backend/api/routes/jobs.py` (`accept_job`, ~L858-916)
**Depends on:** S-B
**Done when:** accepting writes `accepted_by="anonymous"` once; if `job.accepted_at` is already set, returns **409** (no re-stamp). Guard reworked so an already-`accepted` job cannot be re-accepted, while `proposed`/`under_review` still can.
- [x] done

### S-G: Backend tests — packaging, accept immutability, download contents
**File:** `tests/test_packaging.py` (new) + additions to existing jobs-route tests
**Depends on:** S-E, S-F
**Done when:** tests assert (1) zip contains all 5 members with correct content, (2) `infer_requirements` is deterministic, (3) second accept → 409, (4) first accept stamps both fields.
- [x] done

### S-H: Frontend API client + types
**File:** `src/frontend/src/api/jobs.ts`, `src/frontend/src/api/types.ts`
**Depends on:** S-F
**Done when:** `JobStatus`/job types expose `accepted_at` + `accepted_by`; `downloadJob` confirmed usable from detail page (already exists); `acceptJob` unchanged unless notes needed.
- [x] done

### S-I: Accepted-state header — locked badge + Download CTA
**File:** `src/frontend/src/pages/JobDetailPage.tsx` (~L224-246)
**Depends on:** S-H
**Done when:** when `status === "accepted"`, the Accept button is replaced by a locked "Accepted" badge showing `accepted_at`, and a prominent "Download migration package" CTA (calls `downloadJob(id)`) is shown as the primary action.
- [x] done

### S-J: Read-only editors in delivered mode
**File:** `src/frontend/src/components/JobDetail/EditorTab.tsx` (~L1093, L1167, L1249-1264)
**Depends on:** S-H
**Done when:** when the job is accepted, the Python editor is forced read-only (edit/lock toggle hidden or disabled); driven by an `accepted` prop threaded from `JobDetailPage`.
- [x] done

### S-K: Verdict strip accepted state
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx` (~L74-900)
**Depends on:** S-H
**Done when:** an `accepted` job renders a distinct "Delivered / Accepted" verdict treatment instead of the green/amber/red ready-to-accept states.
- [x] done

### S-L: Full suite green
**File:** —
**Depends on:** all above
**Done when:** `make test` exits 0; ruff + mypy pass; backlog updated.
- [x] done

## Dependencies on other features

- **F14 (auth):** will replace `accepted_by="anonymous"` with a real user identity. Stub until then.
- Databricks Workflow YAML export — out of scope (blocked on cloud deployment spec).

## Out of scope for this feature

- Email / webhook notifications on acceptance
- Databricks Workflow YAML in the export package
- Revoke acceptance (create a new job instead)
- Per-file input hashing (single `input_hash` field used as-is)
