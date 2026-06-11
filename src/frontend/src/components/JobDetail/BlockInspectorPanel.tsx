import type { BlockPlan, TrustReportBlock } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BlockInspectorPanelProps {
  sourceFile: string;
  blockPlans: BlockPlan[];
  trustBlocks: Record<string, TrustReportBlock>;
  humanVerifiedBlocks: Set<string>;
  onBlockClick: (blockId: string) => void;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Status badge helpers
// ---------------------------------------------------------------------------

type BlockStatusKind =
  | "human-verified"
  | "failed"
  | "manual"
  | "review"
  | "pass"
  | "pending";

function getBlockStatus(
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

const STATUS_CONFIG: Record<
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

// ---------------------------------------------------------------------------
// BlockRow
// ---------------------------------------------------------------------------

interface BlockRowProps {
  bp: BlockPlan;
  trustBlock: TrustReportBlock | undefined;
  isHumanVerified: boolean;
  onClick: () => void;
}

function BlockRow({
  bp,
  trustBlock,
  isHumanVerified,
  onClick,
}: BlockRowProps): React.ReactElement {
  const statusKind = getBlockStatus(bp, trustBlock, isHumanVerified);
  const statusCfg = STATUS_CONFIG[statusKind];

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "w-full flex items-center gap-2 px-3 py-2 text-left",
        "hover:bg-muted/50 transition-colors cursor-pointer",
        "border-b border-border last:border-b-0",
      ].join(" ")}
      aria-label={`Inspect block ${bp.block_id}`}
    >
      {/* Block type pill */}
      <span
        className={[
          "shrink-0 inline-flex items-center rounded px-1.5 py-0.5",
          "text-[11px] font-medium font-mono",
          "bg-slate-100 text-slate-700 border border-slate-200",
        ].join(" ")}
      >
        {bp.block_type}
      </span>

      {/* Line number */}
      <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
        :{bp.start_line}
      </span>

      {/* Spacer */}
      <span className="flex-1 min-w-0" />

      {/* Status badge */}
      <span
        className={[
          "shrink-0 inline-flex items-center rounded px-1.5 py-0.5",
          "text-[11px] font-medium",
          statusCfg.className,
        ].join(" ")}
        aria-label={`Status: ${statusCfg.label}`}
      >
        {statusCfg.label}
      </span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// BlockInspectorPanel
// ---------------------------------------------------------------------------

export default function BlockInspectorPanel({
  sourceFile,
  blockPlans,
  trustBlocks,
  humanVerifiedBlocks,
  onBlockClick,
  onClose,
}: BlockInspectorPanelProps): React.ReactElement {
  const basename = sourceFile.includes("/")
    ? sourceFile.slice(sourceFile.lastIndexOf("/") + 1)
    : sourceFile;

  const fileBlocks = [...blockPlans]
    .filter((bp) => bp.source_file === sourceFile)
    .sort((a, b) => a.start_line - b.start_line);

  return (
    <div
      className={[
        "flex flex-col w-80 shrink-0",
        "bg-background border border-border rounded-lg",
        "shadow-sm overflow-hidden",
      ].join(" ")}
      aria-label={`Block inspector for ${basename}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <span
          className="font-semibold text-sm text-foreground font-mono truncate min-w-0"
          title={sourceFile}
        >
          {basename}
        </span>
        <Badge
          variant="secondary"
          className="shrink-0 font-mono text-xs tabular-nums"
        >
          {fileBlocks.length}
        </Badge>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          className="shrink-0 ml-auto h-6 w-6"
          aria-label="Close block inspector"
        >
          <X size={14} />
        </Button>
      </div>

      {/* Block list — scrollable */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {fileBlocks.length === 0 ? (
          <p className="px-3 py-4 text-xs text-muted-foreground">
            No blocks found for this file.
          </p>
        ) : (
          fileBlocks.map((bp) => (
            <BlockRow
              key={bp.block_id}
              bp={bp}
              trustBlock={trustBlocks[bp.block_id]}
              isHumanVerified={humanVerifiedBlocks.has(bp.block_id)}
              onClick={() => onBlockClick(bp.block_id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
