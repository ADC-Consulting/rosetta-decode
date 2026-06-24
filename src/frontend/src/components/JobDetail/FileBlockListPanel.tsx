import type { BlockPlan, TrustReportBlock } from "@/api/types";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import { getBlockStatus, STATUS_CONFIG } from "./blockStatusHelpers";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FileBlockListPanelProps {
  pyFile: string;
  blockPlans: BlockPlan[];
  trustBlocks: Record<string, TrustReportBlock>;
  humanVerifiedBlocks: Set<string>;
  sasFiles: string[];
  onBlockClick: (blockId: string) => void;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function blockLabel(blockType: string, rationale?: string): string {
  if (rationale?.trim()) return rationale.trim();
  const map: Record<string, string> = {
    PROC_IMPORT: "Import data",
    PROC_SQL: "SQL query",
    DATA_STEP: "Data transformation",
    PROC_MEANS: "Compute statistics",
    PROC_SORT: "Sort data",
    PROC_FREQ: "Frequency table",
    PROC_TRANSPOSE: "Transpose data",
    MACRO_CALL: "Macro execution",
  };
  return map[blockType] ?? blockType;
}

const SORT_ORDER: Record<string, number> = {
  Manual: 0,
  Failed: 1,
  Review: 2,
  Pending: 3,
  Verified: 4,
  Pass: 5,
};

function sortOrder(label: string): number {
  return SORT_ORDER[label] ?? 3;
}

// ---------------------------------------------------------------------------
// FileBlockListPanel
// ---------------------------------------------------------------------------

export default function FileBlockListPanel({
  pyFile,
  blockPlans,
  trustBlocks,
  humanVerifiedBlocks,
  sasFiles,
  onBlockClick,
  onClose,
}: FileBlockListPanelProps): React.ReactElement {
  const basename = pyFile.split("/").pop() ?? pyFile;

  // Filter to blocks belonging to this pyFile's SAS sources
  const fileBlocks = blockPlans.filter((bp) => sasFiles.includes(bp.source_file));

  // Annotate with status and sort
  const annotated = fileBlocks.map((bp) => {
    const tb = trustBlocks[bp.block_id];
    const kind = getBlockStatus(bp, tb, humanVerifiedBlocks.has(bp.block_id));
    const cfg = STATUS_CONFIG[kind];
    return { bp, kind, label: cfg.label };
  });

  annotated.sort((a, b) => sortOrder(a.label) - sortOrder(b.label));

  // Summary counts
  const totalCount = annotated.length;
  const nonPassCount = annotated.filter((a) => a.label !== "Pass" && a.label !== "Verified").length;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 pt-4 pb-3 border-b border-border shrink-0">
        <div className="flex items-center justify-between gap-2">
          <span
            className="font-mono font-bold text-sm text-foreground truncate"
            title={pyFile}
          >
            {basename}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 shrink-0"
            onClick={onClose}
            aria-label="Close panel"
          >
            <X size={14} />
          </Button>
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          {totalCount} {totalCount === 1 ? "block" : "blocks"}
          {nonPassCount > 0 && (
            <span className="text-amber-600 font-medium">
              {" "}· ⚠ {nonPassCount} {nonPassCount === 1 ? "needs" : "need"} attention
            </span>
          )}
        </div>
      </div>

      {/* Block rows */}
      <div className="flex-1 overflow-y-auto">
        {annotated.length === 0 ? (
          <div className="px-4 py-6 text-xs text-muted-foreground text-center">
            No blocks found for this file.
          </div>
        ) : (
          annotated.map(({ bp, label }) => {
            let dotColor = "text-amber-500";
            let dotChar = "⚠";
            if (label === "Pass" || label === "Verified") {
              dotColor = "text-green-600";
              dotChar = "●";
            } else if (label === "Manual" || label === "Failed") {
              dotColor = "text-red-600";
              dotChar = "✗";
            }

            const primaryLabel = blockLabel(bp.block_type, bp.rationale);

            return (
              <button
                key={bp.block_id}
                type="button"
                className="w-full text-left px-4 py-2.5 border-b border-border hover:bg-muted/50 transition-colors"
                onClick={() => onBlockClick(bp.block_id)}
              >
                {/* Row 1: status dot + rationale */}
                <div className="flex items-start gap-1.5 min-w-0">
                  <span className={`${dotColor} text-[11px] leading-4 shrink-0`} aria-hidden="true">
                    {dotChar}
                  </span>
                  <span
                    className="text-xs text-foreground truncate"
                    title={primaryLabel}
                  >
                    {primaryLabel}
                  </span>
                </div>
                {/* Row 2: SAS chip + block_type + line */}
                <div className="flex items-center gap-1.5 mt-0.5 pl-4 min-w-0">
                  <span className="inline-flex items-center rounded px-1 text-[9px] font-semibold bg-slate-100 text-slate-500 font-mono shrink-0">
                    SAS
                  </span>
                  <span className="text-[10px] text-muted-foreground font-mono truncate">
                    {bp.block_type}
                  </span>
                  <span className="text-[10px] text-muted-foreground/60 shrink-0">
                    · line {bp.start_line}
                  </span>
                </div>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
