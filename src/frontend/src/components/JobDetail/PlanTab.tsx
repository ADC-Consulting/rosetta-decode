import { getJobAssessment, getJobPlan, getJobTrustReport } from "@/api/jobs";
import type {
  AnalyseResponse,
  BlockOverride,
  BlockPlan,
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
// AssessmentCallouts — missing deps, circular deps, PII.
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
          ⚠ {uniqueMissingDeps.length} file{uniqueMissingDeps.length > 1 ? "s" : ""} referenced but not uploaded — translations for dependent blocks may be incomplete ({uniqueMissingDeps.map((d) => d.name.split("/").pop() ?? d.name).join(", ")})
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
// AttentionBlocksSummary — PM-facing per-block summary for blocks that need
// action. Shows only the blocks requiring attention with plain-language
// rationale, so a code owner can assess risk without reading the full table.
// ---------------------------------------------------------------------------

function AttentionBlocksSummary({
  blockPlans,
  trustBlocks,
}: {
  blockPlans: BlockPlan[];
  trustBlocks: Record<string, TrustReportBlock>;
}): React.ReactElement | null {
  const attentionBlocks = blockPlans.filter(
    (b) => trustBlocks[b.block_id]?.needs_attention,
  );

  if (attentionBlocks.length === 0) return null;

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Needs attention
      </p>
      {attentionBlocks.map((block) => {
        const isManual = block.strategy === "manual";
        const confidencePct = Math.round(block.confidence_score * 100);

        return (
          <div
            key={block.block_id}
            className={`rounded-md border px-4 py-3 space-y-1.5 ${
              isManual
                ? "border-red-200 bg-red-50/50"
                : "border-amber-200 bg-amber-50/50"
            }`}
          >
            <div className="space-y-0.5">
              <span
                className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-full ${
                  isManual
                    ? "bg-red-100 text-red-800"
                    : "bg-amber-100 text-amber-800"
                }`}
              >
                {isManual ? "🔴 Manual implementation required" : "🟡 Review recommended"}
              </span>
              <p className="text-xs text-muted-foreground font-mono">
                {block.source_file} · line {block.start_line} · {block.block_type.replace(/_/g, " ").toLowerCase()}
                {!isManual && ` · ${confidencePct}% confident`}
              </p>
            </div>
            {block.rationale && (
              <p className="text-xs text-foreground/70 leading-relaxed">
                {block.rationale}
              </p>
            )}
            {isManual && (
              <p className="text-xs text-red-700 font-medium">
                Accepting now will run this block as placeholder code — the pipeline will be incomplete until a developer implements it.
              </p>
            )}
          </div>
        );
      })}
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
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-md" />
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

  const hasAttentionBlocks =
    trustReport && (trustReport.needs_review + trustReport.manual_todo) > 0;

  const n = (count: number, noun: string) => `${count} ${noun}${count === 1 ? "" : "s"}`;
  const recommendation = trustReport
    ? trustReport.manual_todo > 0
      ? {
          text: `Not ready to accept — ${n(trustReport.manual_todo, "block")} requires manual implementation before the pipeline will run correctly.`,
          classes: "border-l-2 border-red-400 bg-red-50/60 text-red-800",
        }
      : trustReport.needs_review > 0
        ? {
            text: `Review recommended — ${n(trustReport.needs_review, "block")} was translated but reconciliation flagged differences. A developer should verify the output before accepting.`,
            classes: "border-l-2 border-amber-400 bg-amber-50/60 text-amber-800",
          }
        : {
            text: `Ready to accept — all ${n(trustReport.auto_verified, "block")} auto-verified against reference data.`,
            classes: "border-l-2 border-green-400 bg-green-50/60 text-green-800",
          }
    : null;

  return (
    <TooltipProvider>
      <div className="h-full min-h-0 overflow-y-auto space-y-3 pb-6">
        {/* Plan summary card + attention section grouped tightly */}
        <Card className="overflow-hidden border-border bg-muted/30">
          <CardContent className="p-0 flex flex-col divide-y divide-border">
            {/* Go/no-go recommendation */}
            {recommendation && (
              <div className={`px-5 py-2.5 text-xs font-medium ${recommendation.classes}`}>
                {recommendation.text}
              </div>
            )}

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

            {/* Assessment callouts — missing deps, circular deps, PII */}
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
                <span className="text-xs text-muted-foreground shrink-0">Risk</span>
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
                    count={trustReport.needs_review > 0 ? trustReport.needs_review : undefined}
                    label="Needs review"
                    colorClass="text-amber-700"
                    dotClass="bg-amber-500"
                    tooltip="Translation ran but reconciliation flagged differences, and the LLM's own confidence was low. A human should inspect these blocks before accepting the migration."
                  />
                  <StatPill
                    count={trustReport.manual_todo > 0 ? trustReport.manual_todo : undefined}
                    label="Manual TODO"
                    colorClass="text-red-700"
                    dotClass="bg-red-500"
                    tooltip="Blocks the migration planner marked as manual — constructs that cannot be auto-translated. A developer must write the Python equivalent by hand."
                  />
                </>
              )}
            </div>
          </CardContent>
        </Card>

        {/* PM-facing attention summary — tightly coupled to plan card above */}
        {hasAttentionBlocks && (
          <AttentionBlocksSummary
            blockPlans={planData.block_plans}
            trustBlocks={trustBlocks}
          />
        )}

        {/* Developer-facing block table — collapsed by default, separated from PM content */}
        {planData?.block_plans && planData.block_plans.length > 0 && (
          <div className="space-y-2 pt-1">
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
