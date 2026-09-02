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
- [ ] done

### S-A: Global sidebar
**File:** `src/frontend/src/components/AppSidebar.tsx`
**Depends on:** none
**Done when:** `.brand-manifest` applied unconditionally (global chrome, every route); hardcoded
colors/radii audited and fixed.
- [ ] done

### S-B: Jobs list ("Migrations")
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-A
**Done when:** scope applied; job-status pills migrated to `StatusChip`/`status-colors.ts`;
remaining hardcoded colors audited and fixed.
- [ ] done

### S-C: ETL tab
**File:** `src/frontend/src/components/JobDetail/ETLTab.tsx` + `TargetGraph.tsx` +
`FileNodeCard.tsx` + `BlockCodePopup.tsx`, `BlockDetailPanel.tsx`, `BlockInspectorPanel.tsx`,
`FileBlockListPanel.tsx`, `FileViewPopup.tsx`, `PipelineStepPanel.tsx`, `PythonModulePanel.tsx`
**Depends on:** none
**Done when:** scope applied; hardcoded `text-green-700`/`text-amber-700`/`text-red-700` changelog
counts routed through the tone system; nested panels audited; `BlockPlanTable` (already themed)
confirmed to still render correctly inside the now-scoped container.
- [ ] done

### S-D: Data tab
**File:** `src/frontend/src/components/JobDetail/DataStorageTab.tsx` + `DataStorageERD.tsx` +
`DataModelERD.tsx`
**Depends on:** none
**Done when:** scope applied + hardcoded colors/radii audited and fixed.
- [ ] done

### S-E: Lineage
**File:** `src/frontend/src/pages/GlobalLineagePage.tsx` + `src/frontend/src/components/LineageGraph.tsx`
**Depends on:** none
**Done when:** scope applied to both call sites (standalone Lineage page + embedded ETL-tab view);
hardcoded colors/radii audited and fixed. `LineageTab.tsx`'s dead-code status noted in
`journal/BACKLOG.md` as a future cleanup item, not deleted here.
- [ ] done

### S-F: Docs page
**File:** `src/frontend/src/pages/DocsPage.tsx`
**Depends on:** none
**Done when:** scope applied + hardcoded colors/radii audited and fixed.
- [ ] done

### S-G: Explain page
**File:** `src/frontend/src/pages/ExplainPage.tsx` + `src/frontend/src/components/Explain/MessageList.tsx`,
`EmptyState.tsx`, `ChatInput.tsx`
**Depends on:** none
**Done when:** scope applied + hardcoded colors/radii audited and fixed (existing `rounded-xl`
usages already covered by the `.brand-manifest` `--radius-xl` fix from F89, no separate radius
work needed here).
- [ ] done

### S-H: Unconditional shell scoping
**File:** `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** S-C, S-D
**Done when:** the `activeTab === "plan"` conditional on `.brand-manifest` is removed and the scope
applies unconditionally to the shared header/shell.
- [ ] done

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
