import { useState } from "react";
import type { BlockPlan, PipelineStep, TrustReportBlock } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import { sasFileToPyFile } from "@/lib/sas-python-file-map";
import { BlockRow } from "./blockRowHelpers";

interface PipelineStepPanelProps {
  step: PipelineStep;
  allSteps: PipelineStep[];
  blockPlans: BlockPlan[];
  trustBlocks: Record<string, TrustReportBlock>;
  humanVerifiedBlocks: Set<string>;
  onBlockClick: (blockId: string) => void;
  onClose: () => void;
  mode?: "source" | "target";
  sasToPyMap?: Map<string, string[]>;
}

export default function PipelineStepPanel({
  step,
  allSteps,
  blockPlans,
  trustBlocks,
  humanVerifiedBlocks,
  onBlockClick,
  onClose,
  mode = "source",
  sasToPyMap,
}: PipelineStepPanelProps): React.ReactElement {
  const [blocksExpanded, setBlocksExpanded] = useState(false);

  // ── Dependency computation ─────────────────────────────────────────────────

  // For each input dataset: find which other step produces it (if any)
  const upstream = step.inputs.map((ds) => ({
    dataset: ds,
    producer: allSteps.find(
      (s) => s.step_id !== step.step_id && s.outputs.includes(ds),
    ) ?? null,
  }));

  // For each output dataset: find which other step consumes it (if any)
  const downstream = step.outputs.map((ds) => ({
    dataset: ds,
    consumer: allSteps.find(
      (s) => s.step_id !== step.step_id && s.inputs.includes(ds),
    ) ?? null,
  }));

  // In target mode, only show upstream entries that have a producer step (skip external inputs)
  const upstreamToShow =
    mode === "target" ? upstream.filter(({ producer }) => producer !== null) : upstream;

  // ── Block list + status summary ────────────────────────────────────────────

  const stepBlocks = [...blockPlans]
    .filter((bp) => step.blocks.includes(bp.block_id))
    .sort(
      (a, b) =>
        a.source_file.localeCompare(b.source_file) || a.start_line - b.start_line,
    );

  const displayBlocks =
    stepBlocks.length > 0
      ? stepBlocks
      : [...blockPlans]
          .filter((bp) => step.files.includes(bp.source_file))
          .sort(
            (a, b) =>
              a.source_file.localeCompare(b.source_file) || a.start_line - b.start_line,
          );

  const nVerified = displayBlocks.filter(
    (bp) =>
      humanVerifiedBlocks.has(bp.block_id) ||
      trustBlocks[bp.block_id]?.reconciliation_status === "pass",
  ).length;
  const nReview = displayBlocks.filter(
    (bp) =>
      !humanVerifiedBlocks.has(bp.block_id) &&
      (trustBlocks[bp.block_id]?.needs_attention ?? false),
  ).length;
  const nManual = displayBlocks.filter((bp) => bp.strategy === "manual").length;

  // ── Section label style ────────────────────────────────────────────────────
  const sectionLabel =
    "px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground";

  return (
    <div
      className="flex flex-col w-80 shrink-0 bg-background border border-border rounded-lg shadow-sm overflow-hidden"
      aria-label={`Pipeline step: ${step.name}`}
    >
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-col px-3 pt-2.5 pb-2 border-b border-border shrink-0">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold text-muted-foreground">
            STEP {step.step_id}
          </span>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="shrink-0 -mr-1 h-6 w-6"
            aria-label="Close step panel"
          >
            <X size={14} />
          </Button>
        </div>
        <span className="font-semibold text-sm text-foreground leading-snug mt-0.5">
          {step.name}
        </span>
      </div>

      {/* ── Scrollable body ─────────────────────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-h-0 overflow-y-auto">

        {/* Description */}
        {step.description && (
          <p className="px-3 py-2 text-xs text-muted-foreground border-b border-border">
            {step.description}
          </p>
        )}

        {/* ── PYTHON MODULES (Target mode only) ───────────────────────────── */}
        {mode === "target" && step.files.length > 0 && (
          <div className="border-b border-border">
            <div className={sectionLabel}>Python modules</div>
            <div className="px-3 pb-2 flex flex-col gap-2">
              {(() => {
                const seen = new Set<string>();
                const rows: Array<{ pyFile: string; sasFile: string }> = [];
                for (const sasFile of step.files) {
                  const pyFiles = sasToPyMap?.get(sasFile) ?? [sasFileToPyFile(sasFile)];
                  for (const pyFile of pyFiles) {
                    const key = `${pyFile}||${sasFile}`;
                    if (!seen.has(key)) {
                      seen.add(key);
                      rows.push({ pyFile, sasFile });
                    }
                  }
                }
                return rows.map(({ pyFile, sasFile }) => (
                  <div key={`${pyFile}||${sasFile}`} className="flex flex-col gap-0.5">
                    <span className="text-xs font-mono text-foreground truncate" title={pyFile}>
                      {pyFile.split("/").pop() ?? pyFile}
                    </span>
                    <span className="text-[11px] font-mono text-muted-foreground truncate ml-2">
                      ← {sasFile.split("/").pop()}
                    </span>
                  </div>
                ));
              })()}
            </div>
          </div>
        )}

        {/* ── MIGRATION STATUS (Target mode: rendered before depends-on) ───── */}
        {mode === "target" && (
          <div className="border-b border-border">
            <button
              type="button"
              className="w-full flex items-center justify-between px-3 pt-3 pb-1 hover:bg-muted/40 transition-colors"
              onClick={() => setBlocksExpanded((v) => !v)}
              aria-expanded={blocksExpanded}
            >
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Migration
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {displayBlocks.length} blocks
                </span>
              </div>
              {blocksExpanded ? (
                <ChevronDown size={12} className="text-muted-foreground" />
              ) : (
                <ChevronRight size={12} className="text-muted-foreground" />
              )}
            </button>

            {/* Status badge row */}
            <div className="flex items-center gap-2 px-3 pb-2">
              {displayBlocks.length === 0 ? (
                <span className="text-[11px] text-muted-foreground">No blocks</span>
              ) : (
                <>
                  {nVerified > 0 && (
                    <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium bg-green-100 text-green-800 border border-green-200">
                      ✓ {nVerified}
                    </span>
                  )}
                  {nReview > 0 && (
                    <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium bg-amber-100 text-amber-800 border border-amber-200">
                      ⚠ {nReview}
                    </span>
                  )}
                  {nManual > 0 && (
                    <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium bg-red-100 text-red-800 border border-red-200">
                      ✗ {nManual}
                    </span>
                  )}
                  {nVerified === 0 && nReview === 0 && nManual === 0 && (
                    <span className="text-[11px] text-muted-foreground">pending</span>
                  )}
                </>
              )}
            </div>

            {/* Expandable block list */}
            {blocksExpanded && displayBlocks.length > 0 && (
              <div className="border-t border-border">
                {displayBlocks.map((bp) => (
                  <BlockRow
                    key={bp.block_id}
                    bp={bp}
                    trustBlock={trustBlocks[bp.block_id]}
                    isHumanVerified={humanVerifiedBlocks.has(bp.block_id)}
                    onClick={() => onBlockClick(bp.block_id)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── DEPENDS ON ──────────────────────────────────────────────────── */}
        {upstreamToShow.length > 0 && (
          <div className="border-b border-border">
            <div className={sectionLabel}>Depends on</div>
            <div className="px-3 pb-2 flex flex-col gap-2">
              {upstreamToShow.map(({ dataset, producer }) => (
                <div key={dataset} className="flex flex-col gap-0.5">
                  {producer ? (
                    <div className="flex items-center gap-1.5">
                      {/* Left arrow accent */}
                      <span className="text-blue-500 font-bold text-xs shrink-0">←</span>
                      <span className="text-xs font-medium text-foreground">
                        Step {producer.step_id}
                      </span>
                      <span
                        className="text-xs text-muted-foreground truncate"
                        title={producer.name}
                      >
                        · {producer.name}
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <span className="text-slate-400 font-bold text-xs shrink-0">←</span>
                      <span className="text-xs text-muted-foreground italic">source data</span>
                    </div>
                  )}
                  {/* Dataset chip */}
                  <div className="ml-4">
                    <span className="inline-block rounded bg-blue-50 border border-blue-100 px-1.5 py-0.5 text-[11px] font-mono text-blue-800 max-w-full break-all">
                      {dataset}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── FEEDS INTO ──────────────────────────────────────────────────── */}
        {downstream.length > 0 && (
          <div className="border-b border-border">
            <div className={sectionLabel}>Feeds into</div>
            <div className="px-3 pb-2 flex flex-col gap-2">
              {downstream.map(({ dataset, consumer }) => (
                <div key={dataset} className="flex flex-col gap-0.5">
                  {consumer ? (
                    <div className="flex items-center gap-1.5">
                      <span className="text-green-600 font-bold text-xs shrink-0">→</span>
                      <span className="text-xs font-medium text-foreground">
                        Step {consumer.step_id}
                      </span>
                      <span
                        className="text-xs text-muted-foreground truncate"
                        title={consumer.name}
                      >
                        · {consumer.name}
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <span className="text-green-600 font-bold text-xs shrink-0">→</span>
                      <span className="text-xs text-muted-foreground italic">final output</span>
                    </div>
                  )}
                  {/* Dataset chip */}
                  <div className="ml-4">
                    <span className="inline-block rounded bg-green-50 border border-green-100 px-1.5 py-0.5 text-[11px] font-mono text-green-800 max-w-full break-all">
                      {dataset}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── CODE (SAS files — Source mode only) ────────────────────────── */}
        {mode !== "target" && step.files.length > 0 && (
          <div className="border-b border-border">
            <div className={sectionLabel}>Code</div>
            <div className="px-3 pb-2 flex flex-col gap-0.5">
              {step.files.map((f) => (
                <span
                  key={f}
                  className="text-xs font-mono text-muted-foreground truncate"
                  title={f}
                >
                  {f.split("/").pop() ?? f}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* ── MIGRATION STATUS (Source mode only — Target renders it above) ── */}
        {mode !== "target" && (
          <div>
            <button
              type="button"
              className="w-full flex items-center justify-between px-3 pt-3 pb-1 hover:bg-muted/40 transition-colors"
              onClick={() => setBlocksExpanded((v) => !v)}
              aria-expanded={blocksExpanded}
            >
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Migration
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {displayBlocks.length} blocks
                </span>
              </div>
              {blocksExpanded ? (
                <ChevronDown size={12} className="text-muted-foreground" />
              ) : (
                <ChevronRight size={12} className="text-muted-foreground" />
              )}
            </button>

            {/* Status badge row */}
            <div className="flex items-center gap-2 px-3 pb-2">
              {displayBlocks.length === 0 ? (
                <span className="text-[11px] text-muted-foreground">No blocks</span>
              ) : (
                <>
                  {nVerified > 0 && (
                    <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium bg-green-100 text-green-800 border border-green-200">
                      ✓ {nVerified}
                    </span>
                  )}
                  {nReview > 0 && (
                    <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium bg-amber-100 text-amber-800 border border-amber-200">
                      ⚠ {nReview}
                    </span>
                  )}
                  {nManual > 0 && (
                    <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium bg-red-100 text-red-800 border border-red-200">
                      ✗ {nManual}
                    </span>
                  )}
                  {nVerified === 0 && nReview === 0 && nManual === 0 && (
                    <span className="text-[11px] text-muted-foreground">pending</span>
                  )}
                </>
              )}
            </div>

            {/* Expandable block list */}
            {blocksExpanded && displayBlocks.length > 0 && (
              <div className="border-t border-border">
                {displayBlocks.map((bp) => (
                  <BlockRow
                    key={bp.block_id}
                    bp={bp}
                    trustBlock={trustBlocks[bp.block_id]}
                    isHumanVerified={humanVerifiedBlocks.has(bp.block_id)}
                    onClick={() => onBlockClick(bp.block_id)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
