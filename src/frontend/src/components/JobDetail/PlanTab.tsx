import { getJobPlan, getJobTrustReport, patchJobPlan } from "@/api/jobs";
import type {
  BlockOverride,
  JobStatusValue,
  PatchPlanRequest,
  TrustReportBlock,
  TrustReportResponse,
} from "@/api/types";
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import BlockPlanTable from "./BlockPlanTable";
import { RISK_BADGE } from "./constants";
import ReconSummaryCard from "./ReconSummaryCard";

export default function PlanTab({
  jobId,
  isReviewable,
  jobStatus,
  report,
  overrides,
  setOverrides,
}: {
  jobId: string;
  isReviewable: boolean;
  jobStatus: JobStatusValue;
  report: Record<string, unknown> | null;
  overrides: Record<string, BlockOverride>;
  setOverrides: React.Dispatch<
    React.SetStateAction<Record<string, BlockOverride>>
  >;
}): React.ReactElement {
  const [savingBlockId, setSavingBlockId] = useState<string | null>(null);

  const trustReportEnabled =
    !!jobId && (jobStatus === "proposed" || jobStatus === "accepted" || jobStatus === "done");

  const { data, isLoading } = useQuery({
    queryKey: ["job", jobId, "plan"],
    queryFn: () => getJobPlan(jobId),
    enabled: !!jobId && isReviewable,
  });

  const { data: trustReport } = useQuery<TrustReportResponse>({
    queryKey: ["trust-report", jobId],
    queryFn: () => getJobTrustReport(jobId),
    enabled: trustReportEnabled,
  });

  const trustBlocks: Record<string, TrustReportBlock> = trustReport
    ? Object.fromEntries(trustReport.blocks.map((b) => [b.block_id, b]))
    : {};

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function saveOverride(blockId: string, override: BlockOverride): void {
    if (saveTimerRef.current !== null) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      setSavingBlockId(blockId);
      void patchJobPlan(jobId, {
        block_overrides: [override],
      } satisfies PatchPlanRequest).finally(() => setSavingBlockId(null));
    }, 500);
  }

  function handleStrategyChange(blockId: string, value: string): void {
    const current = overrides[blockId] ?? { block_id: blockId };
    const updated: BlockOverride = {
      ...current,
      block_id: blockId,
      strategy: value,
    };
    setOverrides((prev) => ({ ...prev, [blockId]: updated }));
    saveOverride(blockId, updated);
  }

  function handleRiskChange(blockId: string, value: string): void {
    const current = overrides[blockId] ?? { block_id: blockId };
    const updated: BlockOverride = {
      ...current,
      block_id: blockId,
      risk: value,
    };
    setOverrides((prev) => ({ ...prev, [blockId]: updated }));
    saveOverride(blockId, updated);
  }

  function handleNoteChange(blockId: string, value: string): void {
    const current = overrides[blockId] ?? { block_id: blockId };
    const updated: BlockOverride = {
      ...current,
      block_id: blockId,
      note: value,
    };
    setOverrides((prev) => ({ ...prev, [blockId]: updated }));
    saveOverride(blockId, updated);
  }

  const isProposed = jobStatus === "proposed";

  if (!isReviewable) {
    return (
      <p className="text-sm text-muted-foreground">
        Migration plan available once migration completes.
      </p>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading plan…
      </div>
    );
  }

  if (!data) {
    return (
      <p className="text-sm text-muted-foreground">
        No migration plan available for this job.
      </p>
    );
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto space-y-6 pb-6">
      <ReconSummaryCard report={report} />

      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-semibold px-2 py-0.5 rounded-full ${RISK_BADGE[data.overall_risk]}`}
          >
            {data.overall_risk.toUpperCase()} RISK
          </span>
        </div>
        <p className="text-sm text-foreground">{data.summary}</p>
      </div>

      {data.recommended_review_blocks.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">
            Blocks requiring manual review
          </h3>
          <div className="flex flex-wrap gap-2">
            {data.recommended_review_blocks.map((bid) => (
              <span
                key={bid}
                className="font-mono text-xs px-2 py-1 rounded bg-amber-50 border border-amber-200 text-amber-800"
              >
                {bid}
              </span>
            ))}
          </div>
        </div>
      )}

      {data.cross_file_dependencies.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Cross-file dependencies</h3>
          <ul className="text-sm space-y-1 list-disc list-inside text-muted-foreground">
            {data.cross_file_dependencies.map((dep, i) => (
              <li key={i}>{dep}</li>
            ))}
          </ul>
        </div>
      )}

      {trustReport && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-lg border border-green-200 bg-green-50 p-3 text-center">
            <p className="text-2xl font-bold text-green-700">{trustReport.auto_verified}</p>
            <p className="text-xs font-medium text-green-600 mt-0.5">Auto-verified</p>
          </div>
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-center">
            <p className="text-2xl font-bold text-amber-700">{trustReport.needs_review}</p>
            <p className="text-xs font-medium text-amber-600 mt-0.5">Needs review</p>
          </div>
          <div className="rounded-lg border border-border bg-muted/50 p-3 text-center">
            <p className="text-2xl font-bold text-muted-foreground">{trustReport.manual_todo}</p>
            <p className="text-xs font-medium text-muted-foreground mt-0.5">Manual TODO</p>
          </div>
        </div>
      )}

      {data.block_plans.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Block plan</h3>
          <BlockPlanTable
            blockPlans={data.block_plans}
            isProposed={isProposed}
            overrides={overrides}
            savingBlockId={savingBlockId}
            onStrategyChange={handleStrategyChange}
            onRiskChange={handleRiskChange}
            onNoteChange={handleNoteChange}
            trustBlocks={trustBlocks}
            jobId={jobId}
            isAccepted={jobStatus === "accepted"}
          />
        </div>
      )}
    </div>
  );
}
