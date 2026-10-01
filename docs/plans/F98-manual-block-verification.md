# F98 — Manual block verification, available consistently in the Plan tab

**Phase:** 3
**Area:** Both (small Backend / API addition + Frontend consolidation)
**Status:** complete

## Goal

**Revised after deeper investigation — this plan originally assumed no verification mechanism
existed at all. That was wrong.** A working, persisted "Mark as verified" feature already exists
in the ETL tab (`BlockCodePopup.tsx`): it calls the existing
`PATCH /jobs/{id}/blocks/{block_id}/python` endpoint with `trigger: "human-verify"`, and status is
derived from the job's changelog (`GET /jobs/{id}/changelog`, filtering `trigger === "human-verify"`)
— genuinely persisted, survives reload, no new backend infrastructure needed for that part.

The real gap: **the Plan tab's step table never got this feature.** `BlockPlanTable.tsx` has its
own separate, hand-rolled code dialog (its own Edit/Save flow, `trigger: "human"` by default, local
`humanEditedBlocks` state) that was built independently of `BlockCodePopup` and never gained the
verify capability. Two divergent implementations of "view/edit a block's code," one with verify,
one without.

Additionally, the existing mechanism has no reviewer attribution at all — `ChangelogEntry` records
`created_at` but nothing resembling "who." The original ask wanted that captured; this plan adds
it narrowly (one nullable column) rather than building new infrastructure that already exists
elsewhere in different form.

Done looks like: one shared code-dialog component, used by both ETL tab and the Plan tab, with a
"Mark as verified" action — distinct from plain Save — available everywhere a block's code can be
viewed, recording who verified it.

## Acceptance Criteria

- [x] `block_revisions` has a nullable `verified_by` column (no `verified_at` needed — the
      existing `created_at` on a `human-verify`-triggered revision already serves as "when")
- [x] `PATCH /jobs/{id}/blocks/{block_id}/python` accepts an optional `verified_by` in its request
      body, stored only when `trigger == "human-verify"`
- [x] `ChangelogEntry` exposes `verified_by`
- [x] A shared `deriveBlockStatus`/`BlockStatus` helper exists (currently duplicated/divergent
      between `ETLTab.tsx` and `BlockPlanTable.tsx`) and both consume it
- [x] `BlockCodePopup` has two distinct footer actions when editable: "Save" (`trigger: "human"`,
      no verification) and "Mark as verified" (`trigger: "human-verify"`, prompts for a reviewer
      name pre-filled from `localStorage`) — not the same action
- [x] `BlockCodePopup` has a dark/light theme toggle for the editor, matching what
      `BlockPlanTable`'s dialog already has today (parity requirement before Plan tab can switch to
      it without regressing)
- [x] `BlockPlanTable.tsx`'s hand-rolled `<Dialog>` is replaced with `<BlockCodePopup>`, keeping its
      existing (more complex) source/generated-file resolution logic intact
- [x] A verified block shows a visible "Verified by X" indicator in both ETL tab and Plan tab
- [x] The job-level `auto_verified`/`needs_review` counts actually reflect verification — found
      missing during live testing (backend never checked `verified_by`, and the Plan tab reads a
      separate, differently-keyed trust-report query than the one originally invalidated), both
      fixed and confirmed live: counts update reactively, no reload needed
- [x] `make test` exits 0, ruff/mypy/tsc/lint all pass

## Subtasks

### A: Alembic migration — `verified_by` on `block_revisions`
**File:** `alembic/versions/022_add_block_revision_verified_by.py`
**Depends on:** none
**Done when:** adds `verified_by: Text, nullable=True` to `block_revisions`, following the exact
style of `020_add_accepted_by.py` (single nullable column, no backfill).
- [x] done

### B: Schema + route — accept and store `verified_by`
**File:** `src/backend/api/schemas.py`, `src/backend/api/routes/jobs.py`
**Depends on:** A
**Done when:** the PATCH python-code request schema gains `verified_by: str | None = None`; the
route stores it on the new revision only when `trigger == "human-verify"` (ignored/null otherwise
— don't let an edit request silently carry over a stale name). `ChangelogEntry` gains
`verified_by: str | None`, populated from the revision row in the changelog query.
- [x] done

### C: Route tests
**File:** `tests/test_jobs_routes_comprehensive.py`
**Depends on:** B
**Done when:** tests confirm `verified_by` is stored when `trigger="human-verify"` and absent
otherwise (e.g. a `trigger="human"` save with a `verified_by` in the body does NOT persist it —
only verify-triggered saves should ever write this field), and that it round-trips through the
changelog endpoint.
- [x] done

### D: Shared `deriveBlockStatus` / `BlockStatus` helper
**File:** `src/frontend/src/components/JobDetail/status-colors.ts` (or a new small file in the same
directory if that one doesn't fit — use judgment, but keep it alongside the other shared
status/tone helpers already there)
**Depends on:** none (independent of A/B/C — pure frontend refactor)
**Done when:** `BlockStatus` type and `deriveBlockStatus()` (currently defined locally in
`ETLTab.tsx`) move to a shared module; `ETLTab.tsx` imports it instead of defining its own copy.
This subtask alone should be a no-op behavior change for ETL tab — pure extraction, verified by
`make test` and a quick manual check that ETL tab still looks identical.
- [x] done

### E: `BlockCodePopup` — split Save/Verify, add theme toggle
**File:** `src/frontend/src/components/JobDetail/BlockCodePopup.tsx`
**Depends on:** D (uses the shared status type), B (needs `verified_by` to display)
**Done when:**
- Footer has two distinct buttons when `!isReadOnly`: "Save" (`saveBlockPython(..., { trigger:
  "human" })`, no name prompt) and "Mark as verified" (prompts for a reviewer name — a small inline
  input, not a browser `prompt()` — pre-filled from `localStorage` key `rosetta.reviewerName` if
  present, required non-empty, then `saveBlockPython(..., { trigger: "human-verify", verified_by })`).
- A dark/light theme toggle for the editor pair, matching `BlockPlanTable`'s existing toggle
  (`codeEditorDark` state, sun/moon icon button) — port that interaction here.
- The "human-verified" status banner/indicator shows the `verified_by` name when present (e.g.
  "Verified by Jane — you can close this panel.").
- [x] done

### F: Replace `BlockPlanTable`'s hand-rolled dialog with `BlockCodePopup`
**File:** `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
**Depends on:** D, E
**Done when:** the existing `useEffect` that resolves `codeDialogPython`/`sasCode`/`codeDialogFile`
(lines ~416-461 as of this writing — handles the harder multi-file lookup that `BlockCodePopup`
doesn't currently need to do, since ETL tab always hands it one specific file's content) stays as
the data-loading logic, but its JSX output changes from a hand-built `<Dialog>` to rendering
`<BlockCodePopup>` with the resolved values, computed `status` (via the shared helper from subtask
D, using this component's existing `trustBlocks`/`bp.strategy` data plus a changelog fetch for
`humanVerifiedBlocks`/`verified_by` — same `useQuery(getJobChangelog)` pattern already used in
`ETLTab.tsx`), and wires `onVerified`/`onClose` to the existing query-invalidation calls
(`block-revisions`, `job`, `job versions`) already present in this file. The now-unused
`codeEditorDark`/`codeEditable`/`codeSaving` local dialog state and JSX are removed — `BlockCodePopup`
owns that now.

Found and fixed two additional gaps while live-testing (both pre-existing, not introduced by this
subtask): (1) `needs_attention` never checked `verified_by` at all — a verified block's own badge
updated but the job-level `auto_verified`/`needs_review` counts (and the effort-estimate formula
that reads them) never moved; fixed server-side with a short-circuit override. (2) the frontend has
two separate trust-report queries under different key shapes (`["job", jobId, "trust-report"]` in
`JobDetailPage.tsx`, consumed by `ETLTab`'s summary bar, vs `["trust-report", jobId]` in
`PlanTab.tsx`, driving the Plan tab's counts) — the verify callbacks only invalidated the first one,
so the Plan tab's counts were stale until a full page reload; fixed by invalidating both. Verified
live end-to-end after both fixes: counts update reactively, in place, with no reload needed.
- [x] done

### G: Manual smoke test
**Depends on:** F
**Done when:** verified live (or via careful code review + `tsc`/lint if a live rebuild isn't
practical, per this session's established fallback) — in the Plan tab's step table, open a
`needs_review` block's code, confirm both "Save" and "Mark as verified" appear and behave distinctly,
confirm the block drops out of the `needs_review` count once verified, confirm "Verified by X" shows
in both the Plan tab and ETL tab for the same block (same underlying data, two surfaces).

Verified live via real browser automation (not just code review): opened a `needs_review` block in
the Plan tab's step table, confirmed the consolidated `BlockCodePopup` renders there with Save and
Mark as verified as distinct actions, confirmed the reviewer-name prompt pre-fills from
`localStorage`, confirmed the badge flips to "Human-verified" with the name shown, and confirmed
(after finding and fixing the two gaps noted in subtask F) the job-level counts update reactively
in the same session, no reload required.
- [x] done

### Final: Full verification
- [x] `make test` exits 0
- [x] ruff, mypy, tsc, lint all pass
- [x] Mark F98 done in `journal/BACKLOG.md`

## Dependencies on other features

- Builds on the existing `BlockRevision`/changelog/`trust-report` infrastructure — extends it with
  one column, doesn't replace anything.

## Follow-ups discovered, not actioned here

- **A third divergent `deriveBlockStatus`-equivalent exists**: `src/frontend/src/components/JobDetail/blockStatusHelpers.ts`
  (`BlockStatusKind`/`getBlockStatus`, used by `BlockInspectorPanel`/`PipelineStepPanel` via
  `BlockRow`) — a different enum shape (includes a `failed` state the others don't), display-only,
  not a code-editing dialog. Out of scope for this feature since it doesn't touch verification
  directly, but it's the same class of duplication this plan just fixed twice over. Worth
  consolidating alongside `status-colors.ts`'s version someday.
- **Two separate trust-report queries with different key shapes** (`["job", jobId, "trust-report"]`
  in `JobDetailPage.tsx`, `["trust-report", jobId]` in `PlanTab.tsx`) is itself a code-quality issue
  — both are now correctly invalidated after a verify action, but having two independent queries
  for the same backend resource is fragile and will bite again the next time someone adds a feature
  that changes trust-report data without knowing both exist. Worth unifying into one shared query
  (e.g. lifted to a hook or context) in a future cleanup.
- **A separate, pre-existing bug unrelated to F98**: hard-navigating directly to any `/jobs/...` URL
  (not via client-side routing) returns raw backend JSON instead of the SPA — nginx's `/jobs`
  location block (added in F97) proxies the request to the backend before the SPA ever loads, since
  the API and the page share the same path prefix. Affects any bookmark, shared link, or browser
  refresh while on a job detail page. Found while live-testing this feature; not fixed here since
  it's an F97-era infrastructure issue, not an F98 one — flagged in `journal/BACKLOG.md` for
  separate follow-up.

## Out of scope for this feature

- Any real authentication/login system — same reasoning as the original draft: the free-text
  reviewer name is a deliberate, minimal stand-in, consistent with how little identity tracking
  exists in this codebase today (`accepted_by`, added in migration 020, is hardcoded to
  `"anonymous"` at its one call site and never actually prompted for — this feature is more
  rigorous than that existing shortcut, not copying it).
- Changing `manual_todo` (`strategy === "manual"`) handling — untouched.
- Carrying verification forward across revisions — a new revision (from editing/refining) starts
  unverified again; this is intended, not a bug to special-case away.
- Changing the effort-estimate formula's logic — it already reads `needs_review` correctly from
  upstream (confirmed in this session's earlier investigation); once `needs_attention` correctly
  reflects verification status, the formula needs no changes.
