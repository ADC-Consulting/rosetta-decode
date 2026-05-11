import { getJobAssessment, getJobPlan, getJobTrustReport } from "@/api/jobs";
import type {
  AnalyseResponse,
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
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
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
        <span className={`text-xs font-semibold tabular-nums ${colorClass}`}>
          {count}
        </span>
        <span className="text-xs text-muted-foreground">{label}</span>
      </TooltipTrigger>
      <TooltipContent
        side="bottom"
        className="max-w-65 text-xs leading-relaxed whitespace-normal text-center"
      >
        {tooltip}
      </TooltipContent>
    </Tooltip>
  );
}

// ---------------------------------------------------------------------------
// AssessmentCallouts — slim inline notes derived from the pre-migration
// assessment that remain relevant after the plan has been generated:
// missing macro/include files and detected PII patterns.
// ---------------------------------------------------------------------------

function AssessmentCallouts({
  assessment,
}: {
  assessment: AnalyseResponse;
}): React.ReactElement | null {
  const uniqueMissingDeps = [
    ...new Map(assessment.missing_dependencies.map((d) => [d.name, d])).values(),
  ];
  const piiPatterns = [
    ...new Set(assessment.sensitive_data_findings.map((f) => f.pattern)),
  ];
  const hasCircular = assessment.circular_dependencies.length > 0;

  if (uniqueMissingDeps.length === 0 && piiPatterns.length === 0 && !hasCircular) return null;

  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1 px-5 py-2 text-xs border-t border-border">
      {hasCircular && (
        <span className="text-red-700">⚠ Circular dependency — execution order cannot be resolved</span>
      )}
      {uniqueMissingDeps.length > 0 && (
        <span className="text-amber-700">
          ⚠ {uniqueMissingDeps.length} missing macro/include file(s):{" "}
          {uniqueMissingDeps.map((d) => d.name.split("/").pop() ?? d.name).join(", ")}
        </span>
      )}
      {piiPatterns.length > 0 && (
        <span className="text-orange-700">
          🔒 Sensitive data detected: {piiPatterns.join(", ")}
        </span>
      )}
    </div>
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
  setOverrides: React.Dispatch<
    React.SetStateAction<Record<string, BlockOverride>>
  >;
  onBlockRefineSuccess?: () => void;
  jobPythonCode?: string;
  generatedFiles?: Record<string, string>;
}): React.ReactElement {
  const trustReportEnabled =
    !!jobId &&
    (jobStatus === "proposed" ||
      jobStatus === "accepted" ||
      jobStatus === "done");

  const { data: planData, isLoading } = useQuery<JobPlanResponse | null>({
    queryKey: ["job", jobId, "plan"],
    queryFn: () => getJobPlan(jobId),
    enabled: !!jobId && isReviewable,
  });

  const { data: assessmentData } = useQuery<AnalyseResponse | null>({
    queryKey: ["job", jobId, "assessment"],
    queryFn: () => getJobAssessment(jobId),
    enabled: !!jobId,
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
  const [blocksCollapsed, setBlocksCollapsed] = useState(true);

  if (!isReviewable) {
    return (
      <p className="text-sm text-muted-foreground">
        Migration plan available once migration completes.
      </p>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28 w-full rounded-lg" />
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
  const confidenceColor =
    CONFIDENCE_COLOR[overallConfidence] ?? CONFIDENCE_COLOR["unknown"];
  const confidencePct = trustReport
    ? Math.round(
        (trustReport.overall_confidence_score ??
          CONFIDENCE_PCT[overallConfidence] / 100) * 100,
      )
    : CONFIDENCE_PCT[overallConfidence];

  const riskBar = RISK_BAR[planData.overall_risk] ?? {
    color: "#9ca3af",
    label: planData.overall_risk,
  };

  const effortStr = (() => {
    const s = assessmentData?.stats;
    if (!s) return null;
    const lo = Math.round((s.estimated_minutes_low / 60) * 10) / 10;
    const hi = Math.round((s.estimated_minutes_high / 60) * 10) / 10;
    return hi < 1 ? "< 1 hr" : lo === hi ? `~${lo} hr` : `${lo}–${hi} hr`;
  })();

  return (
    <TooltipProvider>
      <div className="h-full min-h-0 overflow-y-auto space-y-4 pb-6">
        <Card className="border-border bg-muted/30">
          <CardContent className="p-0 flex flex-col divide-y divide-border">
            {/* Summary text */}
            <div className="flex items-center px-5 py-2">
              <p className="text-sm text-foreground leading-relaxed w-full">
                {planData.summary ?? (
                  <span className="italic text-muted-foreground">
                    No summary available.
                  </span>
                )}
              </p>
            </div>

            {/* Assessment callouts — missing deps and PII only, if present */}
            {assessmentData && <AssessmentCallouts assessment={assessmentData} />}

            {/* Stats row */}
            <div className="flex items-center justify-start gap-4 px-5 py-2 flex-wrap">
              {trustReport && (
                <>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground shrink-0">
                      Confidence
                    </span>
                    <Progress
                      value={confidencePct}
                      className="h-1.5 w-20 **:data-[slot=progress-indicator]:bg-(--bar-fill)"
                      style={{ "--bar-fill": confidenceColor } as React.CSSProperties}
                    />
                    <span
                      className="text-xs font-semibold tabular-nums"
                      style={{ color: confidenceColor }}
                    >
                      {confidencePct}%
                    </span>
                  </div>
                  <Separator orientation="vertical" className="h-4 hidden sm:block" />
                </>
              )}

              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground shrink-0">
                  Risk
                </span>
                <Progress
                  value={riskPctMap[planData.overall_risk] ?? 0}
                  className="h-1.5 w-20 **:data-[slot=progress-indicator]:bg-(--bar-fill)"
                  style={{ "--bar-fill": riskBar.color } as React.CSSProperties}
                />
                <span
                  className="text-xs font-semibold capitalize"
                  style={{ color: riskBar.color }}
                >
                  {riskBar.label}
                </span>
              </div>

              {effortStr && (
                <>
                  <Separator orientation="vertical" className="h-4 hidden sm:block" />
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-muted-foreground shrink-0">Effort</span>
                    <span className="text-xs font-semibold tabular-nums">{effortStr}</span>
                  </div>
                </>
              )}

              {trustReport && (
                <>
                  <Separator orientation="vertical" className="h-4 hidden sm:block" />
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
                </>
              )}
            </div>

            {/* Blocks toggle */}
            {planData?.block_plans && planData.block_plans.length > 0 && (
              <div className="px-5 py-2">
                <button
                  type="button"
                  onClick={() => setBlocksCollapsed((v) => !v)}
                  className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
                >
                  {blocksCollapsed ? (
                    <ChevronRight size={14} className="text-muted-foreground shrink-0" />
                  ) : (
                    <ChevronDown size={14} className="text-muted-foreground shrink-0" />
                  )}
                  <h2 className="text-sm font-semibold text-foreground">Blocks</h2>
                  <Badge variant="secondary" className="text-xs font-mono">
                    {planData.block_plans.length}
                  </Badge>
                  {trustReport && trustReport.needs_review + trustReport.manual_todo > 0 && (
                    <span className="text-xs text-amber-600">
                      · {trustReport.needs_review + trustReport.manual_todo} need attention
                    </span>
                  )}
                </button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Block table — outside the card so it can expand to full width */}
        {!blocksCollapsed && planData?.block_plans && planData.block_plans.length > 0 && (
          <BlockPlanTable
            blockPlans={planData.block_plans}
            isProposed={isProposed}
            trustBlocks={trustBlocks}
            jobId={jobId}
            jobStatus={jobStatus}
            isAccepted={jobStatus === "accepted"}
            onBlockRefineSuccess={onBlockRefineSuccess}
            jobPythonCode={jobPythonCode}
            generatedFiles={generatedFiles}
          />
        )}
      </div>
    </TooltipProvider>
  );
}
