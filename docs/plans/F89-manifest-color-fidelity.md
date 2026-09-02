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

## Fine-toothed-comb polish fixes (2026-08-27)

A follow-up design audit (browser-verified with `getBoundingClientRect`/`getComputedStyle`) found
5 more concrete Plan tab issues, all fixed on this branch:

1. **Header/body 44px left-edge misalignment (HIGH).** The previous "near-zero padding" fix
   (above) added `px-8 md:px-11 pt-6` to `PlanTab.tsx`'s `.brand-manifest` root without checking it
   against the sticky header row's own padding in `JobDetailPage.tsx`. Both the header and
   `PlanTab.tsx`'s content root sit inside the same outer scroll container
   (`px-6 py-2` in `JobDetailPage.tsx`), and the header adds **zero** padding of its own beyond
   that — confirmed via `getBoundingClientRect` (`left: 244` for both the sticky header row and the
   `.brand-manifest` box, `paddingLeft: "0px"` on the header). `PlanTab.tsx`'s extra `md:px-11`
   (44px) was therefore pure double-padding, pushing content to `left: 288`, a 44px zig-zag against
   the header. Fixed by removing the horizontal padding classes from `PlanTab.tsx`'s root
   (`px-8 md:px-11` → none — vertical `pt-6 pb-6` kept), letting it rely on the same outer `px-6`
   the header uses. Verified both rows now measure `left: 244` in both jobs and both themes (0px
   delta, not just within tolerance).
2. **"Needs attention" → Table view truncated Step ID/Source file (MEDIUM-HIGH).** The
   `AttentionTable` component in `PlanTab.tsx` had `max-w-[160px] truncate` on the Step ID and
   Source file `<td>`s, cutting off identifiers despite visible unused width to the right of the
   Blast radius column — Cards view showed the same identifiers in full. Root cause was the fixed
   `max-w-[160px]` cap itself (the table has no `table-layout: fixed`, so this wasn't a
   layout-algorithm issue). Fixed by removing `max-w-[160px] truncate` and using
   `whitespace-nowrap` instead, so the columns grow to fit their content like the others. Verified
   on both jobs (both themes) — full step IDs/file paths render, table still fits within its
   `overflow-x-auto` wrapper.
3. **"Filter by Strategy" pills didn't match the Strategy column's chip style (MEDIUM).** In
   `BlockPlanTable.tsx`, the filter pills were plain `rounded-full` outline buttons with no color
   coding, while the Strategy column's data cells render the same three labels as filled
   `rounded-lg` (6px) tone-colored chips (blue/amber/red). Fixed by adding a
   `STRATEGY_PILL_SELECTED_CLASS` map (`manual`→red, `translated_with_review`→amber,
   `translated`→blue — the exact same Tailwind classes the Strategy cell already hardcodes) and
   switching the pill shape from `rounded-full` to `rounded-lg`; unselected stays the existing
   neutral outline. Verified via `getComputedStyle` that a selected pill's background/text/radius
   are byte-identical (`oklch(...)` values match exactly) to the corresponding Strategy column
   chip, for all three strategies (Translated, Review needed, Manual), in both themes.
4. **Off-grid icon size (LOW-MEDIUM).** The "Sensitive data detected" warning triangle in
   `PlanTab.tsx` rendered at `size={15}`, off the page's established 12/14/18px cluster. Changed to
   `size={14}`. Verified via the rendered `<svg>`'s `width`/`height` attributes (`14`).
5. **Inconsistent banner heading weight (LOW).** The "N dependencies were unavailable"/"N missing
   dependencies detected" banner headings in `PlanTab.tsx` (both the non-accepted and accepted-state
   variants) used `font-medium` (500) while "Delivered — Accepted"/"Needs attention"/"Steps" use
   `font-semibold` (600) for the same "bold statement in a colored callout" role. Changed both
   banner headings' `font-medium` → `font-semibold`. Verified via `getComputedStyle` —
   `fontWeight: "600"` on the accepted-state banner ("2 dependencies were unavailable during
   translation") on the KYC/AML job.

Verified end-to-end on both `dec0de00-0000-4000-8000-000000000001` (Needs Review) and
`dec0de00-0000-4000-8000-000000000003` (Accepted) in both light and dark theme. `make tsc-check`,
`make frontend-lint`, `make frontend-build`, and `make test` (all 7 gates) all exit 0.

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

## Content margin + attention-cards grid fixes (2026-08-27, later same day)

Two more gaps found against the approved Manifest mockup, fixed on this branch:

1. **Content margin too tight (25px from sidebar).** The fine-toothed-comb fix above (item 1)
   correctly resolved a header/body *misalignment* bug by removing `PlanTab.tsx`'s horizontal
   padding entirely, but that incidentally reverted the margin to the outer scroll container's bare
   `px-6` (24px) — both header and body now aligned, but both tight (`getBoundingClientRect`
   confirmed sidebar `right: 220`, content `left: 244`, a 24-25px gap). Fixed by adding a matching
   `px-4` (16px) on top of the shared `px-6`, in both places, so the delta stays identical and both
   stay aligned: `JobDetailPage.tsx`'s sticky header row gets `px-4` appended to its existing
   `activeTab === "plan" && "brand-manifest"` conditional (now `"brand-manifest px-4"`, still scoped
   to the Plan tab only — ETL/Data/BI/AI keep the unmodified 24px), and `PlanTab.tsx`'s
   `.brand-manifest` root gets an unconditional `px-4` (it only renders for the Plan tab). Verified
   via `getBoundingClientRect` on both `dec0de00-0000-4000-8000-000000000001` and
   `...0003`, both themes: back button and description paragraph both measure `left: 260` (sidebar
   `right: 220` + 40px), and the ETL tab (no `brand-manifest`/`px-4`) still measures `left: 244`,
   confirming zero bleed to the other 4 tabs.
2. **"Needs attention" Cards view was single-column.** The approved mockup renders the individual
   attention cards in a 2-column grid (`grid-template-columns:repeat(2,minmax(0,1fr));gap:12px`);
   the live `AttentionCards` component in `PlanTab.tsx` stacked them full-width, one per row. Fixed
   by wrapping the `top5.map(...)` card list in a `grid grid-cols-2 gap-3` container (12px gap,
   matching the mockup; the "N manual steps" warning banner above and the "+N more · Show all"
   link below stay outside the grid, full-width). Verified on the Needs Review job (5 attention
   items, no "+more" link since `top5` already includes all 5): cards render 2+2+1 via
   `getBoundingClientRect` (rows at consistent `x: 260`/`828.5`, last card alone at `x: 260`); card
   text (step id, rationale, "View in steps table →") still reads fine at half-width in both light
   and dark theme on both jobs, including the KYC/AML job's longer rationale text (wraps to more
   lines, not truncated).

Verified via `getBoundingClientRect`/screenshots on `dec0de00-0000-4000-8000-000000000001` (Needs
Review) and `...0003` (Accepted), both light and dark theme. `make tsc-check`, `make frontend-lint`,
`make frontend-build`, and `make test` (all 7 gates) all exit 0.

## Post-commit fix: header row grouping didn't match the mockup

A closer re-read of the mockup source (`Manifest.dc.html`, not just a description of it — a prior
fidelity check relied on a mis-description and wrongly concluded no fix was needed) found the
mockup's header is 3 rows: (1) back arrow + title + status badge, (2) files/steps subtitle **with
the Accept/Download button on the same row**, (3) tab bar alone. The live app had the button
sharing a row with the tab bar instead (row 3), not the subtitle (row 2).

**Fix** (`src/frontend/src/pages/JobDetailPage.tsx`): restructured the header into the same 3 rows
— subtitle and the action-button cluster (Accept migration / Accepted badge + Download migration
package) now share one `justify-between` row; `ChevronTabBar` sits alone on the row below. This is
a structural change to shared header chrome (not a `.brand-manifest` color/font change), so it
applies uniformly across all 5 tabs rather than being conditionally scoped to Plan — confirmed via
screenshot that the ETL tab's header still reads sensibly with the new row grouping (in its normal
unstyled colors, as expected). Verified in light + dark theme on both the Needs Review and Accepted
jobs. `make test` (all 7 gates) exits 0.

## Post-commit fix: `warning` tone read as brown, not amber

Live review of the "Manifest" palette flagged that `warning` (used for "Needs Review"
badges/chips, medium/high risk and criticality tags, and the dependencies-unavailable banners)
read as **brown**, not amber, despite the hue angle being technically in the amber range. Root
cause: `--tone-warning: #a15c00` is `hsl(35, 100%, 32%)` — fully saturated but very
low-lightness, and a dark+saturated warm hue perceptually reads as brown regardless of hue.

**Fix** (`src/frontend/src/index.css`, `.brand-manifest` scope only):

| Token | Old | New | Reasoning |
|---|---|---|---|
| `--tone-warning` (light) | `#a15c00` — `hsl(35, 100%, 32%)` | `#b5680d` — `hsl(33, 87%, 38%)` | Lightness raised 32% → 38%, saturation eased 100% → 87%, landing near Tailwind `amber-700` (`#b45309`) rather than the loud stock `amber-500` (`#f59e0b`) this effort deliberately moved away from. |
| `--tone-warning` (dark, `.dark .brand-manifest`) | `#e0a94a` — `hsl(38, 71%, 58%)` | `#e6ab4c` — `hsl(36, 80%, 60%)` | Already reasonably light but read slightly muddy against the dark card; nudged hue/saturation for a cleaner, more legible gold-amber while staying muted. |

`--tone-warning-bg` (`#fbedd8` light / `rgba(224, 169, 74, 0.12)` dark) was checked against the
new, lighter foreground and left unchanged — contrast against the light pale-amber background is
~3.7:1 (down from ~4.5:1 with the old darker foreground, since a lighter foreground closes the gap
against an already-light background), which is above the 3:1 WCAG threshold for bold/large UI text
and chip labels (this token's only usage), and screenshots confirm it's clearly legible in both
themes. Widening the gap further would require lightening the background toward near-white,
diluting the pale-amber tint that gives the chips their identity, so it was left as-is.

Verified via `getComputedStyle` and screenshots in both themes on "Monthly Revenue Pipeline"
(Needs Review badge, Needs review stat tile, medium risk/criticality chips) and "KYC / AML Client
Screening" (Steps table `warning`-tone chips, dependencies-unavailable banner): the amber now
reads as a clear, warm, unambiguous warning signal in both light and dark theme, distinct from
brown. `success`/`danger`/`danger-strong`/`--brand-paper` were not touched. `make tsc-check`,
`make frontend-lint`, `make frontend-build`, and `make test` (all 7 gates) all exit 0.

## Post-commit fix: `--radius-xl` missed by the earlier radius-indirection fix

A fresh comparison against the published mockup artboard (not just eyeballing — computed styles
on the live app) found the Plan tab's main unified summary card (PII warning + confidence/risk
bars + stat tiles + criticality + "Before you accept") still rendering at a 12px corner radius
instead of the scoped 6px. Root cause: this card uses the shared shadcn `Card` primitive
(`src/frontend/src/components/ui/card.tsx`), whose base classes include `rounded-xl` — and the
earlier fix for this exact class of bug (see "Post-commit fix" further up, and the locked pattern
in `DECISIONS.md`) only redeclared `--radius-lg`/`-md`/`-sm` inside `.brand-manifest`, never
`--radius-xl`. Confirmed via `getComputedStyle`: `--radius` correctly resolved to `6px` inside the
scope, but `--radius-xl` still resolved to the stock `0.75rem` (12px).

Same card also had its 3px top accent strip hardcoded to `bg-red-500` (stock Tailwind red,
`oklch(0.637 0.237 25.331)`) instead of routing through `--tone-danger-strong` like every other
tone-driven color on the page — so it never picked up the muted Manifest red in light mode or the
correct dark-mode value.

**Fix:** added `--radius-xl: var(--radius);` alongside the existing `--radius-lg/-md/-sm`
declarations in `.brand-manifest` (`src/frontend/src/index.css`); changed the accent strip's class
from `bg-red-500` to `bg-[var(--tone-danger-strong)]` (`src/frontend/src/components/JobDetail/PlanTab.tsx`).
Did not touch `card.tsx` — kept the fix scoped via the CSS variable since `Card` is a shared
primitive used outside the Plan tab. Verified via `getComputedStyle` in both themes: radius now
6px, strip color `#8f1c15` light / `#f0a099` dark (matching the existing `.brand-manifest`
`--tone-danger-strong` values). `make test` (all 7 gates) exits 0.

## Post-commit fix: "Needs attention" card cap was 5, not 3

Direct comparison against the mockup artboard found it caps the "Needs attention" card grid at 3
visible cards (2+1 in the 2-column grid) with a "+N more · Show all →" link taking the 4th grid
slot. The live `AttentionCards` component already had this exact mechanism (`top5`/`.slice(0, 5)`
+ a conditional "+N more" link) — it just wasn't missing, only miscalibrated to a cap of 5. The
test job used throughout this session's verification happened to have exactly 5 needs-attention
items, so `remaining` was always 0 and the "show all" link never rendered, making the feature look
entirely absent.

**Fix:** changed `.slice(0, 5)` to `.slice(0, 3)` in `AttentionCards`
(`src/frontend/src/components/JobDetail/PlanTab.tsx`), renaming `top5` → `top3` throughout the
function. Verified in-browser: the Needs Review job now shows exactly 3 cards + "+ 2 more · Show
all →", and clicking it correctly switches to the Table view showing all 5 rows. `make test` (all
7 gates) exits 0.
