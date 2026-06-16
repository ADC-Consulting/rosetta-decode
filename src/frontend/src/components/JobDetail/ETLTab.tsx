import { getJobChangelog, getJobLineage } from "@/api/jobs";
import type {
  BlockPlan,
  FileNode,
  TrustReportBlock,
  TrustReportResponse,
} from "@/api/types";
import LineageGraph from "@/components/LineageGraph";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import BlockCodePopup from "./BlockCodePopup";
import BlockInspectorPanel from "./BlockInspectorPanel";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ETLTabProps {
  jobId: string;
  blockPlans: BlockPlan[];
  trustReport: TrustReportResponse | undefined;
  jobSources: Record<string, string> | undefined;
  isReviewable: boolean;
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
}: ETLTabProps): React.ReactElement {
  const queryClient = useQueryClient();

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null);

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
  };

  const handleVerified = () => {
    void queryClient.invalidateQueries({
      queryKey: ["job", jobId, "changelog"],
    });
    setSelectedBlock(null);
  };

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
      </div>

      {/* ── Body: graph + optional side panel ───────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Graph — shrinks when side panel is open */}
        <div className={selectedFile ? "flex-1 min-w-0" : "w-full"}>
          {isLineageLoading ? (
            <Skeleton className="h-full w-full rounded" />
          ) : !etlLineage || etlLineage.nodes.length === 0 ? (
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
              No lineage data available for this job.
            </div>
          ) : (
            <LineageGraph
              key={selectedFile ? "with-panel" : "full"}
              lineage={etlLineage}
              blockPlans={blockPlans}
              trustFiles={trustReport?.files}
              trustBlocks={trustBlocks}
              onFileNodeClick={handleFileNodeClick}
              initialView="files"
            />
          )}
        </div>

        {/* Block inspector side panel */}
        {selectedFile && (
          <div
            className={[
              "w-80 border-l border-border overflow-y-auto shrink-0",
            ].join(" ")}
          >
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
