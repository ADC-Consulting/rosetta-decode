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
    className:
      "bg-[var(--tone-danger-bg)] text-[var(--tone-danger)] border border-[var(--tone-danger)]/30",
  },
  manual: {
    label: "Manual",
    className:
      "bg-[var(--tone-danger-bg)] text-[var(--tone-danger)] border border-[var(--tone-danger)]/30",
  },
  review: {
    label: "Review",
    className:
      "bg-[var(--tone-warning-bg)] text-[var(--tone-warning)] border border-[var(--tone-warning)]/30",
  },
  pass: {
    label: "Pass",
    className:
      "bg-[var(--tone-success-bg)] text-[var(--tone-success)] border border-[var(--tone-success)]/30",
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
