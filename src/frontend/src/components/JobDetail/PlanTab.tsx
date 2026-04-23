import { getJobPlan, getJobTrustReport } from "@/api/jobs";
import type {
  BlockOverride,
  JobPlanResponse,
  JobStatusValue,
  TrustReportBlock,
  TrustReportResponse,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import BlockPlanTable from "./BlockPlanTable";

// ---------------------------------------------------------------------------
// Colour maps
// ---------------------------------------------------------------------------

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "#22c55e",
  medium: "#f59e0b",
  low: "#ef4444",
  very_low: "#dc2626",
  unknown: "#9ca3af",
};

const CONFIDENCE_PCT: Record<string, number> = {
  high: 90,
  medium: 65,
  low: 40,
  very_low: 20,
  unknown: 0,
};

const riskPctMap: Record<string, number> = { low: 33, medium: 66, high: 100 };

const RISK_BAR: Record<string, { color: string; label: string }> = {
  low: { color: "#22c55e", label: "Low" },
  medium: { color: "#f59e0b", label: "Medium" },
  high: { color: "#ef4444", label: "High" },
};

// ---------------------------------------------------------------------------
// StatPill
// ---------------------------------------------------------------------------

function StatPill({
  count,
  label,
  colorClass,
  dotClass,
  tooltip,
}: {
  count: number | undefined;
  label: string;
  colorClass: string;
  dotClass: string;
  tooltip: string;
}): React.ReactElement | null {
  if (count === undefined) return null;
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <div className="flex items-center gap-1.5 cursor-default select-none" />
        }
      >
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotClass}`} />
        <span className={`text-xs font-semibold tabular-nums ${colorClass}`}>{count}</span>
        <span className="text-xs text-muted-foreground">{label}</span>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-65 text-xs leading-relaxed whitespace-normal text-center">
        {tooltip}
      </TooltipContent>
    </Tooltip>
  );
}

// ---------------------------------------------------------------------------
// PlanTab
// ---------------------------------------------------------------------------

export default function PlanTab({
  jobId,
  isReviewable,
  jobStatus,
  onBlockRefineSuccess,
  jobPythonCode,
  generatedFiles,
}: {
  jobId: string;
  isReviewable: boolean;
  jobStatus: JobStatusValue;
  report?: Record<string, unknown> | null;
  overrides: Record<string, BlockOverride>;
  setOverrides: React.Dispatch<React.SetStateAction<Record<string, BlockOverride>>>;
  onBlockRefineSuccess?: () => void;
  jobPythonCode?: string;
  generatedFiles?: Record<string, string>;
}): React.ReactElement {
  const trustReportEnabled =
    !!jobId &&
    (jobStatus === "proposed" || jobStatus === "accepted" || jobStatus === "done");

  const { data: planData, isLoading } = useQuery<JobPlanResponse | null>({
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
      <div className="space-y-4">
        <Skeleton className="h-28 w-full rounded-lg" />
        <Skeleton className="h-8 w-full rounded-md" />
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (!planData) {
    return (
      <p className="text-sm text-muted-foreground">
        No migration plan available for this job.
      </p>
    );
  }

  const overallConfidence = trustReport?.overall_confidence ?? "unknown";
  const confidenceColor = CONFIDENCE_COLOR[overallConfidence] ?? CONFIDENCE_COLOR["unknown"];
  const confidencePct = trustReport
    ? Math.round(
        (trustReport.overall_confidence_score ?? CONFIDENCE_PCT[overallConfidence] / 100) * 100,
      )
    : CONFIDENCE_PCT[overallConfidence];

  const riskBar = RISK_BAR[planData.overall_risk] ?? {
    color: "#9ca3af",
    label: planData.overall_risk,
  };

  return (
    <TooltipProvider>
    <div className="h-full min-h-0 overflow-y-auto space-y-4 pb-6">
      {/* Single summary card */}
      <Card className="border-border bg-muted/30">
        <CardContent className="p-4 space-y-3">
          <p className="text-sm text-foreground leading-relaxed">
            {planData.summary ?? (
              <span className="italic text-muted-foreground">No summary available.</span>
            )}
          </p>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 pt-1 border-t border-border">
            {/* Confidence bar */}
            <div className="flex items-center gap-2 min-w-[180px]">
              <span className="text-xs text-muted-foreground shrink-0 w-20">Confidence</span>
              <Progress
                value={confidencePct}
                className="h-1.5 flex-1 [&_[data-slot=progress-indicator]]:bg-[var(--bar-fill)]"
                style={{ "--bar-fill": confidenceColor } as React.CSSProperties}
              />
              <span
                className="text-xs font-semibold tabular-nums w-8 text-right"
                style={{ color: confidenceColor }}
              >
                {confidencePct}%
              </span>
            </div>
            {/* Risk bar */}
            <div className="flex items-center gap-2 min-w-[160px]">
              <span className="text-xs text-muted-foreground shrink-0 w-8">Risk</span>
              <Progress
                value={riskPctMap[planData.overall_risk] ?? 0}
                className="h-1.5 flex-1 [&_[data-slot=progress-indicator]]:bg-[var(--bar-fill)]"
                style={{ "--bar-fill": riskBar.color } as React.CSSProperties}
              />
              <span
                className="text-xs font-semibold capitalize w-12 text-right"
                style={{ color: riskBar.color }}
              >
                {riskBar.label}
              </span>
            </div>

            {/* Vertical divider */}
            {trustReport && <Separator orientation="vertical" className="h-4 hidden sm:block" />}

            {/* Stat pills */}
            {trustReport && (
              <>
                <StatPill
                  count={trustReport.auto_verified}
                  label="Auto-verified"
                  colorClass="text-green-700"
                  dotClass="bg-green-500"
                  tooltip="The generated Python was executed against the same input data as the SAS and the outputs matched — schema, row count, and aggregates all pass. Safe to accept without manual review."
                />
                <StatPill
                  count={trustReport.needs_review}
                  label="Needs review"
                  colorClass="text-amber-700"
                  dotClass="bg-amber-500"
                  tooltip="Translation ran but reconciliation flagged differences, and the LLM's own confidence was low. A human should inspect these blocks before accepting the migration."
                />
                <StatPill
                  count={trustReport.manual_todo}
                  label="Manual TODO"
                  colorClass="text-muted-foreground"
                  dotClass="bg-border"
                  tooltip="Blocks the migration planner marked as manual, manual_ingestion, or skip — constructs that cannot be auto-translated. A developer must write the Python equivalent by hand."
                />
                <StatPill
                  count={trustReport.failed_reconciliation}
                  label="Failed recon"
                  colorClass="text-red-700"
                  dotClass="bg-red-500"
                  tooltip="The generated Python executed successfully but produced output that did not match the SAS reference data. These blocks need refinement or manual correction."
                />
              </>
            )}
          </div>
          {planData.risk_explanation && (
            <p className="text-xs text-muted-foreground leading-relaxed">
              {planData.risk_explanation}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Attention strip */}
      {trustReport &&
        (trustReport.needs_review > 0 || trustReport.failed_reconciliation > 0) && (
          <div className="flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50/60 px-4 py-2.5 text-sm text-amber-800">
            <AlertTriangle size={14} className="shrink-0 mt-0.5 text-amber-500" aria-hidden />
            <span className="text-xs leading-relaxed">
              {trustReport.needs_review > 0 && (
                <>
                  <strong>{trustReport.needs_review}</strong> block
                  {trustReport.needs_review !== 1 ? "s" : ""} need review
                </>
              )}
              {trustReport.needs_review > 0 && trustReport.failed_reconciliation > 0 && " · "}
              {trustReport.failed_reconciliation > 0 && (
                <>
                  <strong>{trustReport.failed_reconciliation}</strong> reconciliation
                  {trustReport.failed_reconciliation !== 1 ? "s" : ""} failed
                </>
              )}
              {" — use the strategy filters below to locate them."}
            </span>
          </div>
        )}

      {/* Block plan section */}
      {planData?.block_plans && planData.block_plans.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-foreground">Blocks</h2>
            <Badge variant="secondary" className="text-xs font-mono">
              {planData.block_plans.length}
            </Badge>
          </div>
          <BlockPlanTable
            blockPlans={planData.block_plans}
            isProposed={isProposed}
            trustBlocks={trustBlocks}
            jobId={jobId}
            isAccepted={jobStatus === "accepted"}
            onBlockRefineSuccess={onBlockRefineSuccess}
            jobPythonCode={jobPythonCode}
            generatedFiles={generatedFiles}
          />
        </div>
      )}
    </div>
    </TooltipProvider>
  );
}
