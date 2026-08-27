# F88 — "Manifest" design system: Plan tab + ETL block table

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

F87 fixed internal component-reuse inconsistency in the JobDetail surfaces, but the "looks vibe
coded" feedback persisted — the app was consistently applying shadcn's unstyled defaults, not a
considered design. This session produced 3 concrete visual-direction mockups of the Plan tab (a
published design canvas Artifact) and the user picked **"Manifest"**: Archivo + Space Mono
typography, a teal brand accent distinct from the existing semantic red/amber/green, a consistent
6px radius scale, and one unified summary card in place of five stacked boxes with a top-edge
color bar replacing the boxed PII warning banner. See `journal/DECISIONS.md` (2026-08-26) for the
full rationale.

Rollout is intentionally scoped to the Plan tab and `BlockPlanTable` (the same surfaces F87
touched) — not the whole app. Done looks like: `PlanTab.tsx` and `BlockPlanTable.tsx` visually
match the "C — Manifest" mockup artboard, every other tab/page is pixel-identical to before this
feature (no bleed from the new tokens), and the existing F87 chip/color consolidation is preserved
underneath the new visual skin (no new duplicate color maps).

**Implementation approach for scoping:** the new fonts/accent/radius are added to
`index.css` as new, additively-named tokens plus a `.brand-manifest` CSS scope class that locally
overrides `--primary` / `--primary-foreground` / `--radius` / `--font-sans` *within that class's
DOM subtree only*. The global `:root` / `.dark` shadcn tokens consumed by every other page are
left untouched. `PlanTab.tsx`'s root and `BlockPlanTable.tsx` get wrapped in `brand-manifest`, so
existing shadcn primitives (`Button`, `Card`, etc.) already used in those files pick up the new
look for free via the CSS variable cascade, without a global theme change or a global font-family
swap.

## Acceptance Criteria

- [x] `@fontsource/archivo` and `@fontsource/space-mono` installed and imported
- [x] New brand tokens (fonts, teal accent, 6px radius) defined in `index.css` as a scoped
      `.brand-manifest` class — global `:root`/`.dark` tokens unchanged
- [x] `PlanTab.tsx` header, tabs, and "Accept migration" button render in the new type/accent/radius
      (header handled via `JobDetailPage.tsx`'s conditional scope, see S-F note; a Tailwind v4
      `--color-primary`/`--primary` indirection bug required using raw `var(--primary)` arbitrary
      classes instead of `bg-primary` — see S-F note for the fix)
- [x] PII warning + confidence/risk bars + stat tiles + criticality + "Before you accept" are one
      unified `Card` with a top-edge color bar, matching the Manifest mockup
- [x] `BlockPlanTable.tsx` badges/pills/step-id mono cells match the new radius and type scale
- [x] Existing F87 `status-colors.ts` / `StatusChip` semantic tone mapping (which value → which
      color) is unchanged — only the visual rendering (radius, fill vs. border) is updated
- [x] No visual regression on any other tab/page (Data Storage, ETL graph, Lineage, Docs, Explain,
      sidebar, jobs list) — verified by manual smoke test (ETL tab spot-checked, confirmed reverts
      to default look)
- [x] `make tsc-check`, `make frontend-lint`, `make frontend-build` all exit 0
- [x] `make test` exits 0
- [x] Manual smoke test in light + dark theme, real job data

## Subtasks

### S-A: Add font packages
**File:** `src/frontend/package.json`
**Depends on:** none
**Done when:** `@fontsource/archivo` and `@fontsource/space-mono` added as dependencies and
installed (`npm install`), matching how `@fontsource-variable/geist` is currently declared.
- [x] done

### S-B: Scoped brand theme tokens
**File:** `src/frontend/src/index.css`
**Depends on:** S-A
**Done when:** font-face imports for Archivo (weights 400/500/600/700/800) and Space Mono are
added; a `.brand-manifest` class is defined that locally overrides `--primary`,
`--primary-foreground`, `--radius`, and `--font-sans` to the teal/6px/Archivo values, plus new
`--brand-teal` reference token — all scoped inside the class selector, not `:root`/`.dark`.
- [x] done

### S-C: `status-colors.ts` → Manifest pill styling
**File:** `src/frontend/src/components/JobDetail/status-colors.ts`
**Depends on:** S-B
**Done when:** tone → class mapping updated to filled-background, 6px-radius pills (no border),
matching the Manifest mockup's `.pill` style; the tone → semantic-value mapping itself (which
band/strategy/risk maps to which tone) is unchanged from F87.
- [x] done

### S-D: `StatusChip.tsx` → Manifest pill rendering
**File:** `src/frontend/src/components/JobDetail/StatusChip.tsx`
**Depends on:** S-C
**Done when:** the chip component renders the new filled/6px-radius pill shape for both its
`chip` and `text` variants where applicable.
- [x] done

### S-E: `StatusBadge.tsx` → align to new pill convention
**File:** `src/frontend/src/components/JobDetail/StatusBadge.tsx`
**Depends on:** S-D
**Done when:** the job-status pill matches the new shape/radius convention; shimmer animation
logic untouched.
- [x] done

### S-F: `PlanTab.tsx` — apply brand scope to header
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-B
**Done when:** the tab's root container has the `brand-manifest` class; job title renders in
Archivo; active tab underline and "Accept migration" button pick up the scoped teal accent via
existing `bg-primary`/`border-primary` usage (no new hardcoded colors).
- [x] done

**Header scope gap — resolved:** the job title, `StatusBadge`, `ChevronTabBar`, and "Accept
migration" button live in `JobDetailPage.tsx`'s sticky header (shared chrome across all 5 tabs),
not in `PlanTab.tsx`. Resolved by conditionally applying `brand-manifest` to that sticky header
`div` in `JobDetailPage.tsx` via `cn(..., activeTab === "plan" && "brand-manifest")` — the header
now picks up Manifest styling (Archivo title, teal tab underline/Accept button) only while the
Plan tab is active, and renders byte-identical to pre-F88 on every other tab (verified: `cn`
resolves to the unchanged base class string when `activeTab !== "plan"`, since `clsx` drops the
falsy second argument and `twMerge` has nothing to dedupe). No all-tabs bleed.

**Teal-not-rendering bug — root cause found and fixed (2026-08-27):** after the above landed, the
teal accent silently failed to render anywhere it depended on the `bg-primary` / `text-primary` /
`border-primary` *utility classes* (Archivo font rendering was unaffected — fonts don't have this
indirection). Root cause, confirmed via live `getComputedStyle` probes on a fresh page load in a
real browser:

- Tailwind v4's `@theme` block in `index.css` declares `--color-primary: var(--primary);` once, on
  `:root` only (this is what `@theme` compiles to — see the served CSS: `@layer theme { :root,
  :host { --color-primary: var(--primary); ... } }`).
- A custom property's `var()` reference is substituted using the cascade *at the element where that
  property is declared* — here, `:root`. The resulting computed value (the old grayscale black,
  since `:root` itself is outside any `.brand-manifest` scope) is what then inherits down to every
  descendant, including elements inside `.brand-manifest`. Overriding `--primary` deeper in the
  tree does **not** retroactively change what `--color-primary` already resolved to at `:root`.
  Confirmed empirically: on a fresh load, `getComputedStyle(button).getPropertyValue('--primary')`
  correctly read `#0f7d72`, but `getPropertyValue('--color-primary')` on the same element still
  read the old default — and `.bg-primary` (which compiles to `background-color:
  var(--color-primary)`) painted the stale color as a direct result.
- This is exactly why raw `--primary` cascaded correctly everywhere (proven in earlier debugging)
  while anything going through the `--color-*` *derived* token (i.e. any `bg-primary` /
  `text-primary` / `border-primary` **class**) did not — the indirection, not layers/specificity/
  Base UI/native `<button>` theming, was the actual cause. (A stray earlier finding that even an
  unlayered `!important` stylesheet override didn't win was a separate red herring from that
  debugging session, not reproducible on a clean reload, and not needed to explain the bug once the
  indirection was found.)

**Fix:** for every element inside the `.brand-manifest` scope that needs the teal accent, replaced
the `bg-primary` / `text-primary` / `border-primary` / `border-l-primary` *utility class* with a
Tailwind arbitrary-value class referencing the **raw** `--primary` / `--primary-foreground` custom
property directly — e.g. `bg-[var(--primary)]`, `text-[var(--primary)]`, `border-l-[var(--primary)]`,
`bg-[var(--primary)]/5` — bypassing the broken `--color-primary`/`--color-primary-foreground`
indirection entirely. Because raw `--primary`/`--primary-foreground` are declared both at `:root`
(default) and inside `.brand-manifest` (teal), and raw custom properties correctly re-resolve at
each element's own position in the cascade, the exact same class works correctly both inside and
outside the scope with no extra fallback syntax needed — teal inside `.brand-manifest`, the
original default outside it. No hardcoded hex values were introduced.

Applied to: `JobDetailPage.tsx`'s "Accept migration" and "Download migration package" buttons
(added override classes, since `bg-primary`/`text-primary-foreground` come from the shared
`Button` component's default variant — `tailwind-merge` cleanly drops the conflicting class),
`ChevronTabBar.tsx`'s active-tab indicator, `PlanTab.tsx`'s accepted-state verdict banner
(`border-l-primary`/`bg-primary/5`/`text-primary` on the icon) and unified summary card's top-edge
color bar, the four `text-primary` inline text links (`InlineRunbook`, `AttentionCards`), and
`BlockPlanTable.tsx`'s strategy-filter chip active state and human-edited-icon highlight.

Verified via live `getComputedStyle` checks and screenshots in a real running browser (not just
code-reads): the Plan tab indicator, Accept/Download buttons, and accepted-state banner border all
resolve to `rgb(15, 125, 114)` (`#0f7d72`) on the Plan tab, and correctly revert to the original
`oklch(0.205 0 0)` default on the ETL tab (zero bleed) on the same job.

### S-G: `PlanTab.tsx` — unified summary card restructure
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-F, S-D
**Done when:** the PII/sensitive-data warning, confidence/risk bars, stat tiles, criticality row,
and `BeforeYouAcceptPanel` footer are nested inside one `Card` with a 3px top-edge color bar (red
when sensitive data is detected) replacing the current separate bordered warning banner — matching
the "C — Manifest" mockup artboard structure.
- [x] done

### S-H: `BlockPlanTable.tsx` → Manifest conventions
**File:** `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
**Depends on:** S-D
**Done when:** the table (wrapped in `brand-manifest`, inherited from `PlanTab` or applied
directly — whichever avoids double-wrapping) uses Space Mono for step-id cells and the new 6px
radius for pills/icon buttons.
- [x] done

### S-I: Manual smoke test
**Depends on:** S-G, S-H
**Done when:** dev server run locally; Plan tab and `BlockPlanTable` checked in light + dark theme
against a real job for visual match to the Manifest mockup; other tabs/pages spot-checked to
confirm zero visual bleed from the new tokens.
- [x] done — checked "Monthly Revenue Pipeline" (Plan tab) in both light and dark theme via
  browser: Archivo headline, teal "Accept migration" button and active-tab underline, red top-edge
  bar on the unified summary card, 6px pills all render correctly in both themes; dark mode toggle
  confirmed no regression. Frontend-builder additionally verified the "KYC / AML" accepted job's
  banner and confirmed the ETL tab (same job) reverts to the original black/default look with zero
  bleed from the `.brand-manifest` scope.

### S-J: Full gate
**Depends on:** S-I
**Done when:** `make tsc-check && make frontend-lint && make frontend-build && make test` all
exit 0.
- [x] done — `make test` (all 7 gates: ruff-check, ruff-format, mypy, pytest+coverage, tsc,
  frontend-lint, frontend-build) exits 0

## Dependencies on other features

- F87 (design-consistency-shared-primitives) — this feature builds directly on its
  `status-colors.ts` / `StatusChip` / `constants.ts` consolidation; do not reintroduce duplicate
  color maps

## Out of scope for this feature

- Rolling the new tokens out to any other tab or page — explicit user decision this session,
  tracked as a follow-up once this lands
- Changing the global `:root`/`.dark` shadcn theme tokens — the scoped `.brand-manifest` class is
  the mechanism specifically to avoid this
- Typography scale work beyond the Plan tab header (section/body sizing) — not part of the
  approved Manifest mockup scope
