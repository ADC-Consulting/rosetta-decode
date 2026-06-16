import type { BlockPlan, TrustReportBlock } from "@/api/types";

// ---------------------------------------------------------------------------
// Status badge types and helpers — pure TypeScript, no JSX.
// Shared between BlockInspectorPanel and PipelineStepPanel via BlockRow.
// ---------------------------------------------------------------------------

export type BlockStatusKind =
  | "human-verified"
  | "failed"
  | "manual"
  | "review"
  | "pass"
  | "pending";

export function getBlockStatus(
  bp: BlockPlan,
  trustBlock: TrustReportBlock | undefined,
  humanVerified: boolean,
): BlockStatusKind {
  if (humanVerified) return "human-verified";
  if (trustBlock?.reconciliation_status === "fail") return "failed";
  if (bp.strategy === "manual") return "manual";
  if (trustBlock?.needs_attention) return "review";
  if (trustBlock?.reconciliation_status === "pass") return "pass";
  return "pending";
}

export const STATUS_CONFIG: Record<
  BlockStatusKind,
  { label: string; className: string }
> = {
  "human-verified": {
    label: "Verified",
    className: "bg-teal-100 text-teal-800 border border-teal-200",
  },
  failed: {
    label: "Failed",
    className: "bg-red-100 text-red-800 border border-red-200",
  },
  manual: {
    label: "Manual",
    className: "bg-red-100 text-red-800 border border-red-200",
  },
  review: {
    label: "Review",
    className: "bg-amber-100 text-amber-800 border border-amber-200",
  },
  pass: {
    label: "Pass",
    className: "bg-green-100 text-green-800 border border-green-200",
  },
  pending: {
    label: "Pending",
    className: "bg-muted text-muted-foreground border border-border",
  },
};

export interface BlockRowProps {
  bp: BlockPlan;
  trustBlock: TrustReportBlock | undefined;
  isHumanVerified: boolean;
  onClick: () => void;
}
