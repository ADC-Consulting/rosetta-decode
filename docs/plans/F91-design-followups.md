# F91 — Close out the three remaining F90 design follow-ups

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

F87–F90 shipped the "Manifest" design system across the whole frontend and are now merged to
`main`. Three follow-up items were left open in `journal/BACKLOG.md`. Both needed decisions are
now made, and live browser verification corrected the scope of the third — see
`docs/plans/F91-design-followups.md`'s companion plan-mode session for the full context:

1. Dark-mode unified summary card border is faint — decision: strengthen it.
2. `Dialog` portals to `document.body`, escaping `.brand-manifest` — decision: patch each dialog
   individually via a `container` prop, confirmed feasible against Base UI's actual API.
3. Graph status colors — re-scoped after live verification: not "no dark-mode support" (the
   graphs render fine in dark mode, fixed-light node cards by design, same as the ETL graph). The
   real bug: both `TargetGraph.tsx` and `LineageGraph.tsx` hardcode the identical stock, unmuted
   hex triad instead of the muted Manifest tone palette — a straight hex swap, not new
   infrastructure.

## Acceptance Criteria

- [x] Plan tab's unified summary card border reads clearly on all four edges in dark mode; light
      mode pixel-unchanged
- [x] All four affected dialogs (`BlockCodePopup`, `FileViewPopup`, `ExplainPage`'s mode-switch
      confirmation, `PlanTab`'s own dialog) render themed (Archivo/teal/6px radius/muted tones)
      instead of stock shadcn when opened
- [x] `TargetGraph.tsx` and `LineageGraph.tsx` both use the muted Manifest tone hex values instead
      of the stock `#22c55e`/`#f59e0b`/`#ef4444` triad
- [x] `make test` exits 0

## Subtasks

### S-A: Strengthen the dark-mode card border
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** the unified summary card's border reads clearly on all four edges in dark mode via
a scoped `dark:` variant on this one card, with light mode pixel-unchanged.
- [x] done — the planned `dark:border-white/20` Tailwind variant turned out to have zero effect:
  filed as its own bug, **#144** — this project's Tailwind `dark:` variant compiles to
  `@media (prefers-color-scheme: dark)`, not this app's actual `.dark`-class theme toggle
  (`enableSystem={false}` in `App.tsx`), so no `dark:`-prefixed utility anywhere in the app has
  ever responded to the in-app switcher. Routed around it using this project's already-proven
  pattern instead: a hand-written `.dark .brand-manifest .plan-summary-card { border-color: rgb(255
  255 255 / 0.2); }` rule in `index.css`. Verified via the app's real theme toggle (not just
  `.dark` class injection): `borderColor` computed style correctly flips between the stock value
  and the strengthened one as the toggle is clicked, light mode pixel-unchanged.

### S-B: Thread a `container` prop through the shared `Dialog` wrapper
**File:** `src/frontend/src/components/ui/dialog.tsx`
**Depends on:** none
**Done when:** `DialogContent` accepts an optional `container` prop and passes it to the inner
`DialogPortal`; omitting it preserves today's exact default behavior.
- [x] done — typed via `DialogPrimitive.Portal.Props["container"]` (reusing Base UI's own type),
  destructured before the rest-spread so it never reaches `DialogPrimitive.Popup`. Verified no
  existing call site (15 usages app-wide) passes `container`, so this is purely additive.

### S-C: Apply `container` at each of the four usage sites
**File:** `BlockCodePopup.tsx`, `FileViewPopup.tsx`, `ExplainPage.tsx`, `PlanTab.tsx`
**Depends on:** S-B
**Done when:** a shared hook resolves the nearest `.brand-manifest` ancestor and each of the four
dialogs passes it as `container`; all four render themed when opened, in both themes.
- [x] done — `useBrandManifestContainer()` in `src/frontend/src/lib/` resolves
  `document.querySelector(".brand-manifest")` once via a lazy `useState` initializer (an earlier
  `useEffect`-based attempt tripped `react-hooks/set-state-in-effect`). Verified 3 of 4 dialogs
  live (BlockCodePopup, FileViewPopup, PlanTab's own dialog) — each is a genuine DOM descendant of
  `.brand-manifest` when open (`dialog.closest('.brand-manifest') !== null`), Archivo/Space Mono
  font and 6px radius confirmed via computed style. The 4th (ExplainPage's mode-switch dialog)
  needs an active sent conversation to trigger and wasn't forced via automation — confirmed
  correct by code review instead (identical hook, identical `container={container}` wiring).

### S-D: Fix `TargetGraph.tsx`'s hardcoded status colors
**File:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** none
**Done when:** `STATUS_COLOR_MAP`'s three hex values are the light-mode muted tone equivalents.
- [x] done — `STATUS_COLOR_MAP`, the progress-bar fill colors, and `FILE_STATUS_ENTRIES`'s legend
  array (three separate occurrences of the same stock triad) all swapped to the muted
  success/warning/danger hex values.

### S-E: Fix `LineageGraph.tsx`'s hardcoded status colors
**File:** `src/frontend/src/components/LineageGraph.tsx`
**Depends on:** none
**Done when:** `STATUS_STYLE`/`STATUS_SYMBOL`'s hex values are the light-mode muted tone
equivalents; `REASON_COLORS` and hover-edge-label styles left untouched.
- [x] done — `STATUS_STYLE`, `STATUS_SYMBOL`, and (found via live verification after the initial
  fix) the `STATUS_ENTRIES` legend array all swapped to the muted tone values. `REASON_COLORS` and
  the neutral `background`/`color` fields left untouched as scoped.

### S-F: Full manual smoke test
**Depends on:** S-A, S-B, S-C, S-D, S-E
**Done when:** all five fixes verified in light + dark theme, no regressions in already-correct
Manifest-scoped surfaces.
- [x] done — live browser pass against a real job (`Monthly Revenue Pipeline`) after all five
  commits landed together: Plan tab summary card border reads clearly on all edges in dark
  (`rgba(255,255,255,0.2)`) and is pixel-unchanged in light (`oklch(0.922 0 0)`); PlanTab's
  "Confidence & criticality" dialog and `FileViewPopup` (opened from the ETL tab's Files graph)
  both confirmed themed live (`insideBrandManifest: true`, `6px` radius, Archivo font); ETL tab's
  `TargetGraph` (Pipeline/Source/Target views) and the embedded/standalone `LineageGraph` (ETL
  tab's Files view and the dedicated Lineage page) all render the muted tone triad with no stock
  `rgb(34,197,94)`/`rgb(239,68,68)`/`rgb(245,158,11)` remaining anywhere on any of those pages,
  confirmed via a DOM sweep in addition to visual inspection. No regressions found in surfaces
  established by F87-F90.

### S-G: Gate
**Depends on:** S-F
**Done when:** `make tsc-check && make frontend-lint && make frontend-build && make test` all exit
0.
- [x] done — `make test` (which runs tsc, frontend-lint, and frontend-build as gates alongside the
  backend suite) ran green immediately before the S-B/S-C commit and again confirmed via the same
  gate sequence for every subsequent commit on this branch.

## Dependencies on other features

- Builds on F87–F90 (the whole Manifest design system and its scoping mechanism)

## Out of scope for this feature

- Promoting Manifest to the app's default theme (considered, explicitly declined in favor of
  per-dialog patching)
- Adding real theme-reactivity to `TargetGraph.tsx`/`LineageGraph.tsx` node cards (they stay
  fixed-light by existing design; only the status accent colors are being corrected)
- `REASON_COLORS` and other non-status-tone coloring in `LineageGraph.tsx`
