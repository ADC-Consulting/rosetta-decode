# F90 — Roll the "Manifest" design system out to the rest of the frontend

**Phase:** 3
**Area:** Frontend
**Status:** in-progress

## Goal

F87–F89 built and fidelity-checked the "Manifest" visual direction (Archivo + Space Mono fonts,
teal accent, 6px radius, muted `--tone-*` palette, `--brand-paper` page background) but scoped it
to only the Plan tab and `BlockPlanTable`, via a `.brand-manifest` CSS class in
`src/frontend/src/index.css`. Every other surface in the app still renders the original stock
shadcn theme. This feature rolls Manifest out to the rest of the frontend so the whole app reads
as one consistent product.

Corrections to the scope named in `journal/BACKLOG.md`'s prior follow-up note, found by
re-verifying actual wiring this session: the five per-job chevron tabs are `plan` (done) / `etl` /
`data-storage` / `bi` / `ai` — not a `lineage` tab; `bi`/`ai` are static "Coming soon" placeholders.
`components/JobDetail/LineageTab.tsx` is dead code (not imported anywhere) — the sidebar's
"Lineage" nav item actually routes to `pages/GlobalLineagePage.tsx` → `components/LineageGraph.tsx`
(also embedded inside the ETL tab).

Branch: `feat/F90-manifest-rollout`, stacked on `feat/F89-manifest-color-fidelity` (user's explicit
choice — F87/F88/F89 remain unmerged, PRs #136/#137/#138 open; F90's own PR will target F89).

## Acceptance Criteria

- [ ] Every surface listed in S-A through S-H visually matches the Manifest design language
      (fonts, teal accent, 6px radius, muted tone palette, `--brand-paper` background) in both
      light and dark theme
- [ ] No hardcoded Tailwind status colors remain in the touched files — all route through
      `status-colors.ts`/`StatusChip`
- [ ] Zero regression in already-themed surfaces (Plan tab, `BlockPlanTable`) or in shared
      components' rendering on surfaces intentionally left out of scope
- [ ] `make test` exits 0
- [ ] ruff and mypy pass (no backend changes expected, but gate still runs)

## Subtasks

### S-0: Preserve the mockup source in the repo
**File:** `docs/design/Manifest.dc.html` (new)
**Depends on:** none
**Done when:** the `.dc.html` source is re-extracted from the published Claude Artifact
(`https://claude.ai/code/artifact/f6b16ae8-8302-4011-b57c-13ddff839450`) via the design skill's
`seed-canvas.mjs --extract` flow and committed under `docs/design/`, so the mockup has a durable,
version-controlled reference independent of the artifact link staying reachable.
- [x] done — extracted and verified (`--ink:#101314`, `--paper:#f6f8f8`, `--green:#137a52`,
  `--amber:#a15c00`, `--sans:'Archivo'`, `--r:6px` all present) before committing

### S-A: Global sidebar
**File:** `src/frontend/src/components/AppSidebar.tsx`
**Depends on:** none
**Done when:** `.brand-manifest` applied unconditionally (global chrome, every route); hardcoded
colors/radii audited and fixed.
- [x] done — `.brand-manifest` added to the root `<aside>`; the logo square's bare `rounded`
  (Tailwind's own static 0.25rem default, confirmed via compiled CSS to never resolve through
  `var(--radius)`) changed to `rounded-md` so it participates in the token system going forward
  (resolves to 4px inside the scope — visually unchanged). No hardcoded colors found; the file
  already used semantic shadcn classes throughout. Verified in-browser: sidebar renders Archivo,
  main content area (Migrations list) unaffected, both themes, `make test` green.

### S-B: Jobs list ("Migrations")
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-A
**Done when:** scope applied; job-status pills migrated to `StatusChip`/`status-colors.ts`;
remaining hardcoded colors audited and fixed.
- [x] done — found three separate hand-rolled status-color systems in this file (`TableStatus`'s
  shimmer gradient + solid text, `UploadStatusBadge`'s pill, plus a file-type badge helper that
  was correctly left alone as out-of-scope — file-type/target-marker chips aren't status tones).
  Warning/success/danger routed through `TONE_HEX`/`TONE_TEXT_CLASS`/raw `--tone-*` vars; the
  shimmer `@keyframes` animation and blue/slate non-tone gradient stops (queued/running) preserved
  untouched. Verified in-browser: shimmer still animates, colors read as the muted Manifest
  palette in both themes (`#b5680d` warning / `#137a52` success / `#b3261e` danger light,
  `#4ade9a` success / muted red danger dark), `make test` green.

### S-C: ETL tab
**File:** `src/frontend/src/components/JobDetail/ETLTab.tsx` + `TargetGraph.tsx` +
`FileNodeCard.tsx` + `BlockCodePopup.tsx`, `BlockDetailPanel.tsx`, `BlockInspectorPanel.tsx`,
`FileBlockListPanel.tsx`, `FileViewPopup.tsx`, `PipelineStepPanel.tsx`, `PythonModulePanel.tsx`
**Depends on:** none
**Done when:** scope applied; hardcoded `text-green-700`/`text-amber-700`/`text-red-700` changelog
counts routed through the tone system; nested panels audited; `BlockPlanTable` (already themed)
confirmed to still render correctly inside the now-scoped container.
- [x] done — scoped `ETLTab.tsx`'s root; `TargetGraph.tsx`/`FileNodeCard.tsx` inherit via cascade
  (confirmed no portals). Fixed genuine status-tone duplicates in `ETLTab.tsx` (changelog counts),
  `BlockCodePopup.tsx` (`STATUS_CONFIG` map + 3 status banners), `BlockDetailPanel.tsx`
  (`ReconStatus`), `FileBlockListPanel.tsx` (summary + per-row dots), `PipelineStepPanel.tsx`
  (migration-status badges + "Feeds into" arrow/chip) — all routed through `TONE_CHIP_CLASS`/
  `TONE_TEXT_CLASS`. Left every blue interactive-link color untouched (different convention from
  the tone system, same rationale as the existing Strategy-chip decision), and left
  `human-verified`'s hardcoded teal alone (not a `Tone` member). Verified in-browser (graph summary
  bar, side-panel colors), `make test` green.
  - **New finding, not fixed here (needs a decision):** `BlockCodePopup.tsx`/`FileViewPopup.tsx`
    use shadcn `Dialog`, which portals to `document.body` — outside any `.brand-manifest` DOM
    subtree, so these dialogs render stock (unthemed) when opened regardless of scoping their
    trigger's container. `PlanTab.tsx`'s own `Dialog` (already shipped in F88) has the identical
    gap. Logged as a new backlog follow-up rather than expanding this subtask's scope.
  - **New finding, not fixed here:** `blockStatusHelpers.ts`'s `STATUS_CONFIG` (consumed by
    `BlockDetailPanel.tsx`, `FileBlockListPanel.tsx`, and `blockRowHelpers.tsx`'s shared `BlockRow`)
    has the same hand-rolled `bg-green/amber/red/teal-100` pattern one level removed via import —
    a per-file grep on this subtask's file list didn't surface it. Logged as a follow-up.

### S-D: Data tab
**File:** `src/frontend/src/components/JobDetail/DataStorageTab.tsx` + `DataStorageERD.tsx` +
`DataModelERD.tsx`
**Depends on:** none
**Done when:** scope applied + hardcoded colors/radii audited and fixed.
- [x] done — scoped the root plus all three early-return guard states (loading/empty), since
  `JobDetailPage.tsx`'s shell scoping isn't unconditional yet (S-H). `DataStorageERD.tsx` turned
  out to be dead code (not imported anywhere) — the tab actually renders `DataModelERD.tsx` +
  `DataFlowDiagram.tsx`, both confirmed clean of hardcoded colors and no portal usage. Fixed 7
  genuine status-tone duplicates (migrated/changed dots + badges, added/dropped diff markers,
  "estimated from SAS" warning chip); left PK/FK/schema-kind badges alone (structural, not status
  tones — same rationale as file-type badges in S-B). Verified in-browser both themes, `make test`
  green.

### S-E: Lineage
**File:** `src/frontend/src/pages/GlobalLineagePage.tsx` + `src/frontend/src/components/LineageGraph.tsx`
**Depends on:** none
**Done when:** scope applied to both call sites (standalone Lineage page + embedded ETL-tab view);
hardcoded colors/radii audited and fixed. `LineageTab.tsx`'s dead-code status noted in
`journal/BACKLOG.md` as a future cleanup item, not deleted here.
- [x] done — scoped `GlobalLineagePage.tsx`'s root; `LineageGraph.tsx` left untouched (confirmed no
  `createPortal` usage, inherits scope via cascade from either ancestor). No Tailwind-class-level
  hardcoded colors found. **New finding, not fixed here:** `LineageGraph.tsx`'s `STATUS_STYLE`/
  `STATUS_SYMBOL` maps drive node border/glyph color via literal inline-style hex (`#22c55e`/
  `#f59e0b`/`#ef4444` — the exact success/warning/danger triad) with no existing dark-mode
  handling at all. This is a bigger, self-contained fix (a 1294-line shared component) than a
  drive-by swap warrants — logged as a follow-up rather than expanding this subtask. Verified
  in-browser: standalone Lineage page renders Archivo/scoped correctly; embedded ETL-tab lineage
  view unaffected (file untouched).

### S-F: Docs page
**File:** `src/frontend/src/pages/DocsPage.tsx`
**Depends on:** none
**Done when:** scope applied + hardcoded colors/radii audited and fixed.
- [x] done — scoped the root; fixed `ConfidenceBadge`/`RiskBadge`'s hand-rolled maps (via
  `CONFIDENCE_TONE`/`RISK_TONE` + a new bordered chip variant preserving the existing pill's
  visible border), the `text-emerald-500` "Accepted" label (same F87/F89 emerald-vs-green bug
  pattern), and `DocCard`'s auto-verified/needs-review/failed count colors (found during the
  audit, same duplication). Verified in-browser: badges and counts render the muted tone palette
  correctly in both themes.

### S-G: Explain page
**File:** `src/frontend/src/pages/ExplainPage.tsx` + `src/frontend/src/components/Explain/MessageList.tsx`,
`EmptyState.tsx`, `ChatInput.tsx`
**Depends on:** none
**Done when:** scope applied + hardcoded colors/radii audited and fixed (existing `rounded-xl`
usages already covered by the `.brand-manifest` `--radius-xl` fix from F89, no separate radius
work needed here).
- [x] done — scoped the root (single one-line change, no early-return states in this file). Zero
  hardcoded status colors found in `ExplainPage.tsx` or the three `components/Explain/*` files;
  confirmed no portal usage in any of them. **New finding, not fixed here:** `ExplainPage.tsx`
  itself renders a shadcn `Dialog` (mode-switch confirmation) that portals to `document.body` —
  same already-tracked gap as `BlockCodePopup.tsx`/`FileViewPopup.tsx`/`PlanTab.tsx`'s dialogs, not
  a new backlog item. Verified in-browser: page renders Archivo/scoped correctly, both themes.

### S-H: Unconditional shell scoping
**File:** `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** S-C, S-D
**Done when:** the `activeTab === "plan"` conditional on `.brand-manifest` is removed and the scope
applies unconditionally to the shared header/shell.
- [x] done — split the previously-bundled conditional: `brand-manifest` now always applied; `px-4`
  (Plan-tab-specific spacing to match `PlanTab.tsx`'s own padding, a 40px-total-inset decision
  unrelated to theming) stays gated on `activeTab === "plan"` so ETL/Data/BI/AI keep their shared
  24px unchanged. Verified via `getBoundingClientRect`: Plan tab still has `px-4` present, BI tab
  correctly does not, both have `brand-manifest`. Confirmed no other `activeTab === "plan"` gate
  on theming exists elsewhere in the file. `make test` green.

### S-I: Full manual smoke test
**Depends on:** S-A, S-B, S-C, S-D, S-E, S-F, S-G, S-H
**Done when:** every surface verified in light + dark theme, single consistent design language
app-wide, no remaining stock-shadcn islands, no regressions in Plan tab/`BlockPlanTable`.
- [ ] done

### S-J: Gate
**Depends on:** S-I
**Done when:** `make tsc-check && make frontend-lint && make frontend-build && make test` all exit
0.
- [ ] done

## Dependencies on other features

- Builds on F87 (`status-colors.ts`/`StatusChip` consolidation), F88 (`.brand-manifest` mechanism),
  F89 (color/radius fidelity, locked Tailwind v4 derived-token scoping pattern)

## Out of scope for this feature

- `bi`/`ai` placeholder tab content (no real UI to theme yet)
- Deleting the dead `components/JobDetail/LineageTab.tsx` file (noted, not acted on)
- Any backend/worker/API changes
