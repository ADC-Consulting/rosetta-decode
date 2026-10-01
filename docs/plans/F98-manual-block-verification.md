# F98 — Manual block verification, available consistently in the Plan tab

**Phase:** 3
**Area:** Both (small Backend / API addition + Frontend consolidation)
**Status:** in-progress

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

- [ ] `block_revisions` has a nullable `verified_by` column (no `verified_at` needed — the
      existing `created_at` on a `human-verify`-triggered revision already serves as "when")
- [ ] `PATCH /jobs/{id}/blocks/{block_id}/python` accepts an optional `verified_by` in its request
      body, stored only when `trigger == "human-verify"`
- [ ] `ChangelogEntry` exposes `verified_by`
- [ ] A shared `deriveBlockStatus`/`BlockStatus` helper exists (currently duplicated/divergent
      between `ETLTab.tsx` and `BlockPlanTable.tsx`) and both consume it
- [ ] `BlockCodePopup` has two distinct footer actions when editable: "Save" (`trigger: "human"`,
      no verification) and "Mark as verified" (`trigger: "human-verify"`, prompts for a reviewer
      name pre-filled from `localStorage`) — not the same action
- [ ] `BlockCodePopup` has a dark/light theme toggle for the editor, matching what
      `BlockPlanTable`'s dialog already has today (parity requirement before Plan tab can switch to
      it without regressing)
- [ ] `BlockPlanTable.tsx`'s hand-rolled `<Dialog>` is replaced with `<BlockCodePopup>`, keeping its
      existing (more complex) source/generated-file resolution logic intact
- [ ] A verified block shows a visible "Verified by X" indicator in both ETL tab and Plan tab
- [ ] `make test` exits 0, ruff/mypy/tsc/lint all pass

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
- [ ] done

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
- [ ] done

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
- [ ] done

### G: Manual smoke test
**Depends on:** F
**Done when:** verified live (or via careful code review + `tsc`/lint if a live rebuild isn't
practical, per this session's established fallback) — in the Plan tab's step table, open a
`needs_review` block's code, confirm both "Save" and "Mark as verified" appear and behave distinctly,
confirm the block drops out of the `needs_review` count once verified, confirm "Verified by X" shows
in both the Plan tab and ETL tab for the same block (same underlying data, two surfaces).
- [ ] done

### Final: Full verification
- [ ] `make test` exits 0
- [ ] ruff, mypy, tsc, lint all pass
- [ ] Mark F98 done in `journal/BACKLOG.md`

## Dependencies on other features

- Builds on the existing `BlockRevision`/changelog/`trust-report` infrastructure — extends it with
  one column, doesn't replace anything.

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
