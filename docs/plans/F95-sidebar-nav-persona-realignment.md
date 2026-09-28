# F95 — Sidebar Nav Persona Realignment (#52)

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

Realign the sidebar nav with who actually uses rosetta-decode today. Issue #52 gated any nav
change on confirming target personas; `docs/personas.md` (PR #156) settles that — P0 (ADC
consultant, current primary user) is the working lens, not the P1/P2 end-state personas the app
was originally designed around. Per the Persona × Feature mapping table, "Docs" is unclearly named
for what it actually does (the plain-English trust-closing view P0 and P2 both rely on), and the
global Lineage page has no owner across any of the three personas — it's most likely scoped for a
not-yet-built compliance/auditor persona (issue #30, Phase 3+).

**Locked constraint (user's explicit instruction, 2026-09-28):** removing Lineage from the sidebar
must never delete the `/lineage` route, `GlobalLineagePage` component, or any of its functionality.
Only the sidebar nav entry is removed — the feature must be trivially re-addable later. Every
subtask below is framed as "remove the nav link," never "remove Lineage."

## Acceptance Criteria

- [x] Sidebar shows 3 items: Migrations, Reports, Explain — in that order
- [x] "Docs" label reads "Reports" everywhere it appears in nav (not just the sidebar — check for
      any other hardcoded "Docs" nav-label references)
- [x] `/lineage` route still resolves and `GlobalLineagePage` still renders correctly when visited
      directly by URL — confirms nothing was deleted, only unlinked
- [x] No dead imports/unused code left behind in `AppSidebar.tsx` from the removed nav entry
- [x] `make test` exits 0
- [x] ruff, mypy, tsc, eslint all pass

## Subtasks

### S-A: Remove Lineage nav entry, keep the route
**File:** `src/frontend/src/components/AppSidebar.tsx`
**Depends on:** none
**Done when:** the `NAV_ITEMS` array (line 22-26) no longer contains the `{ to: "/lineage", label:
"Lineage", Icon: GitFork }` entry. The `GitFork` icon import is removed only if nothing else in
this file uses it (check before removing). `src/frontend/src/App.tsx`'s `/lineage` route
(`<Route path="/lineage" element={<GlobalLineagePage />} />`, line 34) and the lazy import of
`GlobalLineagePage` (line 11) are explicitly NOT touched — this subtask is a nav-array edit only,
nothing else.
- [x] done — `GitFork` icon import also removed (confirmed unused elsewhere in the file).
  `App.tsx` confirmed byte-for-byte unchanged (`git diff` empty). Live-verified: `/lineage`
  resolves directly by URL and renders `GlobalLineagePage` correctly, just no longer in the
  sidebar's active-link set.

### S-B: Rename "Docs" to "Reports"
**File:** `src/frontend/src/components/AppSidebar.tsx`
**Depends on:** none
**Done when:** the `NAV_ITEMS` entry `{ to: "/docs", label: "Docs", Icon: FileText }` becomes
`{ to: "/docs", label: "Reports", Icon: FileText }` — route path (`/docs`) and icon stay the same,
only the visible label changes. Grep the rest of `src/frontend/src/` for any other hardcoded "Docs"
string used as a nav label or page heading that should read "Reports" for consistency (e.g. a page
title on `DocsPage.tsx` itself) — update only actual nav-facing labels, not internal variable/file
names like `DocsPage.tsx` itself (renaming the file/component is out of scope, see below).
- [x] done — grepped `src/frontend/src/` for other "Docs" strings. Found two unrelated matches in
  `LiveTraceDialog.tsx`'s `ENRICHMENT_LABELS` map ("Technical docs", "Lineage graph") — these
  label per-block trace enrichment types, a different concept from the top-level nav pages;
  correctly left unchanged. No actual nav-label or page-heading matches needed updating
  (`DocsPage.tsx`'s own `<h1>` already reads "Documentation", not "Docs").

### S-C: Manual smoke test
**Depends on:** S-A, S-B
**Done when:** verified live — sidebar shows exactly Migrations, Reports, Explain in that order;
clicking Reports navigates to `/docs` and renders the existing Docs page correctly; navigating
directly to `/lineage` by URL still renders `GlobalLineagePage` with no errors (confirms the route
wasn't broken, just unlinked); no console errors; light and dark theme both checked.
- [x] done — verified live via browser automation: sidebar shows exactly Migrations/Reports/
  Explain in order, Reports link navigates to `/docs` correctly, direct navigation to `/lineage`
  renders `GlobalLineagePage` with no app errors (one unrelated Chrome-extension messaging
  artifact in the console, not an app issue).

### S-D: `make test` gate
**Depends on:** S-C
**Done when:** `make test` exits 0 (ruff, mypy, pytest+coverage, tsc, frontend-lint,
frontend-build all green).
- [x] done — all 7 gates green, exit code 0.

## Dependencies on other features

- Stacked on `fix/sidebar-rosetta-logo-mark` (PR #157) rather than `main` — that branch already
  modifies `AppSidebar.tsx` (the logo mark), and this feature modifies the same file's nav array.
  Avoids a same-file merge conflict between two in-flight branches. Rebase onto `main` once #157
  merges if this branch is still open at that point.

## Out of scope for this feature

- Renaming `DocsPage.tsx` the file/component, or any internal `docs`-prefixed route/variable
  naming — only the user-facing nav label changes
- Any change to `GlobalLineagePage.tsx` or the `/lineage` route itself — explicitly preserved,
  not touched
- Visual/structural grouping of the remaining 3 nav items (e.g. section headers) — not needed at
  3 items, the original "four flat, equally-weighted items" problem is resolved by removing the
  one item with no persona owner, not by adding structure
- Re-adding Lineage to the nav when the compliance/auditor persona (#30) is eventually scoped —
  tracked as a future item, not part of this feature
