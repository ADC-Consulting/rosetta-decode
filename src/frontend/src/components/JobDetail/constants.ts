import type { JobStatusValue } from "@/api/types";

// RISK_BADGE/RISK_CELL/RISK_LABELS moved to ./status-colors.ts (F87 S-G) — the single source of
// truth for risk color/label maps, shared with PlanTab and BlockPlanTable. Re-exported here,
// values unchanged, for backward compatibility.
export { RISK_BADGE, RISK_CELL, RISK_LABELS } from "./status-colors";

export const STATUS_LABEL: Record<JobStatusValue, string> = {
  queued: "Queued",
  running: "Processing",
  proposed: "Needs Review",
  under_review: "Needs Review",
  accepted: "Accepted",
  failed: "Failed",
  done: "Done",
};

// Amber/green/red tones reference the shared --tone-* CSS custom properties (F89,
// src/frontend/src/index.css) via raw var() arbitrary-value classes, same pattern as
// TONE_CHIP_CLASS in status-colors.ts. These resolve to stock Tailwind hex equivalents at
// :root/.dark (unchanged everywhere outside .brand-manifest, e.g. the jobs list page) and to
// the muted "Manifest" palette inside .brand-manifest (Plan tab only) — see F89 plan doc.
// queued/running (slate/blue) are intentionally left as stock Tailwind classes — they're not
// part of the red/amber/green semantic tone family.
export const STATUS_PILL_CLASS: Record<JobStatusValue, string> = {
  queued: "bg-slate-600",
  running: "bg-blue-600",
  proposed: "bg-[var(--tone-warning)]",
  under_review: "bg-[var(--tone-warning)]",
  accepted: "bg-[var(--tone-success)]",
  failed: "bg-[var(--tone-danger)]",
  done: "bg-[var(--tone-success)]",
};

export const STATUS_SHIMMER: Record<JobStatusValue, boolean> = {
  queued: true,
  running: true,
  proposed: false,
  under_review: false,
  accepted: false,
  failed: false,
  done: false,
};

export const POLLING_STATUSES: JobStatusValue[] = ["queued", "running", "proposed"];

export const STRATEGY_LABELS: Record<string, string> = {
  translated: "Translated",
  translated_with_review: "Review needed",
  manual: "Manual",
};

export const TAB_CONTENT_HEIGHT = "calc(100vh - 140px)";
