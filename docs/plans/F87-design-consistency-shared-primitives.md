# F87 — Design consistency pass: shared status/badge/card primitives

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

A read-only design audit (this session, see `journal/SESSIONS.md`) found that the "looks vibe coded"
complaint traces to one root cause, not many independent style bugs: nearly every recurring UI
concept in `JobDetail/` (status pill, color-by-state, bordered card) has 2-3 independently
hand-rolled implementations instead of one shared source. `PlanTab.tsx` alone defines two
different confidence-color maps that disagree with each other; shadcn `Badge` is imported in only
8 places against 29 hand-rolled pill patterns; shadcn `Card` is imported in only 2 files. This
feature consolidates those into shared primitives on the Plan tab and `BlockPlanTable` (the ETL
tab's block detail surface) first, on the audit's finding that doing so resolves most of the
secondary spacing/typography/icon-size drift as a side effect. Done looks like: one status-color
token module, one `StatusChip` component wrapping shadcn `Badge`, all Plan/ETL chip markup wired
to it, no raw hex color literals for state colors, and no visual regression.

## Acceptance Criteria

- [x] Single shared status-color token module defines confidence-band, strategy, and risk
      color/label maps — no duplicate or divergent maps remain
- [x] All hand-rolled status/strategy/confidence/criticality pill markup in `PlanTab.tsx` and
      `BlockPlanTable.tsx` renders through one shared `StatusChip` component (built on shadcn `Badge`) —
      **exception:** `BlockPlanTable.tsx`'s Strategy column (Translated/Review needed) was out of
      S-E's scope and still uses its own blue/amber rounded-rect markup, not `StatusChip`; see
      "Out of scope" below, flagged as a follow-up candidate
- [x] `StatusBadge.tsx` job-status pill uses the same chip shape/border-radius/sizing convention
      (shimmer animation preserved — it's a distinct effect, not a duplicate concept)
- [x] No raw hex color literals remain in `PlanTab.tsx` / `StatusBadge.tsx` for state colors
      (a small `TONE_HEX` bridge remains centralized in `status-colors.ts`, used only for the two
      `<Progress>` bar fills which need a computed CSS value, not a Tailwind class)
- [x] `size={13}` icon call sites reviewed and normalized to the established 12/14 scale
- [x] `make tsc-check`, `make frontend-lint`, `make frontend-build` all exit 0
- [x] `make test` exits 0 (no backend/worker files touched)
- [x] Manual smoke test in both light and dark theme: Plan tab attention cards/table, block plan
      table chips, job status badge — consistent shape/color, no layout regression

## Subtasks

### S-A: Shared status-color token module
**File:** `src/frontend/src/components/JobDetail/status-colors.ts` (new)
**Depends on:** none
**Done when:** a single module exports typed color/label maps for confidence band
(high/medium/low/very_low/unknown), strategy (translated/translated_with_review/manual), and risk
(low/medium/high) — each as Tailwind class strings, no raw hex. Not consumed yet.
- [x] done

### S-B: `StatusChip` shared component
**File:** `src/frontend/src/components/JobDetail/StatusChip.tsx` (new)
**Depends on:** S-A
**Done when:** a component wraps shadcn `Badge`, accepts a semantic tone resolved from S-A tokens,
and renders one consistent pill shape/size. Not consumed yet.
- [x] done

### S-C: Wire `StatusChip` into `PlanTab.tsx` AttentionCards + AttentionTable
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-B
**Done when:** local `strategyColor`/`strategyLabel` (AttentionCards) and `STRAT_COLOR`/
`STRAT_LABEL`/`CONF_COLOR`/`ConfBadge` (AttentionTable) are removed; both components render chips
via `StatusChip` sourced from S-A.
- [x] done

### S-D: Replace header confidence/risk bar hex colors
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-A
**Done when:** module-scope `CONFIDENCE_COLOR` and `RISK_BAR` (raw hex) are replaced by S-A tokens;
confidence bar and risk bar render correctly in both themes.
- [x] done

### S-E: Wire `StatusChip` into `BlockPlanTable.tsx` risk/criticality/confidence chips
**File:** `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
**Depends on:** S-B
**Done when:** the hand-rolled risk chip, criticality chip, and `CONFIDENCE_BAND_TEXT_COLOR` usage
are replaced by `StatusChip`; local `CRITICALITY_CLASSES`/`riskCls` maps removed in favor of S-A.
- [x] done

### S-F: Align `StatusBadge.tsx` job-status pill to the shared chip convention
**File:** `src/frontend/src/components/JobDetail/StatusBadge.tsx`
**Depends on:** S-B
**Done when:** the job-status pill uses the same shape/padding/sizing convention as `StatusChip`;
shimmer animation logic is preserved unchanged (distinct visual effect); `STATUS_PILL_CLASS`
domain (job status, not block strategy) stays separate from S-A by design.
- [x] done

### S-G: Consolidate `constants.ts` risk/criticality maps
**File:** `src/frontend/src/components/JobDetail/constants.ts`
**Depends on:** S-A
**Done when:** `RISK_BADGE`, `RISK_CELL`, `RISK_LABELS` are re-exported from or merged into S-A so
there is exactly one source of truth per semantic domain — no value changes, de-duplication only.
- [x] done

### S-H: Normalize off-grid icon sizes
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`, `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`, `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** none
**Done when:** every `size={13}` call site is reviewed against its role (inline label icon vs.
icon-button) and changed to `size={12}` or `size={14}` per the established convention, with no
visual regression in icon-button padding.
- [x] done

### S-I: Card primitive pass on Plan tab bordered containers
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-C, S-D
**Done when:** hand-rolled `rounded-lg border border-border bg-card` containers that represent the
same "card" concept as the shadcn `Card` already used in the file are converted to
`Card`/`CardContent` where semantically a card; `px-4 py-3` vs `px-3 py-2` padding reconciled to
one convention per container tier.
- [x] done

### S-J: Manual smoke test
**Depends on:** S-C, S-D, S-E, S-F, S-G, S-H, S-I
**Done when:** dev server run locally; Plan tab and ETL tab block table visually inspected in both
light and dark theme against a real job — chip shape/color/size consistent, no layout regression.
Note added to this plan file with what was checked.
- [x] done — checked via `docker compose up -d` against job "Monthly Revenue Pipeline"
  (`dec0de00-0000-4000-8000-000000000001`), light + dark theme:
  - Jobs list `StatusBadge` pills ("Needs Review", "Accepted") — consistent shape
  - Plan tab header confidence bar (green 85%) and risk bar (amber Medium) — render correctly,
    no hex/theme mismatch in dark mode
  - Criticality pills ("medium 5", "low 10") — consistent rounded-full pill in both themes
  - Needs attention: Cards view and Table view both show identical "Review needed" amber
    `StatusChip` pill (previously three divergent implementations)
  - Steps table (`BlockPlanTable`) — risk/criticality chips now `StatusChip` pills (green
    "low" / amber "medium"); confidence % as colored text; icon buttons consistent size
  - ETL tab Pipeline view — summary bar stats and node graph render correctly
  - No console errors observed
  - Note: `BlockPlanTable`'s own Strategy column (Translated/Review needed, blue/amber
    rounded-rect) was intentionally left out of S-E's scope and still differs in shape from
    `StatusChip`'s pill — flagged as a candidate for a follow-up pass, not fixed here

### S-K: Full gate
**Depends on:** S-J
**Done when:** `make tsc-check && make frontend-lint && make frontend-build && make test` all
exit 0.
- [x] done — `make test` (all 7 gates: ruff-check, ruff-format, mypy, pytest+coverage, tsc,
  frontend-lint, frontend-build) exits 0

## Dependencies on other features

- none

## Out of scope for this feature

- `BlockPlanTable.tsx`'s Strategy column (Translated/Review needed cell, ~line 700) — uses its
  own blue/amber rounded-rect markup with different colors than the rest of the app's strategy
  convention; discovered during S-E but not in that subtask's literal scope (risk/criticality/
  confidence only). Candidate for a small follow-up to migrate onto `StatusChip`.
- DataStorageTab, ETL tab's own TargetGraph/FileNodeCard components, and other tabs not
  identified as high-visibility in the audit — a follow-up pass once this one lands
- Typography scale (`text-xs` vs `text-sm` header sizing) — flagged by the audit as lower-impact
  and expected to partially resolve once chip/card consolidation removes ad-hoc containers;
  revisit only if still inconsistent after this feature
- Any backend/API/worker changes — this is frontend-only
