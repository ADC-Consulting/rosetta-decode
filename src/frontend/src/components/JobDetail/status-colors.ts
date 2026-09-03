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
 */
export type Tone = "success" | "warning" | "caution" | "danger" | "danger-strong" | "neutral";

/**
 * Chip appearance per tone: filled background, no border, 6px radius — the "Manifest" pill
 * convention (F88). `rounded-lg` resolves to the scoped `--radius` (6px) inside `.brand-manifest`
 * and to the global default radius outside it; `border-transparent` overrides Badge's base
 * `border-border`/`border-transparent` variant classes so no visible border ever renders.
 * Tailwind classes only, no raw hex.
 */
export const TONE_CHIP_CLASS: Record<Tone, string> = {
  success: "text-green-700 bg-green-50 rounded-lg border-transparent",
  warning: "text-amber-700 bg-amber-50 rounded-lg border-transparent",
  caution: "text-orange-700 bg-orange-50 rounded-lg border-transparent",
  danger: "text-red-700 bg-red-50 rounded-lg border-transparent",
  "danger-strong": "text-red-800 bg-red-100 rounded-lg border-transparent",
  neutral: "text-muted-foreground bg-muted rounded-lg border-transparent",
};

/** Text-only appearance per tone (no background/border) — for inline value text. */
export const TONE_TEXT_CLASS: Record<Tone, string> = {
  success: "text-green-700",
  warning: "text-amber-700",
  caution: "text-orange-700",
  danger: "text-red-600",
  "danger-strong": "text-red-800",
  neutral: "text-muted-foreground",
};

/**
 * Hex bridge — ONLY for contexts that need a computed inline style, such as a
 * `<Progress>` bar fill driven by a CSS variable (Tailwind classes can't
 * target that). Chip/text rendering must always go through the class maps
 * above; this map exists so the header confidence/risk bars in PlanTab don't
 * need their own local hex literals.
 */
export const TONE_HEX: Record<Tone, string> = {
  success: "#22c55e",
  warning: "#f59e0b",
  caution: "#f97316",
  danger: "#ef4444",
  "danger-strong": "#dc2626",
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
  high: "caution",
  medium: "warning",
  low: "success",
  unknown: "neutral",
};
