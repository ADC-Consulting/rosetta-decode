# F94 — Migration Row Actions (sensitive-data flag, delete, archive, bulk actions)

**Phase:** 3
**Area:** Both
**Status:** complete

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
  untouched. Reversible — including from the UI: a live-testing pass found the original build had
  no way to actually reverse an archive (only "Show archived" to view it), so an "Unarchive" kebab
  item and a bulk-bar toggle were added (see S-I/S-J notes below).

## Acceptance Criteria

- [x] `GET /jobs` excludes archived jobs by default; an `include_archived` query param opts back in
- [x] `JobSummary` exposes `sensitive_data: bool` and `is_archived: bool`
- [x] `DELETE /jobs/{job_id}` hard-deletes the job and all FK-cascaded child rows; 404 if not found
- [x] `PATCH /jobs/{job_id}/archive` toggles `is_archived`
- [x] Frontend: row checkbox selection + bulk action bar (Download/Archive/Delete) replaces the
      toolbar while ≥1 row is selected, matching the mockup
- [x] Frontend: per-row kebab menu offers "Delete migration" behind a confirm dialog
- [x] Frontend: sensitive-data warning icon shown per row when `sensitive_data` is true, with a
      tooltip
- [x] Frontend: row action distinguishes a static "Trace" (completed jobs) from a pulsing "Watch
      live" state (running/queued jobs)
- [x] Frontend: archive is reversible from the UI — per-row "Unarchive" kebab item (shown only on
      archived rows) and a bulk-bar toggle (Archive ⇄ Unarchive when all selected rows share the
      same archived state) — added after live testing found the original build was one-directional
- [x] `make test` exits 0, including new route tests for list/delete/archive
- [x] ruff and mypy pass

## Subtasks

### S-A: Alembic migration — `is_archived` column
**File:** `alembic/versions/021_add_job_is_archived.py`, `src/backend/db/models.py`
**Depends on:** none
**Done when:** `jobs.is_archived` exists as `Boolean NOT NULL DEFAULT false` (matches the
`cancellation_requested`/`skip_llm` column pattern already on `Job`); `Job.is_archived` mapped
column added.
- [x] done — `021_add_job_is_archived.py` chains `down_revision = "020"`; column added matching
  the `cancellation_requested` pattern exactly. Verified applying cleanly via `docker compose up
  --build backend` (entrypoint runs `alembic upgrade head` automatically) — logged
  `020 -> 021, Add is_archived column to jobs` on startup.

### S-B: `JobSummary` schema fields
**File:** `src/backend/api/schemas.py`
**Depends on:** S-A
**Done when:** `JobSummary` gains `sensitive_data: bool = False` and `is_archived: bool = False`.
- [x] done — also added `ArchiveJobRequest { archived: bool }` here (needed for S-E).

### S-C: List route — populate new fields + exclude archived by default
**File:** `src/backend/api/routes/jobs.py` (`list_jobs`)
**Depends on:** S-B
**Done when:** `list_jobs` derives `sensitive_data` from
`bool((j.migration_plan_post_run or j.migration_plan or {}).get("sensitive_data_findings"))` (no
extra query — `migration_plan`/`migration_plan_post_run` are already loaded on the `Job` row),
sets `is_archived=j.is_archived`, and excludes `is_archived=True` rows unless a new
`include_archived: bool = Query(default=False)` param is set.
- [x] done — `is_archived` coerced via `bool(j.is_archived)` (not a bare attribute read) so an
  unflushed/partially-populated `Job` object can never pass a `None` through to the non-Optional
  schema field; fixed a real regression this caused in 3 pre-existing tests (see S-F).

### S-D: `DELETE /jobs/{job_id}` route
**File:** `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py` if a response body is
needed
**Depends on:** none
**Done when:** the route hard-deletes the `Job` row (relying on existing FK cascades), returns 204
on success, 404 if the job doesn't exist.
- [x] done — `await session.delete(job)` relies on the ORM-level `cascade="all, delete-orphan"`
  relationships (not raw SQL), so cascade doesn't depend on the DB enforcing `ON DELETE CASCADE` —
  works identically under SQLite (tests) and Postgres (prod).

### S-E: `PATCH /jobs/{job_id}/archive` route
**File:** `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py`
**Depends on:** S-A
**Done when:** a new `ArchiveJobRequest { archived: bool }` schema exists; the route sets
`job.is_archived` and returns the updated `JobStatusResponse` (or a minimal ack), 404 if not found.
- [x] done — returns `JobStatusResponse`, matching the `accept_job`/`update_python_code` house
  style of update-then-refetch-then-respond.

### S-F: Backend route tests
**File:** `tests/test_jobs_routes.py` (or the existing route-test module covering `/jobs` — match
current test file naming, do not create a duplicate)
**Depends on:** S-C, S-D, S-E
**Done when:** tests cover: list excludes archived by default, `include_archived=true` includes
them, `sensitive_data` reflects a job with `sensitive_data_findings` present vs absent, DELETE
removes the row and cascades (assert child rows gone), DELETE 404 on unknown id, PATCH archive
toggles the flag and is reflected in a subsequent list call.
- [x] done — added to `tests/test_jobs_routes_comprehensive.py` with a real in-memory-SQLite
  fixture (`f94_session`) rather than mocks, since filtering/cascade behavior needs a real DB.
  Also fixed 5 pre-existing `list_jobs(...)` call sites broken by the new `include_archived`
  positional param, and fixed 3 pre-existing tests broken by the S-C `None`-vs-`bool` issue.

### S-G: Frontend types
**File:** `src/frontend/src/api/types.ts`
**Depends on:** S-F
**Done when:** `JobSummary` interface gains `sensitive_data: boolean` and `is_archived: boolean`.
- [x] done

### S-H: Frontend API client functions
**File:** `src/frontend/src/api/jobs.ts`
**Depends on:** S-G
**Done when:** `deleteJob(jobId: string): Promise<void>`, `archiveJob(jobId: string, archived:
boolean): Promise<void>` exist; `listJobs` accepts an optional `includeArchived` param threaded to
the query string.
- [x] done

### S-I: Bulk selection + bulk action bar
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-H
**Done when:** a checkbox column exists per row + a header "select all" checkbox; when ≥1 row is
selected, the toolbar (search/filter/New migration from F93) is replaced by a bulk action bar
showing "N selected" plus Download/Archive/Delete buttons, matching the mockup. Bulk Delete
confirms before firing; bulk Archive calls `archiveJob` for each selected id and refetches the
list.
- [x] done — extracted into `src/frontend/src/components/JobsTable/{BulkActionBar,
  DeleteConfirmDialog}.tsx`. Bulk Download loops the existing single-job download per selected id
  (matches "Out of scope" — no combined zip). **Post-smoke-test addition:** the Archive button now
  reads "Unarchive" (with an `ArchiveRestore` icon) and un-archives instead when every selected row
  is already archived — mixed selections keep the "Archive" label and re-archiving an
  already-archived row in the batch is a harmless no-op.

### S-J: Per-row kebab menu
**File:** `src/frontend/src/pages/JobsPage.tsx` (or a new `src/frontend/src/components/MigrationRowMenu.tsx` if the inline JSX gets unwieldy)
**Depends on:** S-H
**Done when:** each row's Actions cell has a kebab (`MoreVertical`) button opening a menu with
"Delete migration" (destructive styling, per mockup); selecting it opens a confirm dialog before
calling `deleteJob` and refetching the list.
- [x] done — extracted into `src/frontend/src/components/JobsTable/MigrationRowActions.tsx`.
  **Post-smoke-test addition:** when the row is archived, an "Unarchive" item (`ArchiveRestore`
  icon, non-destructive, no confirm dialog) now appears above a separator, ahead of "Delete
  migration" — the original build had no way to reverse an archive from the UI at all.

### S-K: Sensitive-data warning icon
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-G
**Done when:** the Name cell renders an `AlertTriangle` icon (red, per mockup) with a tooltip when
`job.sensitive_data` is true; no icon rendered otherwise.
- [x] done — extracted into `src/frontend/src/components/JobsTable/SensitiveDataIcon.tsx`; table
  wrapped in `TooltipProvider`. Verified live: "Sensitive data detected" tooltip on hover.

### S-L: "Show archived" toggle
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-H
**Done when:** a toggle/checkbox in the filter row lets the user opt into seeing archived jobs
(threads `includeArchived` into the `listJobs` query) — required so Archive stays genuinely
reversible from the UI, not just from the API.
- [x] done — verified live: toggling "Show archived" correctly brings archived rows back into
  view and threads `includeArchived` into the query key so it refetches correctly.

### S-M: Trace vs "Watch live" row action
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** none
**Done when:** the row action button reads "Trace" (static, per mockup row 1) for
completed/reviewable jobs and shows a pulsing "Watch live" state for `running`/`queued` jobs,
replacing the current single icon-only `Activity` button that only varies by pulse class; opens the
same `LiveTraceDialog` either way.
- [x] done — folded into `MigrationRowActions.tsx`. `accepted` jobs show "Download" (existing
  behavior, not mentioned in the plan's literal wording but consistent with what it replaced).

### S-N: Manual smoke test
**Depends on:** S-I, S-J, S-K, S-L, S-M
**Done when:** verified live — select rows and use each bulk action, delete a single job via
kebab (confirm dialog blocks accidental deletion), archive then find it via "Show archived",
sensitive-data icon appears only on jobs with findings, Trace/Watch-live states render correctly
for running vs completed jobs.
- [x] done — verified live at localhost:5173/jobs via browser automation, against the real dev
  stack (backend rebuilt + migration 021 applied). Bulk select/archive, "Show archived", kebab
  delete confirm dialog, sensitive-data tooltip all confirmed working. Live testing surfaced two
  real bugs, both fixed before sign-off: (1) a pre-existing, unrelated self-import bug in
  `checkbox.tsx` that white-screened any page rendering a `Checkbox` — this was the first feature
  to actually render one; (2) no UI path existed to reverse an archive (see S-I/S-J additions
  above). Test data restored to its original state afterward via the API directly.

### S-O: `make test` gate
**Depends on:** S-N
**Done when:** `make test` exits 0 (ruff, mypy, pytest+coverage, tsc, frontend-lint,
frontend-build all green).
- [x] done — all 7 gates green, exit code 0, confirmed after the unarchive-UI addition too.

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
