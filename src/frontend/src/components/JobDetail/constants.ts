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

export const STATUS_PILL_CLASS: Record<JobStatusValue, string> = {
  queued: "bg-slate-600",
  running: "bg-blue-600",
  proposed: "bg-amber-500",
  under_review: "bg-amber-500",
  accepted: "bg-emerald-600",
  failed: "bg-red-600",
  done: "bg-emerald-600",
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
