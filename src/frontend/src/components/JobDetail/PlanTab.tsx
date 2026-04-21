import { getJobPlan, patchJobPlan } from "@/api/jobs";
import type { BlockOverride, JobStatusValue, PatchPlanRequest } from "@/api/types";
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

  const { data, isLoading } = useQuery({
    queryKey: ["job", jobId, "plan"],
    queryFn: () => getJobPlan(jobId),
    enabled: !!jobId && isReviewable,
  });

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
          />
        </div>
      )}
    </div>
  );
}
