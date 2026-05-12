import { getJobAssessment, getJobPlan, getJobTrustReport } from "@/api/jobs";
import type {
  AnalyseResponse,
  AssessedBlock,
  BlockOverride,
  BlockPlan,
  JobPlanResponse,
  JobStatusValue,
  TrustReportBlock,
  TrustReportResponse,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
// AssessmentCallouts — missing deps (elevated card), circular deps, PII.
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
    <div className="px-5 py-2 space-y-2 border-t border-border">
      {/* Missing deps — elevated to distinct amber card */}
      {uniqueMissingDeps.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50/60 px-4 py-2.5 space-y-0.5">
          <p className="text-xs font-semibold text-amber-800">Translation may be incomplete</p>
          <p className="text-xs text-amber-700/80">
            {uniqueMissingDeps.length} source file{uniqueMissingDeps.length > 1 ? "s" : ""} referenced but not uploaded — translations for dependent blocks may be incomplete ({uniqueMissingDeps.map((d) => d.name.split("/").pop() ?? d.name).join(", ")})
          </p>
        </div>
      )}
      {/* Circular dep and PII remain as inline spans */}
      {(hasCircular || piiPatterns.length > 0) && (
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
          {hasCircular && (
            <span className="text-red-700">⚠ Circular dependency — execution order cannot be resolved</span>
          )}
          {piiPatterns.length > 0 && (
            <span className="text-orange-700">
              🔒 Sensitive data detected: {piiPatterns.join(", ")}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AttentionBlocksSummary — PM-facing per-block summary for blocks that need
// action. Shows only the blocks requiring attention with plain-language
// rationale and which output datasets are affected.
// ---------------------------------------------------------------------------

function AttentionBlocksSummary({
  blockPlans,
  trustBlocks,
  assessedBlocks,
}: {
  blockPlans: BlockPlan[];
  trustBlocks: Record<string, TrustReportBlock>;
  assessedBlocks?: AssessedBlock[];
}): React.ReactElement | null {
  const attentionBlocks = blockPlans.filter(
    (b) => trustBlocks[b.block_id]?.needs_attention,
  );

  if (attentionBlocks.length === 0) return null;

  const assessedMap: Record<string, AssessedBlock> = assessedBlocks
    ? Object.fromEntries(assessedBlocks.map((b) => [b.block_id, b]))
    : {};

  const count = attentionBlocks.length;

  return (
    <div className="px-5 py-3 space-y-2.5">
      <p className="text-xs font-semibold text-foreground/60">
        {count === 1 ? "1 block needs attention" : `${count} blocks need attention`}
      </p>
      {attentionBlocks.map((block) => {
        const isManual = block.strategy === "manual";
        const confidencePct = Math.round(block.confidence_score * 100);
        const assessed = assessedMap[block.block_id];
        const affectsDatasets = assessed?.output_datasets ?? [];

        return (
          <div
            key={block.block_id}
            className={`rounded-md border px-4 py-3 space-y-1.5 ${
              isManual
                ? "border-red-200 bg-red-50/50"
                : "border-amber-200 bg-amber-50/50"
            }`}
          >
            <div className="space-y-1.5">
              <span
                className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${
                  isManual
                    ? "bg-red-100 text-red-800"
                    : "bg-amber-100 text-amber-800"
                }`}
              >
                <span>{isManual ? "🔴" : "🟡"}</span>
                <span>{isManual ? "Manual implementation required" : "Review recommended"}</span>
              </span>
              <p className="text-xs text-muted-foreground font-mono">
                {block.source_file} · line {block.start_line} · {block.block_type}
                {!isManual && ` · ${confidencePct}% confident`}
              </p>
              {affectsDatasets.length > 0 && (
                <p className="text-xs text-foreground/50">
                  Affects: {affectsDatasets.join(", ")}
                </p>
              )}
            </div>
            {block.rationale && (
              <p className="text-xs text-foreground/70 leading-relaxed">
                {block.rationale}
              </p>
            )}
            {isManual && (
              <p className="text-xs text-red-700 font-medium">
                ⚠ Accepting now will run this block as placeholder code — the pipeline will be incomplete until a developer implements it.
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
  onAccept,
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
  onAccept?: () => void;
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
  const isAcceptable = jobStatus === "proposed" || jobStatus === "under_review";
  const isGreen = !!trustReport && trustReport.manual_todo === 0 && trustReport.needs_review === 0;

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

  // S-F: scope summary — "2 SAS files · 15 blocks · 3 output datasets"
  const scopeParts: string[] = [];
  if (assessmentData?.filenames?.length) {
    const c = assessmentData.filenames.length;
    scopeParts.push(`${c} SAS file${c === 1 ? "" : "s"}`);
  }
  if (planData.block_plans.length) {
    const c = planData.block_plans.length;
    scopeParts.push(`${c} block${c === 1 ? "" : "s"}`);
  }
  if (assessmentData?.output_datasets?.length) {
    const c = assessmentData.output_datasets.length;
    scopeParts.push(`${c} output dataset${c === 1 ? "" : "s"}`);
  }

  const hasAttentionBlocks =
    trustReport && (trustReport.needs_review + trustReport.manual_todo) > 0;

  const n = (count: number, noun: string) => `${count} ${noun}${count === 1 ? "" : "s"}`;
  const recommendation = trustReport
    ? trustReport.manual_todo > 0
      ? {
          icon: "⚠",
          label: "Not ready to accept",
          detail: `${n(trustReport.manual_todo, "block")} could not be auto-translated and will produce placeholder code. The pipeline will be incomplete until a developer implements ${trustReport.manual_todo === 1 ? "it" : "them"}.`,
          classes: "border-l-2 border-red-400 bg-red-50/60 text-red-800",
        }
      : trustReport.needs_review > 0
        ? {
            icon: "⚠",
            label: "Review recommended",
            detail: `${n(trustReport.needs_review, "block")} was translated but the generated output differed from the original SAS. A developer should review those blocks before this pipeline is used in production.`,
            classes: "border-l-2 border-amber-400 bg-amber-50/60 text-amber-800",
          }
        : {
            icon: "✓",
            label: "Ready to accept",
            detail: `The generated Python matched the original SAS output — schema, row counts, and aggregates verified. Accepting marks this pipeline ready for use and retires the SAS workflow.`,
            classes: "border-l-[3px] border-green-500 bg-green-50 text-green-800",
          }
    : null;

  return (
    <TooltipProvider>
      <div className="h-full min-h-0 overflow-y-auto pb-6">
        <Card className="overflow-hidden border-border bg-muted/30">
          <CardContent className="p-0 flex flex-col divide-y divide-border">
            {/* Card header — label + effort + scope summary (S-F) */}
            <div className="px-5 py-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-foreground/50 uppercase tracking-wide">
                  Migration plan
                </span>
                {effortStr && (
                  <span className="text-xs text-muted-foreground">
                    Est.{" "}
                    <span className="font-semibold text-foreground/70">
                      {effortStr}
                    </span>
                  </span>
                )}
              </div>
              {scopeParts.length > 0 && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {scopeParts.join(" · ")}
                </p>
              )}
            </div>

            {/* Go/no-go recommendation — verdict text only, no button (S-G) */}
            {recommendation && (
              <div className={`px-5 pt-4 pb-3 ${recommendation.classes}`}>
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-bold shrink-0 leading-none">
                    {recommendation.icon}
                  </span>
                  <span className="text-xs">
                    <span className="font-semibold">{recommendation.label}</span>
                    {" — "}
                    <span className="opacity-80">{recommendation.detail}</span>
                  </span>
                </div>
              </div>
            )}

            {/* Summary text */}
            <div className="flex items-center px-5 pt-4 pb-3">
              <p className="text-sm text-foreground/80 leading-relaxed w-full">
                {planData.summary ?? (
                  <span className="italic text-muted-foreground">
                    No summary available.
                  </span>
                )}
              </p>
            </div>

            {/* Reads — input sources (S-I) */}
            {assessmentData?.input_sources && assessmentData.input_sources.length > 0 && (
              <div className="flex items-baseline gap-3 px-5 py-2.5">
                <span className="text-xs font-semibold text-foreground/50 uppercase tracking-wide shrink-0">
                  Reads
                </span>
                <span className="text-xs text-foreground/70 leading-relaxed">
                  {assessmentData.input_sources.join(", ")}
                </span>
              </div>
            )}

            {/* Produces — output dataset scope */}
            {assessmentData?.output_datasets && assessmentData.output_datasets.length > 0 && (
              <div className="flex items-baseline gap-3 px-5 py-2.5">
                <span className="text-xs font-semibold text-foreground/50 uppercase tracking-wide shrink-0">
                  Produces
                </span>
                <span className="text-xs text-foreground/70 leading-relaxed">
                  {assessmentData.output_datasets.join(", ")}
                </span>
              </div>
            )}

            {/* Stats row — moved above callouts (S-H) */}
            <div className="flex items-center justify-start gap-4 px-5 py-2 flex-wrap">
              {trustReport && (
                <>
                  <div className="flex items-center gap-2">
                    <Tooltip>
                      <TooltipTrigger
                        render={<span className="text-xs text-muted-foreground shrink-0 cursor-help" />}
                      >
                        Confidence
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="max-w-72 text-xs leading-relaxed whitespace-normal">
                        The AI translator's self-assessed confidence in its own translation quality, averaged across all blocks. Reconciliation results above are the stronger signal — a block can pass verification even at moderate confidence.
                      </TooltipContent>
                    </Tooltip>
                    <Progress
                      value={confidencePct}
                      className="h-1.5 w-28 **:data-[slot=progress-indicator]:bg-(--bar-fill)"
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
                <Tooltip>
                  <TooltipTrigger
                    render={<span className="text-xs text-muted-foreground shrink-0 cursor-help" />}
                  >
                    Complexity
                  </TooltipTrigger>
                  <TooltipContent side="bottom" className="max-w-72 text-xs leading-relaxed whitespace-normal">
                    How complex the SAS patterns were to translate. Higher complexity means some constructs required interpretation. This is not a measure of whether the translation succeeded — check the reconciliation result above for that.{planData.risk_explanation ? ` ${planData.risk_explanation}` : ""}
                  </TooltipContent>
                </Tooltip>
                <Progress
                  value={riskPctMap[planData.overall_risk] ?? 0}
                  className="h-1.5 w-28 **:data-[slot=progress-indicator]:bg-(--bar-fill)"
                  style={{ "--bar-fill": riskBar.color } as React.CSSProperties}
                />
                <span
                  className="text-xs font-semibold capitalize"
                  style={{ color: riskBar.color }}
                >
                  {riskBar.label}
                </span>
              </div>

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

            {/* Assessment callouts — missing deps (elevated), circular deps, PII (S-K) */}
            {assessmentData && <AssessmentCallouts assessment={assessmentData} />}

            {/* Attention blocks — with "Affects" per card (S-J) */}
            {hasAttentionBlocks && planData?.block_plans && (
              <AttentionBlocksSummary
                blockPlans={planData.block_plans}
                trustBlocks={trustBlocks}
                assessedBlocks={assessmentData?.blocks}
              />
            )}

            {/* Blocks toggle */}
            {planData?.block_plans && planData.block_plans.length > 0 && (
              <div>
                <button
                  type="button"
                  onClick={() => setBlocksCollapsed(!blocksCollapsed)}
                  className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity w-full px-5 py-3"
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
                  {trustReport && trustReport.manual_todo > 0 && (
                    <span className="text-xs text-red-600 font-medium">
                      · {trustReport.manual_todo} not ready
                    </span>
                  )}
                </button>
                {!blocksCollapsed && (
                  <div className="px-4 pb-4">
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
                  </div>
                )}
              </div>
            )}

            {/* Accept action row — standalone bottom row (S-G) */}
            {isAcceptable && onAccept ? (
              <div className="px-5 py-3 flex justify-end">
                {isGreen ? (
                  <Button
                    size="sm"
                    onClick={onAccept}
                    className="cursor-pointer bg-green-700 hover:bg-green-800 text-white text-xs h-7 px-3"
                  >
                    Accept migration
                  </Button>
                ) : trustReport?.manual_todo ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={onAccept}
                    className="cursor-pointer border-red-300 text-red-700 hover:bg-red-50 text-xs h-7 px-3"
                  >
                    Accept anyway
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={onAccept}
                    className="cursor-pointer text-xs h-7 px-3"
                  >
                    Accept migration
                  </Button>
                )}
              </div>
            ) : jobStatus === "accepted" ? (
              <div className="px-5 py-3">
                <span className="text-xs text-emerald-700 font-medium">
                  ✓ This migration has been accepted
                </span>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  );
}
