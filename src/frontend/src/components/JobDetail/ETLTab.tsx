import { getJobChangelog, getJobLineage } from "@/api/jobs";
import type {
  BlockPlan,
  FileNode,
  PipelineStep,
  TrustReportBlock,
  TrustReportResponse,
} from "@/api/types";
import LineageGraph from "@/components/LineageGraph";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import BlockCodePopup from "./BlockCodePopup";
import BlockInspectorPanel from "./BlockInspectorPanel";
import PipelineStepPanel from "./PipelineStepPanel";
import TargetGraph from "@/components/JobDetail/TargetGraph";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ETLTabProps {
  jobId: string;
  blockPlans: BlockPlan[];
  trustReport: TrustReportResponse | undefined;
  jobSources: Record<string, string> | undefined;
  isReviewable: boolean;
  generatedFiles: Record<string, string> | null;
}

type BlockStatus =
  | "auto-verified"
  | "needs-review"
  | "manual"
  | "human-verified"
  | "pending";

// ---------------------------------------------------------------------------
// Status derivation helper
// ---------------------------------------------------------------------------

function deriveBlockStatus(
  blockId: string,
  blockPlan: BlockPlan,
  trustBlocks: Record<string, TrustReportBlock>,
  humanVerifiedBlocks: Set<string>,
): BlockStatus {
  if (humanVerifiedBlocks.has(blockId)) return "human-verified";
  if (blockPlan.strategy === "manual") return "manual";
  if (trustBlocks[blockId]?.needs_attention) return "needs-review";
  if (trustBlocks[blockId]?.reconciliation_status === "pass") return "auto-verified";
  return "pending";
}

// ---------------------------------------------------------------------------
// ETLTab
// ---------------------------------------------------------------------------

export default function ETLTab({
  jobId,
  blockPlans,
  trustReport,
  jobSources,
  isReviewable,
  generatedFiles,
}: ETLTabProps): React.ReactElement {
  const queryClient = useQueryClient();

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null);
  const [selectedStep, setSelectedStep] = useState<PipelineStep | null>(null);
  const [graphView, setGraphView] = useState<"source" | "target">("source");

  // ── Lineage ──────────────────────────────────────────────────────────────
  const { data: lineageData, isLoading: isLineageLoading } = useQuery({
    queryKey: ["job", jobId, "lineage"],
    queryFn: () => getJobLineage(jobId),
    enabled: isReviewable,
  });

  // Filter lineage to .sas files only — excludes CSV/data file nodes from ETL graph
  const etlLineage = useMemo(() => {
    if (!lineageData) return undefined;
    const sasFilenames = new Set(
      (lineageData.file_nodes ?? [])
        .filter((fn) => fn.filename.toLowerCase().endsWith('.sas'))
        .map((fn) => fn.filename),
    );
    return {
      ...lineageData,
      file_nodes: (lineageData.file_nodes ?? []).filter((fn) =>
        fn.filename.toLowerCase().endsWith('.sas'),
      ),
      file_edges: (lineageData.file_edges ?? []).filter(
        (fe) => sasFilenames.has(fe.source_file) && sasFilenames.has(fe.target_file),
      ),
    };
  }, [lineageData]);

  // ── Changelog → humanVerifiedBlocks ──────────────────────────────────────
  const { data: changelog } = useQuery({
    queryKey: ["job", jobId, "changelog"],
    queryFn: () => getJobChangelog(jobId),
    enabled: isReviewable,
  });

  const humanVerifiedBlocks = useMemo(() => {
    const s = new Set<string>();
    (changelog?.entries ?? [])
      .filter((e) => e.trigger === "human-verify")
      .forEach((e) => s.add(e.block_id));
    return s;
  }, [changelog]);

  // ── trustBlocks map ───────────────────────────────────────────────────────
  const trustBlocks: Record<string, TrustReportBlock> = useMemo(
    () =>
      Object.fromEntries(
        (trustReport?.blocks ?? []).map((b) => [b.block_id, b]),
      ),
    [trustReport],
  );

  // ── Selected block plan ───────────────────────────────────────────────────
  const selectedBlockPlan = blockPlans.find(
    (bp) => bp.block_id === selectedBlock,
  );

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleFileNodeClick = (file: FileNode) => {
    setSelectedFile(file.filename);
    setSelectedStep(null); // close step panel when file panel opens
  };

  const handlePipelineStepClick = (step: PipelineStep) => {
    setSelectedStep(step);
    setSelectedFile(null); // close file panel when step panel opens
  };

  function handleToggle(next: "source" | "target") {
    setGraphView(next);
    setSelectedFile(null);
    setSelectedStep(null);
  }

  const handleVerified = () => {
    void queryClient.invalidateQueries({
      queryKey: ["job", jobId, "changelog"],
    });
    // Don't close modal — let user see the Verified badge update, then close manually
  };

  // ── Derived values ────────────────────────────────────────────────────────
  const hasTargetNodes =
    !!generatedFiles && Object.keys(generatedFiles).some((f) => f !== "pipeline.py");

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      {/* ── Summary bar ─────────────────────────────────────────────────── */}
      <div
        className={[
          "flex items-center gap-4 px-2 py-1.5",
          "text-xs text-muted-foreground border-b border-border shrink-0",
        ].join(" ")}
      >
        <span>files: {new Set(blockPlans.map((b) => b.source_file)).size}</span>
        <span>blocks: {blockPlans.length}</span>
        {trustReport && (
          <>
            <span className="text-green-700">
              ✓ verified: {trustReport.auto_verified + humanVerifiedBlocks.size}
            </span>
            <span className="text-amber-700">
              ⚠ review: {trustReport.needs_review}
            </span>
            <span className="text-red-700">
              ✗ manual: {trustReport.manual_todo}
            </span>
          </>
        )}
        <div className="ml-auto flex items-center gap-1">
          {(["source", "target"] as const).map((v) => {
            const disabled = v === "target" && !hasTargetNodes;
            return (
              <button
                key={v}
                type="button"
                onClick={() => handleToggle(v)}
                disabled={disabled}
                className={[
                  "px-2 py-0.5 rounded text-[11px] font-medium border transition-colors",
                  graphView === v
                    ? "bg-foreground text-background border-foreground"
                    : "bg-transparent text-muted-foreground border-border hover:border-foreground/40",
                  disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer",
                ].join(" ")}
              >
                {v.charAt(0).toUpperCase() + v.slice(1)}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Body: graph + optional side panel ───────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Graph — shrinks when side panel is open */}
        <div className={(selectedFile || selectedStep) ? "flex-1 min-w-0" : "w-full"}>
          {isLineageLoading ? (
            <Skeleton className="h-full w-full rounded" />
          ) : !etlLineage || etlLineage.nodes.length === 0 ? (
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
              No lineage data available for this job.
            </div>
          ) : graphView === "source" ? (
            <LineageGraph
              key={(selectedFile || selectedStep) ? "with-panel" : "full"}
              lineage={etlLineage}
              blockPlans={blockPlans}
              trustFiles={trustReport?.files}
              trustBlocks={trustBlocks}
              onFileNodeClick={handleFileNodeClick}
              onPipelineStepClick={handlePipelineStepClick}
              initialView="pipeline"
              selectedFilePath={selectedFile}
              humanVerifiedBlocks={humanVerifiedBlocks}
            />
          ) : (
            <TargetGraph
              key="target"
              lineage={etlLineage}
              generatedFiles={generatedFiles ?? {}}
              blockPlans={blockPlans}
              trustFiles={trustReport?.files}
              onFileClick={(sasFiles) => {
                // TODO F67: show composite block list for merged modules
                setSelectedFile(sasFiles[0] ?? null);
                setSelectedStep(null);
              }}
            />
          )}
        </div>

        {/* Block inspector side panel */}
        {selectedFile && (
          <div className="w-80 border-l border-border overflow-y-auto shrink-0">
            <BlockInspectorPanel
              sourceFile={selectedFile}
              blockPlans={blockPlans}
              trustBlocks={trustBlocks}
              humanVerifiedBlocks={humanVerifiedBlocks}
              onBlockClick={(blockId) => setSelectedBlock(blockId)}
              onClose={() => setSelectedFile(null)}
            />
          </div>
        )}

        {/* Pipeline step side panel */}
        {selectedStep && (
          <div className="w-80 border-l border-border overflow-y-auto shrink-0">
            <PipelineStepPanel
              step={selectedStep}
              allSteps={etlLineage?.pipeline_steps ?? []}
              blockPlans={blockPlans}
              trustBlocks={trustBlocks}
              humanVerifiedBlocks={humanVerifiedBlocks}
              onBlockClick={(blockId) => setSelectedBlock(blockId)}
              onClose={() => setSelectedStep(null)}
            />
          </div>
        )}
      </div>

      {/* ── Code popup modal ────────────────────────────────────────────── */}
      {selectedBlock && selectedBlockPlan && (
        <BlockCodePopup
          jobId={jobId}
          blockId={selectedBlock}
          sourceFile={selectedBlockPlan.source_file}
          blockType={selectedBlockPlan.block_type}
          status={deriveBlockStatus(
            selectedBlock,
            selectedBlockPlan,
            trustBlocks,
            humanVerifiedBlocks,
          )}
          sasSource={jobSources?.[selectedBlockPlan.source_file] ?? ""}
          startLine={selectedBlockPlan.start_line}
          endLine={selectedBlockPlan.end_line}
          onClose={() => setSelectedBlock(null)}
          onVerified={handleVerified}
        />
      )}
    </div>
  );
}
