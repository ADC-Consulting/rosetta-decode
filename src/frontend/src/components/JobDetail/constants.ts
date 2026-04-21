import type { JobStatusValue } from "@/api/types";

export const STATUS_LABEL: Record<JobStatusValue, string> = {
  queued: "Queued",
  running: "Running",
  proposed: "Under Review",
  accepted: "Accepted",
  failed: "Failed",
  done: "Under Review",
};

export const STATUS_PILL_CLASS: Record<JobStatusValue, string> = {
  queued: "bg-slate-600",
  running: "bg-blue-600",
  proposed: "bg-amber-500",
  done: "bg-amber-500",
  accepted: "bg-emerald-600",
  failed: "bg-red-600",
};

export const STATUS_SHIMMER: Record<JobStatusValue, boolean> = {
  queued: true,
  running: true,
  proposed: true,
  done: false,
  accepted: false,
  failed: false,
};

export const POLLING_STATUSES: JobStatusValue[] = ["queued", "running", "proposed"];

export const STRATEGY_LABELS: Record<string, string> = {
  translate: "Auto-translate",
  translate_with_review: "Translate + review",
  manual_ingestion: "Manual ingestion",
  manual: "Manual",
  skip: "Skip",
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
