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
import { pyFileToSasFiles, sasFileToPyFile } from "@/lib/sas-python-file-map";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import BlockCodePopup from "./BlockCodePopup";
import BlockDetailPanel from "./BlockDetailPanel";
import BlockInspectorPanel from "./BlockInspectorPanel";
import PipelineStepPanel from "./PipelineStepPanel";
import PythonModulePanel from "./PythonModulePanel";
import TargetGraph from "./TargetGraph";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ETLTabProps {
  jobId: string;
  blockPlans: BlockPlan[];
  trustReport: TrustReportResponse | undefined;
  jobSources: Record<string, string> | undefined;
  isReviewable: boolean;
  isAccepted?: boolean;
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
  isAccepted = false,
  generatedFiles,
}: ETLTabProps): React.ReactElement {
  const queryClient = useQueryClient();

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null);
  const [selectedStep, setSelectedStep] = useState<PipelineStep | null>(null);
  const [graphView, setGraphView] = useState<"source" | "target">("source");
  // Target sub-view state
  const [targetView, setTargetView] = useState<"steps" | "modules" | "blocks">("steps");
  // Selected Python module for right panel (Target view only)
  const [selectedPyModule, setSelectedPyModule] = useState<string | null>(null);
  // Block code popup — separate from selectedBlock so target panel doesn't auto-open popup
  const [codePopupBlockId, setCodePopupBlockId] = useState<string | null>(null);

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

  // Code popup block plan (may differ from selectedBlock when in target view)
  const codePopupBlockPlan = blockPlans.find(
    (bp) => bp.block_id === codePopupBlockId,
  );

  // ── Target view derived values ────────────────────────────────────────────
  const hasTargetNodes =
    !!generatedFiles && Object.keys(generatedFiles).some((f) => f !== "pipeline.py");

  const pyModuleCount = generatedFiles
    ? Object.keys(generatedFiles).filter((f) => f !== "pipeline.py").length
    : 0;

  // ── Derived SAS source files for the selected Python module ───────────────
  const selectedPyModuleSasFiles = useMemo(() => {
    if (!selectedPyModule) return [];
    return pyFileToSasFiles(selectedPyModule, blockPlans);
  }, [selectedPyModule, blockPlans]);

  // ── Derive parentPyFile for block-detail back link ────────────────────────
  const blockDetailParentPyFile = useMemo(() => {
    if (!selectedBlock || !selectedBlockPlan) return selectedPyModule ?? "";
    return selectedPyModule ?? sasFileToPyFile(selectedBlockPlan.source_file);
  }, [selectedBlock, selectedBlockPlan, selectedPyModule]);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleToggle = (next: "source" | "target") => {
    setGraphView(next);
    setSelectedFile(null);
    setSelectedStep(null);
    setSelectedPyModule(null);
    setSelectedBlock(null);
    setCodePopupBlockId(null);
  };

  const handleFileNodeClick = (file: FileNode) => {
    setSelectedFile(file.filename);
    setSelectedStep(null); // close step panel when file panel opens
  };

  const handlePipelineStepClick = (step: PipelineStep) => {
    setSelectedStep(step);
    setSelectedFile(null); // close file panel when step panel opens
  };

  const handleVerified = () => {
    void queryClient.invalidateQueries({
      queryKey: ["job", jobId, "changelog"],
    });
    // Don't close modal — let user see the Verified badge update, then close manually
  };

  // Target view handlers
  const handleModuleClick = (pyFile: string) => {
    setSelectedPyModule(pyFile);
    setSelectedBlock(null);
  };

  const handleTargetBlockClick = (blockId: string) => {
    // Find which pyModule this block belongs to
    const bp = blockPlans.find((b) => b.block_id === blockId);
    if (bp) {
      const pyFile = sasFileToPyFile(bp.source_file);
      setSelectedPyModule(pyFile);
    }
    setSelectedBlock(blockId);
  };

  // ── Determine right panel for target view ─────────────────────────────────
  // When a block is selected in Target mode → show BlockDetailPanel
  // When a module is selected (no block) → show PythonModulePanel
  const showTargetBlockDetail =
    graphView === "target" && !!selectedBlock && !!selectedBlockPlan;
  const showTargetModulePanel =
    graphView === "target" && !!selectedPyModule && !showTargetBlockDetail;

  // ── Render ───────────────────────────────────────────────────────────────
  const hasSidePanel =
    selectedFile ||
    selectedStep ||
    showTargetModulePanel ||
    showTargetBlockDetail;

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      {/* ── Summary bar ─────────────────────────────────────────────────── */}
      <div
        className={[
          "flex items-center gap-4 px-2 py-1.5",
          "text-xs text-muted-foreground border-b border-border shrink-0",
        ].join(" ")}
      >
        {graphView === "source" ? (
          <>
            <span>files: {new Set(blockPlans.map((b) => b.source_file)).size}</span>
            <span>blocks: {blockPlans.length}</span>
          </>
        ) : (
          <span>modules: {pyModuleCount}</span>
        )}
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
          {/* Source / Target toggle */}
          {(["source", "target"] as const).map((v) => {
            const disabled = v === "target" && !hasTargetNodes;
            return (
              <button
                key={v}
                onClick={() => handleToggle(v)}
                disabled={disabled}
                title={v === "source" ? "SAS source pipeline" : "Generated Python modules"}
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
        <div className={hasSidePanel ? "flex-1 min-w-0" : "w-full"}>
          {graphView === "source" ? (
            isLineageLoading ? (
              <Skeleton className="h-full w-full rounded" />
            ) : !etlLineage || etlLineage.nodes.length === 0 ? (
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                No lineage data available for this job.
              </div>
            ) : (
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
            )
          ) : (
            <TargetGraph
              key={`target-${targetView}`}
              lineage={etlLineage ?? { job_id: jobId, nodes: [], edges: [] }}
              generatedFiles={generatedFiles ?? {}}
              blockPlans={blockPlans}
              trustFiles={trustReport?.files}
              trustBlocks={trustBlocks}
              view={targetView}
              onViewChange={setTargetView}
              onFileClick={(sasFiles) => {
                setSelectedFile(sasFiles[0] ?? null);
                setSelectedStep(null);
              }}
              onModuleClick={handleModuleClick}
              onBlockClick={handleTargetBlockClick}
              selectedBlockId={selectedBlock}
            />
          )}
        </div>

        {/* Source view: Block inspector side panel */}
        {graphView === "source" && selectedFile && (
          <div className="w-80 border-l border-border overflow-y-auto shrink-0">
            <BlockInspectorPanel
              sourceFile={selectedFile}
              displayTitle={undefined}
              blockPlans={blockPlans}
              trustBlocks={trustBlocks}
              humanVerifiedBlocks={humanVerifiedBlocks}
              onBlockClick={(blockId) => {
                setSelectedBlock(blockId);
                setCodePopupBlockId(blockId);
              }}
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
              onBlockClick={(blockId) => {
                setSelectedBlock(blockId);
                setCodePopupBlockId(blockId);
              }}
              onClose={() => setSelectedStep(null)}
            />
          </div>
        )}

        {/* Target view: Python module panel */}
        {showTargetModulePanel && (
          <div className="w-80 border-l border-border overflow-y-auto shrink-0">
            <PythonModulePanel
              pyFile={selectedPyModule!}
              sasSourceFiles={selectedPyModuleSasFiles}
              blockPlans={blockPlans}
              trustBlocks={trustBlocks}
              humanVerifiedBlocks={humanVerifiedBlocks}
              onBlockClick={(blockId) => {
                setSelectedBlock(blockId);
              }}
              onClose={() => {
                setSelectedPyModule(null);
                setSelectedBlock(null);
              }}
            />
          </div>
        )}

        {/* Target view: Block detail panel */}
        {showTargetBlockDetail && selectedBlockPlan && (
          <div className="w-80 border-l border-border overflow-y-auto shrink-0">
            <BlockDetailPanel
              blockId={selectedBlock!}
              blockPlan={selectedBlockPlan}
              trustBlock={trustBlocks[selectedBlock!]}
              isHumanVerified={humanVerifiedBlocks.has(selectedBlock!)}
              parentPyFile={blockDetailParentPyFile}
              onBack={() => setSelectedBlock(null)}
              onViewCode={(blockId) => {
                setCodePopupBlockId(blockId);
              }}
              onClose={() => {
                setSelectedBlock(null);
                setSelectedPyModule(null);
              }}
            />
          </div>
        )}
      </div>

      {/* ── Code popup modal ────────────────────────────────────────────── */}
      {codePopupBlockId && codePopupBlockPlan && (
        <BlockCodePopup
          jobId={jobId}
          blockId={codePopupBlockId}
          sourceFile={codePopupBlockPlan.source_file}
          blockType={codePopupBlockPlan.block_type}
          status={deriveBlockStatus(
            codePopupBlockId,
            codePopupBlockPlan,
            trustBlocks,
            humanVerifiedBlocks,
          )}
          sasSource={jobSources?.[codePopupBlockPlan.source_file] ?? ""}
          startLine={codePopupBlockPlan.start_line}
          endLine={codePopupBlockPlan.end_line}
          onClose={() => setCodePopupBlockId(null)}
          onVerified={handleVerified}
          jobAccepted={isAccepted}
        />
      )}
    </div>
  );
}
