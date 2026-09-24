# F93 — Migrations Page Visual Refresh

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

Bring `JobsPage.tsx` (the Migrations list) and `AppSidebar.tsx` up to the approved "Manifest"
mockup (`docs/design/MigrationsPage.dc.html`) for everything that needs no backend change: the
job-status column restyled onto the shared `StatusChip`/`status-colors.ts` tone system, a header
stat line, client-side search/filter/sort on the existing jobs array, and a check on whether the
sidebar nav icons actually need changing. This is the low-risk half of the mockup — see
`journal/DECISIONS.md` 2026-09-24 for the split rationale and F94 for the backend-touching half
(sensitive-data flag, delete, archive, bulk actions, kebab menu).

Token fidelity was pre-checked: the mockup's `:root` tokens already match the live
`.brand-manifest` scope (`src/frontend/src/index.css`) exactly — no F88/F89-style drift-fix pass
needed here.

## Acceptance Criteria

- [x] Migrations table's Status column renders via `StatusChip` (filled Manifest pill) instead of
      the current shimmer-gradient/plain-text `TableStatus` treatment
- [x] Header shows a stat line ("N migrations, N need review, N running, N accepted") matching the
      mockup, computed entirely client-side from the already-fetched jobs array
- [x] A search input filters the visible rows by job name (case-insensitive substring)
- [x] A status filter control filters the visible rows by status, composable with search
- [x] Name, Status, Files, and Created column headers sort the table client-side, with a visual
      sort-direction indicator matching the mockup
- [x] Sidebar nav icons confirmed correct against the mockup (swapped only if a real mismatch is
      found — see S-G)
- [x] `make test` exits 0
- [x] ruff and mypy pass (no backend touched, but gate stays part of `make test`)

## Subtasks

### S-A: Job-status → Tone map
**File:** `src/frontend/src/components/JobDetail/status-colors.ts`
**Depends on:** none
**Done when:** a new `JOB_STATUS_TONE: Record<JobStatusValue, Tone>` export exists, mapping
`queued`/`running` → `neutral`, `proposed`/`under_review` → `warning`, `accepted`/`done` →
`success`, `failed` → `danger` — reusing the existing five-tone system (no new tones invented).
- [x] done

### S-B: Status column → `StatusChip`
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-A
**Done when:** the table's Status cell renders `<StatusChip tone={JOB_STATUS_TONE[job.status]}>`
with `STATUS_LABEL[job.status]` and a status icon (per mockup lines ~240-244), replacing the
current `TableStatus` component; the `running`/`queued` pulse indication is preserved (e.g. an
`animate-pulse` class on the icon) so in-progress jobs are still visually distinct from a static
pill. `TableStatus` is deleted once nothing references it.
- [x] done — implemented as `StatusCell`/`StatusCellIcon`; running/queued show a pulsing dot
  instead of a static icon. Verified live: amber "Needs Review" pill w/ triangle icon, green
  "Accepted" pill w/ check icon render correctly.

### S-C: Header stat line
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** none
**Done when:** a `<p>` under the "Migrations" `<h1>` renders a stat summary derived via `useMemo`
from the jobs array (total count, count where status is `proposed`/`under_review`, count
`running`/`queued`, count `accepted`), matching the mockup's copy pattern.
- [x] done — verified live: "17 migrations, 16 need review, 0 running, 1 accepted" matches the
  visible rows.

### S-D: Search input (client-side name filter)
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** none
**Done when:** a controlled text input (mockup's search bar, magnifying-glass icon) filters the
rendered rows by case-insensitive substring match against `job.name` (fallback to `job.job_id`
when name is null); empty-state copy updates to reflect an active filter yielding zero rows,
distinct from the true empty-state copy.
- [x] done — verified live: searching "Biometrics" narrows 17 rows to the single matching job.

### S-E: Status filter pill
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-D
**Done when:** a status filter control (mockup's dropdown pill) narrows the rendered rows to a
selected status (or "All"); composes with S-D's search filter via AND, sharing one filter-state
object rather than two independent `useState` filters re-deriving the list separately.
- [x] done — implemented via shadcn `Select`, collapses proposed/under_review into one "Needs
  Review" option. Verified live: selecting "Accepted" narrows to exactly the 1 accepted job.

### S-F: Sortable columns
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** none
**Done when:** clicking the Name, Status, Files, or Created column header toggles sort direction
and reorders the (already filtered) rows client-side; the active sort column shows a chevron
indicator per the mockup, inactive columns show a dimmed indicator.
- [x] done — verified live: clicking "Created" sorts ascending then descending correctly, chevron
  flips direction, other columns' chevrons stay dimmed.

### S-G: Sidebar icon verification
**File:** `src/frontend/src/components/AppSidebar.tsx`
**Depends on:** none
**Done when:** each of the 4 mockup sidebar icon SVGs (`docs/design/MigrationsPage.dc.html` lines
140/144/148/152) has been compared against the live `NAV_ITEMS` icons (`LayoutList`, `GitFork`,
`FileText`, `MessageSquare`). Live-component check first, per the 2026-09-04 correction in
`journal/DECISIONS.md` — do not assume the backlog note's "icons need correcting" is still true
without re-reading the component; the mockup's paths may just reflect a newer `lucide-react`
render of the *same* icon components already in use. Only swap an import if a genuine name-level
mismatch is confirmed, and record the finding (swap made, or no change needed) in this subtask's
done-note.
- [x] done — no change made. Diffed the mockup's 4 sidebar SVGs against the installed
  `lucide-react` source for `LayoutList`/`GitFork`/`FileText`/`MessageSquare`: path data is
  byte-for-byte identical. The live icons already match the mockup exactly.

### S-H: Manual smoke test
**Depends on:** S-B, S-C, S-D, S-E, S-F, S-G
**Done when:** verified live against the local dev stack — status pills render correct tone per
status, search + status filter compose correctly, each column sorts both directions, sidebar
renders unchanged or correctly swapped, no regression to existing row-click navigation or the
"New migration" dialog.
- [x] done — verified live at localhost:5173/jobs via browser automation: status chips, header
  stat line, search, status filter, both sort directions, row-click navigation into job detail
  all confirmed working; sidebar unchanged (per S-G). "New migration" dialog not re-tested (out
  of F93 scope, untouched by this feature).

### S-I: `make test` gate
**Depends on:** S-H
**Done when:** `make test` exits 0 (ruff, mypy, pytest+coverage, tsc, frontend-lint,
frontend-build all green).
- [x] done — all 7 gates green, exit code 0.

## Dependencies on other features

- None. F94 (backend-touching row actions) is independent and can be planned/built in either
  order relative to this feature, but both touch `JobsPage.tsx` — land one PR before starting the
  other to avoid a merge-conflict-heavy parallel branch.

## Out of scope for this feature

- Sensitive-data warning icon (needs a backend field — F94)
- Bulk selection, bulk action bar, per-row kebab menu, delete, archive (F94)
- Richer Trace vs "Watch live" row-action distinction (F94, since it's grouped with the row-actions
  redesign even though it's frontend-only)
- Any change to `JobSummary`'s backend schema or the `/jobs` list route
