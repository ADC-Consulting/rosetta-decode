import type { JobStatusValue } from "@/api/types";

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

export const RISK_BADGE: Record<"low" | "medium" | "high", string> = {
  low: "text-green-700 bg-green-50 border border-green-200",
  medium: "text-amber-700 bg-amber-50 border border-amber-200",
  high: "text-red-700 bg-red-50 border border-red-200",
};

export const RISK_CELL: Record<"low" | "medium" | "high", string> = {
  low: "text-green-700",
  medium: "text-amber-700",
  high: "text-red-700",
};

export const RISK_LABELS: Record<"low" | "medium" | "high", string> = {
  low: "Low",
  medium: "Mid",
  high: "High",
};

export const TAB_CONTENT_HEIGHT = "calc(100vh - 140px)";
