import type { BlockPlan, TrustReportBlock } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import { BlockRow } from "./blockRowHelpers";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BlockInspectorPanelProps {
  sourceFile: string;
  displayTitle?: string;  // overrides header text only
  blockPlans: BlockPlan[];
  trustBlocks: Record<string, TrustReportBlock>;
  humanVerifiedBlocks: Set<string>;
  onBlockClick: (blockId: string) => void;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// BlockInspectorPanel
// ---------------------------------------------------------------------------

export default function BlockInspectorPanel({
  sourceFile,
  displayTitle,
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
          {displayTitle ?? basename}
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
