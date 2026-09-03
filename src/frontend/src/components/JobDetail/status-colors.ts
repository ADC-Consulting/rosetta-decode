// ---------------------------------------------------------------------------
// Shared status-color tokens for the Job Detail Plan/ETL surfaces.
//
// Before F87, confidence/strategy/risk/criticality color-by-state markup was
// hand-rolled independently in PlanTab.tsx (three separate maps) and
// BlockPlanTable.tsx (two more), and disagreed with each other in places
// (e.g. PlanTab's CONFIDENCE_COLOR treated `low` and `very_low` as distinct
// danger shades while its own AttentionTable's CONF_COLOR collapsed them to
// the same color). This module is the single source of truth: every
// confidence/strategy/risk/criticality value resolves to one semantic `Tone`,
// and `StatusChip` (./StatusChip.tsx) renders a `Tone` as one consistent pill
// or text treatment.
// ---------------------------------------------------------------------------

/**
 * Semantic tone shared by confidence, strategy, risk, and criticality
 * indicators. Everything in this module reduces to one of these five tones.
 * (`caution` was merged into `warning` in F89 — visually redundant next to it.)
 */
export type Tone = "success" | "warning" | "danger" | "danger-strong" | "neutral";

/**
 * Chip appearance per tone: filled background, no border, 6px radius — the "Manifest" pill
 * convention (F88). `rounded-lg` resolves to the scoped `--radius` (6px) inside `.brand-manifest`
 * and to the global default radius outside it; `border-transparent` overrides Badge's base
 * `border-border`/`border-transparent` variant classes so no visible border ever renders.
 *
 * Colors (F89) reference the raw `--tone-X`/`--tone-X-bg` custom properties via Tailwind
 * arbitrary-value classes (`bg-[var(...)]`/`text-[var(...)]`), not a derived `@theme --color-*`
 * token — see the `.brand-manifest` comment in index.css for why a derived token would not
 * re-resolve correctly inside the scoped override (the exact bug F88 found and fixed for
 * `--primary`). Outside `.brand-manifest`, `--tone-X` resolves to the stock Tailwind hex
 * equivalents declared at `:root`/`.dark`, so non-Plan-tab consumers are pixel-unchanged.
 */
export const TONE_CHIP_CLASS: Record<Tone, string> = {
  success: "text-[var(--tone-success)] bg-[var(--tone-success-bg)] rounded-lg border-transparent",
  warning: "text-[var(--tone-warning)] bg-[var(--tone-warning-bg)] rounded-lg border-transparent",
  danger: "text-[var(--tone-danger)] bg-[var(--tone-danger-bg)] rounded-lg border-transparent",
  "danger-strong":
    "text-[var(--tone-danger-strong)] bg-[var(--tone-danger-strong-bg)] rounded-lg border-transparent",
  neutral: "text-muted-foreground bg-muted rounded-lg border-transparent",
};

/** Text-only appearance per tone (no background/border) — for inline value text. */
export const TONE_TEXT_CLASS: Record<Tone, string> = {
  success: "text-[var(--tone-success)]",
  warning: "text-[var(--tone-warning)]",
  danger: "text-[var(--tone-danger)]",
  "danger-strong": "text-[var(--tone-danger-strong)]",
  neutral: "text-muted-foreground",
};

/**
 * CSS var() bridge — ONLY for contexts that need a computed inline style, such as a
 * `<Progress>` bar fill driven by a CSS variable (Tailwind classes can't
 * target that). Chip/text rendering must always go through the class maps
 * above; this map exists so the header confidence/risk bars in PlanTab don't
 * need their own local hex literals.
 *
 * Values are `var(--tone-X)` references (not baked hex, F89) so an inline `style={{ color: ... }}`
 * consumer re-resolves against the nearest ancestor's `--tone-X` override at render time — inline
 * style values resolve per the cascade at the element, unlike the `@theme` derived-token
 * indirection, so this is safe without the arbitrary-value-class workaround.
 */
export const TONE_HEX: Record<Tone, string> = {
  success: "var(--tone-success)",
  warning: "var(--tone-warning)",
  danger: "var(--tone-danger)",
  "danger-strong": "var(--tone-danger-strong)",
  neutral: "#9ca3af",
};

// ---------------------------------------------------------------------------
// Confidence band
// ---------------------------------------------------------------------------

export type ConfidenceBand = "high" | "medium" | "low" | "very_low" | "unknown";

/**
 * `low` and `very_low` are intentionally distinct danger shades, not
 * collapsed to one color. They are semantically different signals (40-64%
 * vs <40% / failed reconciliation), and treating them as visually distinct
 * is the more informative choice — this is the one convention going forward.
 */
export const CONFIDENCE_TONE: Record<ConfidenceBand, Tone> = {
  high: "success",
  medium: "warning",
  low: "danger",
  very_low: "danger-strong",
  unknown: "neutral",
};

export const CONFIDENCE_PCT: Record<ConfidenceBand, number> = {
  high: 90,
  medium: 65,
  low: 40,
  very_low: 20,
  unknown: 0,
};

// ---------------------------------------------------------------------------
// Strategy
// ---------------------------------------------------------------------------

export type Strategy = "translated" | "translated_with_review" | "manual";

export const STRATEGY_TONE: Record<Strategy, Tone> = {
  translated: "success",
  translated_with_review: "warning",
  manual: "danger",
};

export const STRATEGY_LABEL: Record<Strategy, string> = {
  translated: "Translated",
  translated_with_review: "Review needed",
  manual: "Manual",
};

// ---------------------------------------------------------------------------
// Risk (static, pre-translation assessment of SAS construct complexity)
// ---------------------------------------------------------------------------

export type RiskLevel = "low" | "medium" | "high";

export const RISK_TONE: Record<RiskLevel, Tone> = {
  low: "success",
  medium: "warning",
  high: "danger",
};

export const RISK_PCT: Record<RiskLevel, number> = { low: 33, medium: 66, high: 100 };

export const RISK_LABEL: Record<RiskLevel, string> = { low: "Low", medium: "Medium", high: "High" };

// Consolidated from JobDetail/constants.ts (S-G) — RISK_BADGE/RISK_CELL/RISK_LABELS were defined
// there but not imported anywhere else in the frontend; kept here, values unchanged, as the one
// source of truth in case call sites are added later.
export const RISK_BADGE: Record<RiskLevel, string> = {
  low: "text-green-700 bg-green-50 border border-green-200",
  medium: "text-amber-700 bg-amber-50 border border-amber-200",
  high: "text-red-700 bg-red-50 border border-red-200",
};
export const RISK_CELL: Record<RiskLevel, string> = {
  low: "text-green-700",
  medium: "text-amber-700",
  high: "text-red-700",
};
export const RISK_LABELS: Record<RiskLevel, string> = { low: "Low", medium: "Mid", high: "High" };

// ---------------------------------------------------------------------------
// Criticality (post-translation signal: strategy + confidence + reconciliation + blast radius)
// ---------------------------------------------------------------------------

export type Criticality = "critical" | "high" | "medium" | "low" | "unknown";

export const CRITICALITY_TONE: Record<Criticality, Tone> = {
  critical: "danger",
  high: "warning",
  medium: "warning",
  low: "success",
  unknown: "neutral",
};
