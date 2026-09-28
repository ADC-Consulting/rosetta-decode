# F96 — Welcome Page (#148, remaining item)

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

Add a welcome/landing page at `/`, closing out the last open item from #148 (the other three —
sidebar revisit, unified upload flow, Manifest styling on the upload dialog — already shipped via
F92/F95). The page's job, per the P0 persona (`docs/personas.md`) and the approved mockup: give a
prospective client a strong, credible first impression in seconds when a consultant opens the tool
at the start of a demo, then hand off cleanly into starting a real migration. Static content only —
no live data pulled in, so it never looks stale or empty regardless of demo-account state.

Design reference: the approved mockup, published as a Claude Artifact
(https://claude.ai/artifact/YbsWRL5EM52aDNDZxU99Xf) — extract and commit its source to
`docs/design/` per this project's standing rule that an approved design-canvas mockup must be
preserved in-repo, not left as an external link only (see `journal/DECISIONS.md` 2026-09-02).

**Locked content decisions (user, 2026-09-28):**
- Primary CTA is "New migration" (upload) only — no secondary "browse demo scenarios" path, since
  no persistent demo library is maintained in the tool (demos are uploaded live per session, see
  the `docs/personas.md` P0 correction)
- Static content only, no live migration counts/stats
- Copy stays concrete to SAS→Python (the current, real capability and market-entry wedge) — do
  not generalize the wording toward "multiple languages," even though that's the long-term vision
  (see memory note `project_multi_language_vision`)

## Acceptance Criteria

- [x] `/` renders the new welcome page (no longer redirects to `/jobs`)
- [x] Page matches the approved mockup: two-column hero (copy + code-proof panel), 3-step process
      panel, trust strip — using real Tailwind/shadcn classes and the actual `.brand-manifest`
      tokens, not the mockup's standalone CSS
- [x] "New migration" CTA navigates to `/jobs` and automatically opens the existing upload dialog
      (no duplicate dialog implementation)
- [x] "or view existing migrations" secondary link navigates to `/jobs` without opening the dialog
- [x] Sidebar (`<AppSidebar />`, rendered once at the `App.tsx` level) is unaffected — no nav item
      shows an active state while on `/`, since none of the 3 nav routes match it
- [x] Light and dark theme both correct
- [x] `make test` exits 0
- [x] ruff, mypy, tsc, eslint all pass

## Subtasks

### S-A: Extract and commit the approved mockup source
**File:** `docs/design/welcome-page.dc.html` (or similar, matching the `docs/design/Manifest.dc.html`/`MigrationsPage.dc.html` naming convention already in this repo)
**Depends on:** none
**Done when:** the mockup's HTML source is committed in-repo, per the standing rule that approved
design-canvas mockups must not exist only as an external Artifact link.
- [x] done — committed as `docs/design/welcome-page.dc.html`.

### S-B: `WelcomePage.tsx` component
**File:** `src/frontend/src/pages/WelcomePage.tsx`
**Depends on:** S-A
**Done when:** a new page component renders the welcome content only — no sidebar, no outer
`flex`/`main` wrapper, since `App.tsx` already renders `<AppSidebar />` once and wraps all routes
in a shared `<main>`. Content: eyebrow line, headline, outcome-focused subhead (no process detail
— see mockup), CTA row (primary button + secondary link, not yet wired to real navigation — that's
S-C), the code-proof panel (static SAS/PySpark example with a `# SAS: <file>:<line>` provenance
comment and a "Reconciled" badge — hardcoded illustrative content, not live data, styled using
`TONE_CHIP_CLASS`/tone tokens from `status-colors.ts` for the badge to stay consistent with the
rest of the app's tone system rather than a one-off color), the 3-step process panel (Upload /
Review / Accept, matching the mockup's copy — this is the only place the process is described, per
the locked "don't repeat the subhead" decision), and the trust strip. All colors/fonts/radius via
real Tailwind classes referencing the actual `.brand-manifest` tokens (e.g. `bg-[var(--primary)]`
where a derived-token indirection risk exists, per the F88/F94 pattern already established in this
codebase — do not reintroduce the `bg-primary`/`text-primary-foreground` bug fixed in PR #157).
- [x] done — `WelcomePage.tsx` built content-only, wrapped in `.brand-manifest`. Badge reuses
  `StatusChip` (`tone="success"`) rather than a hand-rolled style. Keyword/string colors use real
  tokens (`text-[var(--primary)]`, `text-[var(--tone-warning)]`) rather than new hex values.

### S-C: Wire the CTA to the existing upload dialog
**File:** `src/frontend/src/pages/WelcomePage.tsx`, `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-B
**Done when:** the "New migration" button navigates to `/jobs?upload=1` (or equivalent query
param); `JobsPage.tsx` reads that param on mount (via `useSearchParams`, matching this codebase's
existing query-param convention used for tab routing elsewhere) and calls the existing
`setUploadOpen(true)` (already at `JobsPage.tsx:790`) to open the same dialog used by its own
"New migration" button — no new dialog implementation, no duplicated upload logic. The "or view
existing migrations" link navigates to plain `/jobs`, no query param, dialog stays closed.
- [x] done — verified live: CTA navigates to `/jobs?upload=1`, dialog opens automatically, param
  strips from the URL afterward (via `setSearchParams(..., { replace: true })`, so back/forward
  navigation doesn't reopen it). Secondary link navigates to `/jobs` with the dialog closed.

### S-D: Wire the route
**File:** `src/frontend/src/App.tsx`
**Depends on:** S-B
**Done when:** `<Route path="/" element={<Navigate to="/jobs" replace />} />` is replaced with
`<Route path="/" element={<WelcomePage />} />` (lazy-imported, matching the pattern already used
for `DocsPage`/`ExplainPage`/etc. in this file).
- [x] done — `Navigate` import removed from `App.tsx` since nothing else used it.

### S-E: Manual smoke test
**Depends on:** S-C, S-D
**Done when:** verified live — `/` shows the welcome page correctly in light and dark theme;
sidebar shows no active nav item while on `/`; clicking "New migration" navigates to `/jobs` and
the upload dialog opens automatically; clicking "or view existing migrations" navigates to `/jobs`
with the dialog closed; the code-proof panel renders correctly at the two-column width and
collapses sensibly at narrow widths; no console errors.
- [x] done — verified live via browser automation: page matches mockup, both light and dark theme
  confirmed (dark mode's Reconciled badge double-checked at full zoom — legible, correctly using
  the app's established dark-mode tone-success tokens), CTA and secondary link both confirmed
  working, no console errors on load or navigation.

### S-F: `make test` gate
**Depends on:** S-E
**Done when:** `make test` exits 0 (ruff, mypy, pytest+coverage, tsc, frontend-lint,
frontend-build all green).
- [x] done — all 7 gates green, exit code 0.

## Dependencies on other features

- None strictly blocking — `WelcomePage.tsx` reuses the live `<AppSidebar />` component directly
  rather than reimplementing it, so it automatically reflects whatever state F95 (#52, PR #158)
  and the logo-mark fix (PR #157) land in, regardless of merge order.

## Out of scope for this feature

- Live migration counts/stats on the welcome page (locked decision — static only)
- A "browse demo scenarios" secondary path (locked decision — no persistent demo library exists)
- Generalizing the copy toward multiple source/target languages (locked decision — stay concrete
  to SAS→Python, the actual current capability)
- A one-time-only "first visit" flag — `/` always renders the welcome page on every visit, since
  P0's actual workflow is opening it fresh at the start of every demo session, not a single
  lifetime onboarding moment
