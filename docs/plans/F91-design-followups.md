# F91 — Close out the three remaining F90 design follow-ups

**Phase:** 3
**Area:** Frontend
**Status:** in-progress

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

- [ ] Plan tab's unified summary card border reads clearly on all four edges in dark mode; light
      mode pixel-unchanged
- [ ] All four affected dialogs (`BlockCodePopup`, `FileViewPopup`, `ExplainPage`'s mode-switch
      confirmation, `PlanTab`'s own dialog) render themed (Archivo/teal/6px radius/muted tones)
      instead of stock shadcn when opened
- [ ] `TargetGraph.tsx` and `LineageGraph.tsx` both use the muted Manifest tone hex values instead
      of the stock `#22c55e`/`#f59e0b`/`#ef4444` triad
- [ ] `make test` exits 0

## Subtasks

### S-A: Strengthen the dark-mode card border
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** none
**Done when:** the unified summary card's border reads clearly on all four edges in dark mode via
a scoped `dark:` variant on this one card, with light mode pixel-unchanged.
- [ ] done

### S-B: Thread a `container` prop through the shared `Dialog` wrapper
**File:** `src/frontend/src/components/ui/dialog.tsx`
**Depends on:** none
**Done when:** `DialogContent` accepts an optional `container` prop and passes it to the inner
`DialogPortal`; omitting it preserves today's exact default behavior.
- [ ] done

### S-C: Apply `container` at each of the four usage sites
**File:** `BlockCodePopup.tsx`, `FileViewPopup.tsx`, `ExplainPage.tsx`, `PlanTab.tsx`
**Depends on:** S-B
**Done when:** a shared hook resolves the nearest `.brand-manifest` ancestor and each of the four
dialogs passes it as `container`; all four render themed when opened, in both themes.
- [ ] done

### S-D: Fix `TargetGraph.tsx`'s hardcoded status colors
**File:** `src/frontend/src/components/JobDetail/TargetGraph.tsx`
**Depends on:** none
**Done when:** `STATUS_COLOR_MAP`'s three hex values are the light-mode muted tone equivalents.
- [ ] done

### S-E: Fix `LineageGraph.tsx`'s hardcoded status colors
**File:** `src/frontend/src/components/LineageGraph.tsx`
**Depends on:** none
**Done when:** `STATUS_STYLE`/`STATUS_SYMBOL`'s hex values are the light-mode muted tone
equivalents; `REASON_COLORS` and hover-edge-label styles left untouched.
- [ ] done

### S-F: Full manual smoke test
**Depends on:** S-A, S-B, S-C, S-D, S-E
**Done when:** all five fixes verified in light + dark theme, no regressions in already-correct
Manifest-scoped surfaces.
- [ ] done

### S-G: Gate
**Depends on:** S-F
**Done when:** `make tsc-check && make frontend-lint && make frontend-build && make test` all exit
0.
- [ ] done

## Dependencies on other features

- Builds on F87–F90 (the whole Manifest design system and its scoping mechanism)

## Out of scope for this feature

- Promoting Manifest to the app's default theme (considered, explicitly declined in favor of
  per-dialog patching)
- Adding real theme-reactivity to `TargetGraph.tsx`/`LineageGraph.tsx` node cards (they stay
  fixed-light by existing design; only the status accent colors are being corrected)
- `REASON_COLORS` and other non-status-tone coloring in `LineageGraph.tsx`
