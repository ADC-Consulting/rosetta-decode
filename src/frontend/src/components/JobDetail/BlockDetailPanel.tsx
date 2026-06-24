import type { BlockPlan, TrustReportBlock } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { CheckCircle2, ChevronLeft, Info, X, XCircle } from "lucide-react";
import { getBlockStatus, STATUS_CONFIG } from "./blockStatusHelpers";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BlockDetailPanelProps {
  blockId: string;
  blockPlan: BlockPlan;
  trustBlock: TrustReportBlock | undefined;
  isHumanVerified: boolean;
  parentPyFile?: string;
  onBack: () => void;
  onViewCode: (blockId: string) => void;
  onClose: () => void;
  onViewSourceFile?: (sasFile: string) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ConfidenceBar({ value }: { value: number }): React.ReactElement {
  const pct = Math.max(0, Math.min(1, value));
  const pctDisplay = Math.round(pct * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-mono text-foreground tabular-nums w-8">
        {pctDisplay}%
      </span>
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          style={{ width: `${pct * 100}%` }}
          className="h-full rounded-full bg-foreground/70"
        />
      </div>
    </div>
  );
}

function ReconStatus({
  status,
}: {
  status: "pass" | "fail" | null | undefined;
}): React.ReactElement {
  if (status === "pass") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-700">
        <CheckCircle2 size={12} />
        Pass
      </span>
    );
  }
  if (status === "fail") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-red-700">
        <XCircle size={12} />
        Fail
      </span>
    );
  }
  return (
    <span className="text-xs text-muted-foreground">—</span>
  );
}

// ---------------------------------------------------------------------------
// BlockDetailPanel
// ---------------------------------------------------------------------------

export default function BlockDetailPanel({
  blockId,
  blockPlan,
  trustBlock,
  isHumanVerified,
  parentPyFile,
  onBack,
  onViewCode,
  onClose,
  onViewSourceFile,
}: BlockDetailPanelProps): React.ReactElement {
  const statusKind = getBlockStatus(blockPlan, trustBlock, isHumanVerified);
  const statusCfg = STATUS_CONFIG[statusKind];

  const sourceBasename = blockPlan.source_file.includes("/")
    ? blockPlan.source_file.slice(blockPlan.source_file.lastIndexOf("/") + 1)
    : blockPlan.source_file;

  const confidence = blockPlan.confidence_score;

  const strategyLabel =
    blockPlan.strategy === "translated"
      ? "Translated"
      : blockPlan.strategy === "translated_with_review"
        ? "Review"
        : "Manual";

  const reconStatus = trustBlock?.reconciliation_status ?? null;

  return (
    <div
      className={[
        "flex flex-col w-80 shrink-0",
        "bg-background border border-border rounded-lg",
        "shadow-sm overflow-hidden",
      ].join(" ")}
      aria-label={`Block detail for ${blockId}`}
    >
      {/* Header: breadcrumb back link + close */}
      <div className="flex items-center gap-1 px-2 py-1.5 border-b border-border">
        {parentPyFile ? (
          <button
            type="button"
            onClick={onBack}
            className="flex flex-1 items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800 transition-colors truncate min-w-0"
            aria-label={`Back to ${parentPyFile}`}
          >
            <ChevronLeft className="w-3 h-3 shrink-0" />
            <span className="truncate">{parentPyFile}</span>
          </button>
        ) : (
          <span className="flex-1 text-xs font-medium text-muted-foreground truncate">Block detail</span>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          className="shrink-0 ml-auto h-6 w-6"
          aria-label="Close block detail panel"
        >
          <X size={14} />
        </Button>
      </div>

      {/* Body */}
      <div className="flex flex-col gap-3 px-3 py-3 flex-1 overflow-y-auto min-h-0">
        {/* Block type */}
        <div>
          <span className="text-sm font-bold font-mono text-foreground">
            {blockPlan.block_type}
          </span>
          {onViewSourceFile ? (
            <button
              type="button"
              onClick={() => onViewSourceFile(blockPlan.source_file)}
              className="text-xs text-blue-500 hover:text-blue-700 hover:underline font-mono mt-0.5 text-left transition-colors"
              title={blockPlan.source_file}
            >
              {sourceBasename} :{blockPlan.start_line}{blockPlan.end_line && blockPlan.end_line !== blockPlan.start_line ? `–${blockPlan.end_line}` : ""}
            </button>
          ) : (
            <div className="text-xs text-muted-foreground font-mono mt-0.5">
              {sourceBasename} :{blockPlan.start_line}{blockPlan.end_line && blockPlan.end_line !== blockPlan.start_line ? `–${blockPlan.end_line}` : ""}
            </div>
          )}
        </div>

        {/* Status badge */}
        <span
          className={[
            "self-start inline-flex items-center rounded px-1.5 py-0.5",
            "text-[11px] font-medium",
            statusCfg.className,
          ].join(" ")}
        >
          {statusCfg.label}
        </span>

        {/* Metadata rows */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-20 shrink-0">Strategy</span>
            <span className="text-xs font-medium text-foreground">{strategyLabel}</span>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">Confidence</span>
            <ConfidenceBar value={confidence} />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-20 shrink-0">Recon</span>
            <ReconStatus status={reconStatus} />
          </div>
        </div>

        {/* Rationale popover */}
        {blockPlan.rationale && (
          <div className="flex justify-end">
            <Popover>
              <PopoverTrigger asChild>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="Show rationale"
                >
                  <Info size={13} />
                  Rationale
                </button>
              </PopoverTrigger>
              <PopoverContent side="left" className="w-64 text-xs text-foreground">
                {blockPlan.rationale}
              </PopoverContent>
            </Popover>
          </div>
        )}

        {/* View Code button */}
        <Button
          variant="outline"
          size="sm"
          onClick={() => onViewCode(blockId)}
          className="w-full mt-auto"
        >
          View Code
        </Button>
      </div>
    </div>
  );
}
