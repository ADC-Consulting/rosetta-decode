import type { BlockPlan, TrustReportBlock } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import { BlockRow } from "./blockRowHelpers";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PythonModulePanelProps {
  pyFile: string;
  sasSourceFiles: string[];
  blockPlans: BlockPlan[];
  trustBlocks: Record<string, TrustReportBlock>;
  humanVerifiedBlocks: Set<string>;
  onBlockClick: (blockId: string) => void;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// PythonModulePanel
// ---------------------------------------------------------------------------

export default function PythonModulePanel({
  pyFile,
  sasSourceFiles,
  blockPlans,
  trustBlocks,
  humanVerifiedBlocks,
  onBlockClick,
  onClose,
}: PythonModulePanelProps): React.ReactElement {
  // All block plans that belong to this python module
  const moduleBlocks = blockPlans.filter((bp) =>
    sasSourceFiles.includes(bp.source_file),
  );

  return (
    <div
      className={[
        "flex flex-col w-80 shrink-0",
        "bg-background border border-border rounded-lg",
        "shadow-sm overflow-hidden",
      ].join(" ")}
      aria-label={`Python module panel for ${pyFile}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <span
          className="font-semibold text-sm text-foreground font-mono truncate min-w-0"
          title={pyFile}
        >
          {pyFile}
        </span>
        <Badge
          variant="secondary"
          className="shrink-0 font-mono text-xs tabular-nums"
        >
          {moduleBlocks.length}
        </Badge>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          className="shrink-0 ml-auto h-6 w-6"
          aria-label="Close Python module panel"
        >
          <X size={14} />
        </Button>
      </div>

      {/* Block list — scrollable */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {moduleBlocks.length === 0 ? (
          <p className="px-3 py-4 text-xs text-muted-foreground">
            No blocks found for this module.
          </p>
        ) : sasSourceFiles.length <= 1 ? (
          // Single SAS source: flat block list sorted by start_line
          [...moduleBlocks]
            .sort((a, b) => a.start_line - b.start_line)
            .map((bp) => (
              <BlockRow
                key={bp.block_id}
                bp={bp}
                trustBlock={trustBlocks[bp.block_id]}
                isHumanVerified={humanVerifiedBlocks.has(bp.block_id)}
                onClick={() => onBlockClick(bp.block_id)}
              />
            ))
        ) : (
          // Multiple SAS sources: group by source file with tinted headers
          sasSourceFiles.map((sasFile) => {
            const sasBasename = sasFile.includes("/")
              ? sasFile.slice(sasFile.lastIndexOf("/") + 1)
              : sasFile;
            const sasBlocks = [...moduleBlocks]
              .filter((bp) => bp.source_file === sasFile)
              .sort((a, b) => a.start_line - b.start_line);
            if (sasBlocks.length === 0) return null;
            return (
              <div key={sasFile}>
                <div className="bg-slate-50 px-3 py-1 text-xs text-muted-foreground font-mono border-b border-border">
                  {sasBasename}
                </div>
                {sasBlocks.map((bp) => (
                  <BlockRow
                    key={bp.block_id}
                    bp={bp}
                    trustBlock={trustBlocks[bp.block_id]}
                    isHumanVerified={humanVerifiedBlocks.has(bp.block_id)}
                    onClick={() => onBlockClick(bp.block_id)}
                  />
                ))}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
