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
// AssessmentPanel
// ---------------------------------------------------------------------------

const VERDICT_STYLES = {
  red: { bg: "bg-red-50 border-red-200", badge: "bg-red-100 text-red-800", dot: "bg-red-500" },
  amber: { bg: "bg-amber-50 border-amber-200", badge: "bg-amber-100 text-amber-800", dot: "bg-amber-500" },
  green: { bg: "bg-green-50 border-green-200", badge: "bg-green-100 text-green-800", dot: "bg-green-500" },
};

function AssessmentPanel({ assessment }: { assessment: AnalyseResponse }): React.ReactElement {
  const { stats } = assessment;
  const [collapsed, setCollapsed] = useState(true);

  const verdict =
    stats.needs_manual > 0 ? "red" : stats.review_recommended > 0 || stats.best_effort > 0 ? "amber" : "green";
  const style = VERDICT_STYLES[verdict];

  // Show "< 1 hr" rather than "0–0.1 hr" for small pipelines — a zero looks like a bug.
  const lowHr = Math.round((stats.estimated_minutes_low / 60) * 10) / 10;
  const highHr = Math.round((stats.estimated_minutes_high / 60) * 10) / 10;
  const effortStr = highHr < 1 ? "< 1 hr" : lowHr === highHr ? `~${lowHr} hr` : `${lowHr}–${highHr} hr`;

  // Include all tier counts inline so the expanded tile grid is not needed.
  const summaryLine =
    verdict === "red"
      ? `${stats.needs_manual} cannot auto-convert · ${stats.review_recommended + stats.best_effort} review · ${stats.auto_converts} auto · ${effortStr}`
      : verdict === "amber"
        ? `${stats.review_recommended + stats.best_effort} need review · ${stats.auto_converts} auto-convert · ${effortStr}`
        : `All ${stats.auto_converts} blocks auto-convert · ${effortStr}`;

  const uniqueMissingDeps = [...new Map(assessment.missing_dependencies.map((d) => [d.name, d])).values()];
  const hasBlockers =
    stats.needs_manual > 0 || uniqueMissingDeps.length > 0 || assessment.circular_dependencies.length > 0;

  // Only show the expand toggle when there is detail worth showing.
  const hasExpandableDetail =
    assessment.sensitive_data_findings.length > 0 || uniqueMissingDeps.length > 0;

  return (
    <div className={`rounded-lg border p-4 space-y-3 ${style.bg}`}>
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${style.badge}`}>
              {verdict === "red" ? "🔴 Not ready" : verdict === "amber" ? "🟡 Review needed" : "🟢 Ready"}
            </span>
            <span className="text-xs text-muted-foreground">{summaryLine}</span>
          </div>
          {assessment.pipeline_description && (
            <p className="text-xs text-foreground/80 leading-relaxed line-clamp-2">
              {assessment.pipeline_description}
            </p>
          )}
        </div>
        {hasExpandableDetail && (
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground shrink-0 cursor-pointer"
          >
            {collapsed ? "Show details" : "Hide"}
          </button>
        )}
      </div>

      {/* Blocker row — always visible when blockers exist */}
      {hasBlockers && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {stats.needs_manual > 0 && (
            <span className="text-red-700">⚠ {stats.needs_manual} block(s) require manual implementation</span>
          )}
          {uniqueMissingDeps.length > 0 && (
            <span className="text-amber-700">⚠ {uniqueMissingDeps.length} missing macro/include file(s)</span>
          )}
          {assessment.circular_dependencies.length > 0 && (
            <span className="text-red-700">⚠ Circular dependency detected</span>
          )}
        </div>
      )}

      {/* Expanded detail: sensitive data patterns and missing dep names.
          The tier counts are already in the summary line so no tile grid here. */}
      {hasExpandableDetail && !collapsed && (
        <div className="space-y-3 pt-1 border-t border-current/10">
          {assessment.sensitive_data_findings.length > 0 && (
            <div className="text-xs text-red-700 bg-red-50 rounded p-2">
              🔒 Sensitive data detected:{" "}
              {[...new Set(assessment.sensitive_data_findings.map((f) => f.pattern))].join(", ")}
            </div>
          )}
          {uniqueMissingDeps.length > 0 && (
            <ul className="text-xs text-muted-foreground space-y-0.5 list-disc list-inside">
              {uniqueMissingDeps.slice(0, 5).map((d) => (
                <li key={d.name}>{d.name.split("/").pop() ?? d.name}</li>
              ))}
              {uniqueMissingDeps.length > 5 && (
                <li className="text-muted-foreground/60">+{uniqueMissingDeps.length - 5} more</li>
              )}
            </ul>
          )}
        </div>
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
      <div className="space-y-4">
        {assessmentData && (
          <>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pre-migration assessment</p>
            <AssessmentPanel assessment={assessmentData} />
          </>
        )}
        <p className="text-sm text-muted-foreground">
          Migration plan available once migration completes.
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        {assessmentData && (
          <>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pre-migration assessment</p>
            <AssessmentPanel assessment={assessmentData} />
          </>
        )}
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
      <div className="space-y-4">
        {assessmentData && (
          <>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pre-migration assessment</p>
            <AssessmentPanel assessment={assessmentData} />
          </>
        )}
        <p className="text-sm text-muted-foreground">
          No migration plan available for this job.
        </p>
      </div>
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

  return (
    <TooltipProvider>
      <div className="h-full min-h-0 overflow-y-auto space-y-4 pb-6">
        {/* Pre-migration assessment */}
        {assessmentData && (
          <>
            <div className="flex items-baseline gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pre-migration assessment</p>
              <span className="text-xs text-muted-foreground/50">predicted before run</span>
            </div>
            <AssessmentPanel assessment={assessmentData} />
          </>
        )}

        {/* Migration plan */}
        {assessmentData && (
          <div className="flex items-baseline gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Migration plan</p>
            <span className="text-xs text-muted-foreground/50">actual results after run</span>
          </div>
        )}
        <Card className="border-border bg-muted/30">
          <CardContent className="p-0 flex flex-col divide-y divide-border">
            {/* Top — summary text, full width */}
            <div className="flex items-center px-5 py-2">
              <p className="text-sm text-foreground leading-relaxed w-full">
                {planData.summary ?? (
                  <span className="italic text-muted-foreground">
                    No summary available.
                  </span>
                )}
              </p>
            </div>

            {/* Bottom — stats centered */}
            <div className="flex items-center justify-center gap-4 px-5 py-2 flex-wrap">
              {/* Confidence bar */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground shrink-0">
                  Confidence
                </span>
                <Progress
                  value={confidencePct}
                  className="h-1.5 w-20 **:data-[slot=progress-indicator]:bg-(--bar-fill)"
                  style={
                    { "--bar-fill": confidenceColor } as React.CSSProperties
                  }
                />
                <span
                  className="text-xs font-semibold tabular-nums"
                  style={{ color: confidenceColor }}
                >
                  {confidencePct}%
                </span>
              </div>

              <Separator
                orientation="vertical"
                className="h-4 hidden sm:block"
              />

              {/* Risk bar */}
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

              {/* Stat pills */}
              {trustReport && (
                <>
                  <Separator
                    orientation="vertical"
                    className="h-4 hidden sm:block"
                  />
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
          </CardContent>
        </Card>

        {/* Block plan section */}
        {planData?.block_plans && planData.block_plans.length > 0 && (
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setBlocksCollapsed((v) => !v)}
              className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
            >
              {blocksCollapsed ? (
                <ChevronRight
                  size={14}
                  className="text-muted-foreground shrink-0"
                />
              ) : (
                <ChevronDown
                  size={14}
                  className="text-muted-foreground shrink-0"
                />
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
            {!blocksCollapsed && (
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
        )}
      </div>
    </TooltipProvider>
  );
}
