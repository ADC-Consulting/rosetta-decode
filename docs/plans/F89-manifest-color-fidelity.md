# F89 — Manifest color fidelity: muted palette + page background + tone cleanup

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

Direct computed-color comparison against the approved "Manifest" mockup (this session) found that
F88 only changed *shape* (radius/border) via `status-colors.ts`, never the actual color values —
the deployed Plan tab still renders F87's original stock Tailwind semantic colors (green `#22c55e`,
amber `#f59e0b`, red `#e7000b`) instead of the mockup's deliberately muted palette (green `#137a52`,
amber `#a15c00`, red `#b3261e`). The page background is also flat white, identical to the card, so
the card doesn't read as sitting on a page the way the mockup's subtly off-white background (`#f6f8f8`)
achieves. A follow-up color-usage audit found two more real inconsistencies to fix alongside this:
`BeforeYouAcceptPanel.tsx` hardcodes `text-emerald-700` for a success message instead of using the
shared `success` tone (same meaning as the green used everywhere else — F87 missed unifying it),
and the `caution` tone (orange, used only for criticality tier "high") is visually redundant next
to `warning` (amber) — user decided to merge `caution` into `warning`, dropping to 5 tones.

`status-colors.ts` / `StatusChip` / `StatusBadge` are shared components also used **outside** the
Plan tab (`LiveTraceDialog.tsx`, `DocsPage.tsx`), so this must preserve F88's "scoped to Plan tab +
BlockPlanTable only" rule — non-Plan-tab usages must render pixel-identical to today. Done looks
like: Plan tab colors match the Manifest mockup's muted palette in both themes, the page/card
background contrast is visible, `caution` no longer exists as a tone, the emerald bug is fixed, and
every other consumer of the shared color system is untouched.

## Acceptance Criteria

- [x] `success`/`warning`/`danger`/`danger-strong` tone colors inside the Plan tab match the
      Manifest mockup's muted hex values in light theme, with a legible dark-theme equivalent that
      preserves the same muted character (not stock Tailwind brightness)
- [x] Every non-`.brand-manifest` consumer of `status-colors.ts`/`StatusChip` (e.g. `LiveTraceDialog`,
      `DocsPage`) renders pixel-identical colors to before this feature
- [x] Plan tab page background is visibly distinct from the unified summary card's white background
      in both themes
- [x] `caution` tone removed entirely from `status-colors.ts` (type, class maps, and
      `CRITICALITY_TONE.high` now maps to `warning`); zero remaining references anywhere (a related
      orphaned `text-orange-700` in `BlockPlanTable.tsx`'s criticality legend was also found and fixed)
- [x] `BeforeYouAcceptPanel.tsx`'s success message uses `TONE_TEXT_CLASS.success`, not a hardcoded
      `text-emerald-700`
- [x] `make tsc-check`, `make frontend-lint`, `make frontend-build` all exit 0
- [x] `make test` exits 0
- [x] Manual smoke test in light + dark theme confirms the above, plus zero bleed outside the
      Plan tab scope

## Subtasks

### S-A: Scoped tone CSS custom properties
**File:** `src/frontend/src/index.css`
**Depends on:** none
**Done when:** for each of `success`/`warning`/`danger`/`danger-strong`, a `--tone-X` (foreground)
and `--tone-X-bg` (background) pair is defined twice: once at `:root`/`.dark` with values matching
the *current* stock Tailwind hex equivalents (green-700/50, amber-700/50, red-700/50, red-800/100)
so nothing outside `.brand-manifest` changes; once inside `.brand-manifest` (plus a dark-mode-aware
variant, e.g. `:is(.dark) .brand-manifest` or equivalent) with the new muted Manifest values
(`#137a52`/`#e3f3ec`, `#a15c00`/`#fbedd8`, `#b3261e`/`#fbe4e1`, plus a deeper muted red for
`danger-strong`). Also add a `--brand-paper` token to `.brand-manifest` (light ~`#f6f8f8`
equivalent; a suitable dark equivalent) for the page-background layer. `neutral` tone is
unaffected — it already uses shadcn's `muted`/`muted-foreground` tokens and needs no override.
- [x] done

### S-B: Apply `--brand-paper` as the Plan tab page background
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-A
**Done when:** the Plan tab's root container (already wrapped in `brand-manifest`) sets its
background to `var(--brand-paper)` instead of the default page white, so the white unified summary
`Card` visibly sits on a subtly distinct background, matching the mockup's depth.
- [x] done

### S-C: `status-colors.ts` → reference the new tone CSS variables
**File:** `src/frontend/src/components/JobDetail/status-colors.ts`
**Depends on:** S-A
**Done when:** `TONE_CHIP_CLASS`/`TONE_TEXT_CLASS`/`TONE_HEX` for `success`/`warning`/`danger`/
`danger-strong` reference `var(--tone-X)`/`var(--tone-X-bg)` via Tailwind arbitrary-value classes
(e.g. `bg-[var(--tone-success-bg)] text-[var(--tone-success)]`) instead of hardcoded Tailwind color
classes — same pattern already proven correct for `--primary` in F88 (raw custom property
reference, not a derived/baked theme token, avoiding the indirection bug found in F88). Semantic
tone→value mapping (which confidence band/strategy/risk maps to which tone) unchanged here.
- [x] done

### S-D: Merge `caution` tone into `warning`
**File:** `src/frontend/src/components/JobDetail/status-colors.ts`
**Depends on:** S-C
**Done when:** `"caution"` is removed from the `Tone` union type and from
`TONE_CHIP_CLASS`/`TONE_TEXT_CLASS`/`TONE_HEX`; `CRITICALITY_TONE.high` changes from `"caution"` to
`"warning"`; grep confirms zero remaining references to `"caution"` in the frontend.
- [x] done

### S-E: Fix `BeforeYouAcceptPanel.tsx` emerald/green inconsistency
**File:** `src/frontend/src/components/JobDetail/BeforeYouAcceptPanel.tsx`
**Depends on:** S-C
**Done when:** the hardcoded `text-emerald-700` success-message color is replaced with
`TONE_TEXT_CLASS.success` imported from `status-colors.ts` — single source of truth, no new
hardcoded color.
- [x] done

### S-F: Manual smoke test
**Depends on:** S-B, S-D, S-E
**Done when:** dev server run; Plan tab visually compared against the Manifest mockup in light AND
dark theme — status colors read as muted (not stock-Tailwind-bright), page background visibly
distinct from the card, criticality shows no orange tier. `LiveTraceDialog` and `DocsPage`
spot-checked to confirm zero color change outside the Plan tab scope.
- [x] done — frontend-builder verified via `getComputedStyle` in both themes (confidence text
  `#137a52` light / `#4ade9a` dark, risk text `#a15c00` light / `#e0a94a` dark, page bg `#f6f8f8`
  light / `#1c2321` dark vs. white/dark card) and confirmed `LiveTraceDialog`/`DocsPage` colors
  unchanged (stock Tailwind red-700/green-600). Orchestrator re-confirmed visually in both themes
  on the live app — muted palette, visible page/card contrast, teal accent, no orange anywhere.

### S-G: Full gate
**Depends on:** S-F
**Done when:** `make tsc-check && make frontend-lint && make frontend-build && make test` all
exit 0.
- [x] done — `make test` (all 7 gates: ruff-check, ruff-format, mypy, pytest+coverage, tsc,
  frontend-lint, frontend-build) exits 0

## Pre-commit fidelity review fixes

A pre-commit color review (browser `getComputedStyle` + className inspection on the "KYC / AML
Client Screening" job, `/jobs/dec0de00-0000-4000-8000-000000000003?tab=plan`) found 3 elements in
`PlanTab.tsx` that S-C missed — they didn't import/use `status-colors.ts` at all and still used
hardcoded stock Tailwind color classes, clashing with the muted chips already fixed next to them:

1. **`StatCard`** (the 4 tiles: Auto-verified / Needs review / Manual TODO / Failed
   reconciliation) — `colorClasses` prop was hardcoded per call site
   (`text-green-700 bg-green-50 border-green-200`, etc.). Replaced each call site's `colorClasses`
   with `TONE_CHIP_CLASS.success` / `.warning` / `.warning` / `.danger` respectively — Manual TODO
   was mapped to `warning` (not `neutral`) because its pre-existing hardcoded color was amber,
   matching Needs review, not gray; Failed reconciliation's `red-700/50/-200` matches the `danger`
   tone's pre-F89 stock-equivalent values exactly. The component's existing zero-count override
   (`text-muted-foreground bg-muted`) is untouched and still takes precedence when a tile's count
   is 0.
2. **"Sensitive data detected" heading** — replaced hardcoded `text-red-600` with
   `TONE_TEXT_CLASS.danger` (both already imported/available from `./status-colors`).
3. **"N dependencies were unavailable during translation" banner** (accepted-state) — replaced
   hardcoded `border-amber-200`/`bg-amber-50`/`text-amber-800`/`text-amber-700`/`text-amber-600`
   with `border-[var(--tone-warning)]/20` / `bg-[var(--tone-warning-bg)]` / `TONE_TEXT_CLASS.warning`
   (applied uniformly in place of the three different stock amber shades, consistent with how the
   rest of the tone system uses one shade per tone).

Verified via `getComputedStyle` in both themes on the live app:

| Element | Light | Dark |
|---|---|---|
| Auto-verified tile | `#137a52` / bg `#e3f3ec` | `#4ade9a` / bg `rgba(74,222,154,.12)` |
| Needs review / Manual TODO tiles | `#a15c00` / bg `#fbedd8` | `#e0a94a` / bg `rgba(224,169,74,.12)` |
| Sensitive data detected text | `#b3261e` | `#e2867f` |
| Dependencies-unavailable banner text | `#a15c00` | `#e0a94a` |
| Dependencies-unavailable banner bg | `#fbedd8` | `rgba(224,169,74,.12)` |

All 4 `StatCard` tiles confirmed to resolve color through the tone system (regex check for
`text-(green|amber|red)-\d` on the rendered className returned no matches). `LiveTraceDialog.tsx`
and `DocsPage.tsx` were not touched by this fix (nor was `status-colors.ts`/`index.css`), so they
remain pixel-identical.

4. **"N missing dependencies detected" banner (non-accepted state)** — the follow-up noted above is
   now fixed too: replaced hardcoded `border-amber-200`/`bg-amber-50`/`text-amber-600`/
   `text-amber-800`/`text-amber-700` (heading icon, heading text, list items, ref-count spans, and
   the "Re-upload with these files included..." footer line) with the same
   `border-[var(--tone-warning)]/20 bg-[var(--tone-warning-bg)]` container + `TONE_TEXT_CLASS.warning`
   pattern already applied to its accepted-state sibling. Verified via `getComputedStyle` on job
   `87c49247-f9c8-4a2e-b374-1f6a9f1f7d4a` (proposed status, 7 missing dependencies): heading/footer
   text `rgb(161, 92, 0)` (`#a15c00`), container bg `rgb(251, 237, 216)` (`#fbedd8`) — matches the
   warning tone exactly in light theme. `make tsc-check`, `make frontend-lint`, `make frontend-build`
   all exit 0 after this fix.

`make tsc-check`, `make frontend-lint`, `make frontend-build` all exit 0. Not committed per
instructions — awaiting orchestrator review alongside the rest of F89.

5. **`--radius-lg`/`--radius-md`/`--radius-sm` indirection bug** — same root cause class as the
   `--color-primary` bug F88 fixed, but for radius instead of color. `@theme`'s
   `--radius-lg: var(--radius); --radius-md: calc(var(--radius) - 2px); --radius-sm: calc(var(--radius) - 4px);`
   derive once at `:root` and don't re-resolve through `.brand-manifest`'s `--radius: 6px`
   override, so every `rounded-lg` element inside the Plan tab scope (status chips, criticality
   pills, stat tiles, block cards) was still rendering at the stale default `10px`
   (`0.625rem`) instead of `6px`. Note the `.brand-manifest` block's own top comment already
   *claimed* it redeclares `--radius-lg/md/sm` — it didn't; this fix makes that comment true.
   Fixed in `src/frontend/src/index.css` by adding the same three derived-token declarations
   (same formulas) directly inside `.brand-manifest`, referencing its own `--radius: 6px`.
   Unlike the tone tokens, no `.dark .brand-manifest` counterpart was needed — `--radius` itself
   is never given a separate dark-mode value, so the single declaration resolves correctly in
   both themes (verified). Verified via `getComputedStyle` on job
   `dec0de00-0000-4000-8000-000000000001`:

   | Element | Before | After (light) | After (dark) |
   |---|---|---|---|
   | "Needs Review" status chip | `--radius-lg` `0.625rem` / `borderRadius` `10px` | `--radius-lg` `6px` / `borderRadius` `6px` | `--radius-lg` `6px` / `borderRadius` `6px` |
   | Stat tiles (Auto-verified, Needs review, Manual TODO, Failed reconciliation) | `10px` | `6px` | `6px` |
   | Criticality pills (medium/low) | `10px` | `6px` | `6px` |
   | Block cards | `10px` | `6px` | `6px` |

   Spot-checked `/jobs` (outside `.brand-manifest`, both themes): `--radius-lg` still
   `0.625rem`, `borderRadius` still `10px`/`8px` per button variant — zero bleed. `make
   tsc-check`, `make frontend-lint`, `make frontend-build` all exit 0 after this fix. Not
   committed per instructions.

## Post-commit follow-up fixes (2026-08-27, after F89 landed)

User review of the merged F89 work found two more gaps, fixed in a follow-up commit on this branch:

1. **Plan tab content padding was near-zero.** The `.brand-manifest` root in `PlanTab.tsx` had
   `padding: 0 0 24px 0` — no left/right/top padding of its own, relying entirely on an outer
   generic scroll container (`px-6 py-2`) tuned for the old tighter layout. Result: description
   text and other top-level content rendered almost touching the left and top edges. Fixed by
   adding explicit `px-8 md:px-11 pt-6` to the `.brand-manifest` root, giving comfortable spacing
   consistent with the header above it.
2. **`StatusBadge`'s job-status pill colors didn't match the muted palette.** The "Needs Review"
   badge (and other job-status states) used `STATUS_PILL_CLASS` in `constants.ts` — hardcoded
   stock Tailwind (`bg-amber-500`, `bg-emerald-600`, `bg-red-600`), a deliberately separate color
   domain from `status-colors.ts` per F88's design (job status vs. block-level tone). Visually,
   though, a bright stock amber badge sitting next to muted `--tone-warning` chips on the same
   page read as a clash, not a deliberate distinction. Fixed by pointing the amber/green/red
   entries at the same `--tone-warning`/`--tone-success`/`--tone-danger` CSS variables (via raw
   `var()` arbitrary-value classes) already used by `status-colors.ts` — these resolve to the
   stock defaults outside `.brand-manifest` (zero bleed to the jobs list, other tabs) and to the
   muted values inside it. `queued` (slate) and `running` (blue) were left untouched — not part of
   the red/amber/green semantic family.

Verified via `getComputedStyle` and screenshots in both themes on two jobs (Needs Review and
Accepted states); confirmed zero bleed on the jobs list page. `make tsc-check`/`frontend-lint`/
`frontend-build` all exit 0.

## Dependencies on other features

- F87 (design-consistency-shared-primitives) — builds on its `status-colors.ts`/`StatusChip`
  consolidation
- F88 (manifest-design-system) — builds on its `.brand-manifest` scoping mechanism and the
  raw-custom-property-reference pattern that avoids the `--color-primary` indirection bug

## Out of scope for this feature

- Any color change outside `.brand-manifest`'s scope (Plan tab + `BlockPlanTable`) — explicit
  constraint carried over from F88
- Rolling the Manifest palette out to other tabs/pages — still an explicit follow-up, not this
  feature
- The `blue` "Translated" strategy pill color in `BlockPlanTable.tsx` — intentionally left outside
  the shared tone system per the approved mockup, not a bug
