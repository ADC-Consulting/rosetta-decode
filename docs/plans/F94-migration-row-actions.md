# F94 — Migration Row Actions (sensitive-data flag, delete, archive, bulk actions)

**Phase:** 3
**Area:** Both
**Status:** in-progress

## Goal

Implement the backend-touching half of the approved "Manifest" Migrations page mockup
(`docs/design/MigrationsPage.dc.html`): a per-row sensitive-data warning icon, bulk row selection
with a bulk action bar (Download/Archive/Delete), a per-row kebab menu (Delete migration), and a
richer per-row action (Trace vs a pulsing "Watch live" state) replacing the current single Activity
icon button. See `journal/DECISIONS.md` 2026-09-24 for why this was split from F93 (visual-only,
no backend changes) and for the locked semantics below.

**Locked semantics (user decision, 2026-09-24):**
- **Delete = hard delete.** Permanently removes the job row via `DELETE /jobs/{job_id}`, relying
  on the existing `ondelete="CASCADE"` foreign keys (job_versions, block revisions, job_traces —
  already confirmed working via the manual stray-job cleanup in the 2026-09-24 session). Requires
  a confirm dialog before the request fires — this is a destructive, irreversible action.
- **Archive = soft-hide.** Adds an `is_archived` flag; archived jobs are excluded from the default
  `GET /jobs` list but the row, `migration_plan`, `generated_files`, and full audit trail are
  untouched. Reversible.

## Acceptance Criteria

- [ ] `GET /jobs` excludes archived jobs by default; an `include_archived` query param opts back in
- [ ] `JobSummary` exposes `sensitive_data: bool` and `is_archived: bool`
- [ ] `DELETE /jobs/{job_id}` hard-deletes the job and all FK-cascaded child rows; 404 if not found
- [ ] `PATCH /jobs/{job_id}/archive` toggles `is_archived`
- [ ] Frontend: row checkbox selection + bulk action bar (Download/Archive/Delete) replaces the
      toolbar while ≥1 row is selected, matching the mockup
- [ ] Frontend: per-row kebab menu offers "Delete migration" behind a confirm dialog
- [ ] Frontend: sensitive-data warning icon shown per row when `sensitive_data` is true, with a
      tooltip
- [ ] Frontend: row action distinguishes a static "Trace" (completed jobs) from a pulsing "Watch
      live" state (running/queued jobs)
- [ ] `make test` exits 0, including new route tests for list/delete/archive
- [ ] ruff and mypy pass

## Subtasks

### S-A: Alembic migration — `is_archived` column
**File:** `alembic/versions/021_add_job_is_archived.py`, `src/backend/db/models.py`
**Depends on:** none
**Done when:** `jobs.is_archived` exists as `Boolean NOT NULL DEFAULT false` (matches the
`cancellation_requested`/`skip_llm` column pattern already on `Job`); `Job.is_archived` mapped
column added.
- [ ] done

### S-B: `JobSummary` schema fields
**File:** `src/backend/api/schemas.py`
**Depends on:** S-A
**Done when:** `JobSummary` gains `sensitive_data: bool = False` and `is_archived: bool = False`.
- [ ] done

### S-C: List route — populate new fields + exclude archived by default
**File:** `src/backend/api/routes/jobs.py` (`list_jobs`)
**Depends on:** S-B
**Done when:** `list_jobs` derives `sensitive_data` from
`bool((j.migration_plan_post_run or j.migration_plan or {}).get("sensitive_data_findings"))` (no
extra query — `migration_plan`/`migration_plan_post_run` are already loaded on the `Job` row),
sets `is_archived=j.is_archived`, and excludes `is_archived=True` rows unless a new
`include_archived: bool = Query(default=False)` param is set.
- [ ] done

### S-D: `DELETE /jobs/{job_id}` route
**File:** `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py` if a response body is
needed
**Depends on:** none
**Done when:** the route hard-deletes the `Job` row (relying on existing FK cascades), returns 204
on success, 404 if the job doesn't exist.
- [ ] done

### S-E: `PATCH /jobs/{job_id}/archive` route
**File:** `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py`
**Depends on:** S-A
**Done when:** a new `ArchiveJobRequest { archived: bool }` schema exists; the route sets
`job.is_archived` and returns the updated `JobStatusResponse` (or a minimal ack), 404 if not found.
- [ ] done

### S-F: Backend route tests
**File:** `tests/test_jobs_routes.py` (or the existing route-test module covering `/jobs` — match
current test file naming, do not create a duplicate)
**Depends on:** S-C, S-D, S-E
**Done when:** tests cover: list excludes archived by default, `include_archived=true` includes
them, `sensitive_data` reflects a job with `sensitive_data_findings` present vs absent, DELETE
removes the row and cascades (assert child rows gone), DELETE 404 on unknown id, PATCH archive
toggles the flag and is reflected in a subsequent list call.
- [ ] done

### S-G: Frontend types
**File:** `src/frontend/src/api/types.ts`
**Depends on:** S-F
**Done when:** `JobSummary` interface gains `sensitive_data: boolean` and `is_archived: boolean`.
- [ ] done

### S-H: Frontend API client functions
**File:** `src/frontend/src/api/jobs.ts`
**Depends on:** S-G
**Done when:** `deleteJob(jobId: string): Promise<void>`, `archiveJob(jobId: string, archived:
boolean): Promise<void>` exist; `listJobs` accepts an optional `includeArchived` param threaded to
the query string.
- [ ] done

### S-I: Bulk selection + bulk action bar
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-H
**Done when:** a checkbox column exists per row + a header "select all" checkbox; when ≥1 row is
selected, the toolbar (search/filter/New migration from F93) is replaced by a bulk action bar
showing "N selected" plus Download/Archive/Delete buttons, matching the mockup. Bulk Delete
confirms before firing; bulk Archive calls `archiveJob` for each selected id and refetches the
list.
- [ ] done

### S-J: Per-row kebab menu
**File:** `src/frontend/src/pages/JobsPage.tsx` (or a new `src/frontend/src/components/MigrationRowMenu.tsx` if the inline JSX gets unwieldy)
**Depends on:** S-H
**Done when:** each row's Actions cell has a kebab (`MoreVertical`) button opening a menu with
"Delete migration" (destructive styling, per mockup); selecting it opens a confirm dialog before
calling `deleteJob` and refetching the list.
- [ ] done

### S-K: Sensitive-data warning icon
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-G
**Done when:** the Name cell renders an `AlertTriangle` icon (red, per mockup) with a tooltip when
`job.sensitive_data` is true; no icon rendered otherwise.
- [ ] done

### S-L: "Show archived" toggle
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-H
**Done when:** a toggle/checkbox in the filter row lets the user opt into seeing archived jobs
(threads `includeArchived` into the `listJobs` query) — required so Archive stays genuinely
reversible from the UI, not just from the API.
- [ ] done

### S-M: Trace vs "Watch live" row action
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** none
**Done when:** the row action button reads "Trace" (static, per mockup row 1) for
completed/reviewable jobs and shows a pulsing "Watch live" state for `running`/`queued` jobs,
replacing the current single icon-only `Activity` button that only varies by pulse class; opens the
same `LiveTraceDialog` either way.
- [ ] done

### S-N: Manual smoke test
**Depends on:** S-I, S-J, S-K, S-L, S-M
**Done when:** verified live — select rows and use each bulk action, delete a single job via
kebab (confirm dialog blocks accidental deletion), archive then find it via "Show archived",
sensitive-data icon appears only on jobs with findings, Trace/Watch-live states render correctly
for running vs completed jobs.
- [ ] done

### S-O: `make test` gate
**Depends on:** S-N
**Done when:** `make test` exits 0 (ruff, mypy, pytest+coverage, tsc, frontend-lint,
frontend-build all green).
- [ ] done

## Dependencies on other features

- F93 (visual refresh) — not a hard blocker, but land F93 first to avoid two branches both
  rewriting large parts of `JobsPage.tsx` in parallel.

## Out of scope for this feature

- Bulk Download (per-job download already exists via `GET /jobs/{id}/download`; a bulk
  multi-job zip is a separate, larger feature if ever requested — bulk Download in this feature
  triggers the existing single-job download once per selected row, not a combined archive)
- Any change to what counts as "sensitive data" (uses the existing `sensitive_data_findings`
  from F32's PII scanner, unchanged)
- Undo/restore after a hard delete (by design — that's what Archive is for)
