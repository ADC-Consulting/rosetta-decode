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
import { TooltipProvider } from "@/components/ui/tooltip";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useRef, useState } from "react";
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
// StatCard
// ---------------------------------------------------------------------------

type StatFilterKey =
  | "auto_verified"
  | "needs_review"
  | "manual_todo"
  | "failed_reconciliation";

function StatCard({
  filterKey,
  count,
  total,
  label,
  colorClasses,
  activeFilter,
  onFilterChange,
}: {
  filterKey: StatFilterKey;
  count: number | undefined;
  total: number | undefined;
  label: string;
  colorClasses: string;
  activeFilter: StatFilterKey | null;
  onFilterChange: (key: StatFilterKey | null) => void;
}): React.ReactElement | null {
  if (count === undefined) return null;
  const isActive = activeFilter === filterKey;
  return (
    <button
      type="button"
      aria-pressed={isActive}
      onClick={() => onFilterChange(isActive ? null : filterKey)}
      className={[
        "flex flex-col items-center justify-center gap-0.5 rounded-lg border p-3 min-w-[80px]",
        "cursor-pointer select-none transition-all",
        colorClasses,
        isActive
          ? "ring-2 ring-offset-1 ring-current shadow-sm"
          : "hover:opacity-80",
      ].join(" ")}
    >
      <span className="text-2xl font-bold tabular-nums leading-none">
        {count}
      </span>
      {total !== undefined && (
        <span className="text-xs text-muted-foreground leading-none">
          of {total}
        </span>
      )}
      <span className="text-xs font-medium mt-0.5 leading-tight text-center">
        {label}
      </span>
    </button>
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
  const [reviewCollapsed, setReviewCollapsed] = useState(true);
  const [activeStatFilter, setActiveStatFilter] =
    useState<StatFilterKey | null>(null);
  const blocksRef = useRef<HTMLDivElement>(null);

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
        {/* Single summary card */}
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

              {/* Stat cards */}
              {trustReport && (
                <>
                  <Separator
                    orientation="vertical"
                    className="h-4 hidden sm:block"
                  />
                  <div className="flex flex-col gap-2 w-full">
                    <div className="grid grid-cols-4 gap-3">
                      <StatCard
                        filterKey="auto_verified"
                        count={trustReport.auto_verified}
                        total={trustReport.total_blocks}
                        label="Auto-verified"
                        colorClasses="text-green-700 bg-green-50 border-green-200"
                        activeFilter={activeStatFilter}
                        onFilterChange={(key) => {
                          setActiveStatFilter(key);
                          if (key !== null) {
                            setBlocksCollapsed(false);
                            setTimeout(
                              () =>
                                blocksRef.current?.scrollIntoView({
                                  behavior: "smooth",
                                  block: "start",
                                }),
                              50,
                            );
                          }
                        }}
                      />
                      <StatCard
                        filterKey="needs_review"
                        count={trustReport.needs_review}
                        total={trustReport.total_blocks}
                        label="Needs review"
                        colorClasses="text-amber-700 bg-amber-50 border-amber-200"
                        activeFilter={activeStatFilter}
                        onFilterChange={(key) => {
                          setActiveStatFilter(key);
                          if (key !== null) {
                            setBlocksCollapsed(false);
                            setTimeout(
                              () =>
                                blocksRef.current?.scrollIntoView({
                                  behavior: "smooth",
                                  block: "start",
                                }),
                              50,
                            );
                          }
                        }}
                      />
                      <StatCard
                        filterKey="manual_todo"
                        count={trustReport.manual_todo}
                        total={trustReport.total_blocks}
                        label="Manual TODO"
                        colorClasses="text-muted-foreground bg-muted border-border"
                        activeFilter={activeStatFilter}
                        onFilterChange={(key) => {
                          setActiveStatFilter(key);
                          if (key !== null) {
                            setBlocksCollapsed(false);
                            setTimeout(
                              () =>
                                blocksRef.current?.scrollIntoView({
                                  behavior: "smooth",
                                  block: "start",
                                }),
                              50,
                            );
                          }
                        }}
                      />
                      <StatCard
                        filterKey="failed_reconciliation"
                        count={trustReport.failed_reconciliation}
                        total={trustReport.total_blocks}
                        label="Failed reconciliation"
                        colorClasses="text-red-700 bg-red-50 border-red-200"
                        activeFilter={activeStatFilter}
                        onFilterChange={(key) => {
                          setActiveStatFilter(key);
                          if (key !== null) {
                            setBlocksCollapsed(false);
                            setTimeout(
                              () =>
                                blocksRef.current?.scrollIntoView({
                                  behavior: "smooth",
                                  block: "start",
                                }),
                              50,
                            );
                          }
                        }}
                      />
                    </div>
                    {activeStatFilter && (
                      <div className="flex justify-end">
                        <button
                          type="button"
                          onClick={() => setActiveStatFilter(null)}
                          className="text-[11px] text-muted-foreground hover:text-foreground underline underline-offset-2 cursor-pointer"
                        >
                          Clear filter ×
                        </button>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Block plan section */}
        {planData?.block_plans && planData.block_plans.length > 0 && (
          <div ref={blocksRef} className="space-y-2">
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
                activeStatFilter={activeStatFilter}
                onClearStatFilter={() => setActiveStatFilter(null)}
              />
            )}
          </div>
        )}

        {trustReport?.review_queue && trustReport.review_queue.length > 0 && (
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setReviewCollapsed((v) => !v)}
              className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
            >
              {reviewCollapsed ? (
                <ChevronRight size={14} className="text-muted-foreground shrink-0" />
              ) : (
                <ChevronDown size={14} className="text-muted-foreground shrink-0" />
              )}
              <h2 className="text-sm font-semibold text-foreground">Review queue</h2>
              <Badge variant="secondary" className="text-xs font-mono">
                {trustReport.review_queue.length}
              </Badge>
            </button>
            {!reviewCollapsed && (() => {
              const CRIT_ORDER: Record<string, number> = {
                critical: 0, high: 1, medium: 2, low: 3,
              };
              const STRAT_COLOR: Record<string, string> = {
                translated: "bg-green-100 text-green-800",
                translated_with_review: "bg-amber-100 text-amber-800",
                manual: "bg-red-100 text-red-800",
              };
              const STRAT_LABEL: Record<string, string> = {
                translated: "Translated",
                translated_with_review: "Review needed",
                manual: "Manual",
              };
              const CRIT_COLOR: Record<string, string> = {
                critical: "text-red-700 bg-red-50 border border-red-200",
                high: "text-orange-700 bg-orange-50 border border-orange-200",
                medium: "text-amber-700 bg-amber-50 border border-amber-200",
                low: "text-green-700 bg-green-50 border border-green-200",
              };
              const sorted = [...trustReport.review_queue]
                .sort((a, b) => (CRIT_ORDER[a.criticality] ?? 99) - (CRIT_ORDER[b.criticality] ?? 99));
              return (
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-muted/50 text-xs text-muted-foreground">
                        <th className="px-3 py-2 text-left font-medium">Block ID</th>
                        <th className="px-3 py-2 text-left font-medium">Strategy</th>
                        <th className="px-3 py-2 text-left font-medium">Criticality</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sorted.map((block) => (
                        <tr key={block.block_id} className="border-t border-border">
                          <td className="px-3 py-2 font-mono text-xs text-muted-foreground max-w-[200px] truncate">
                            {block.block_id}
                          </td>
                          <td className="px-3 py-2">
                            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${STRAT_COLOR[block.strategy] ?? "bg-muted text-muted-foreground"}`}>
                              {STRAT_LABEL[block.strategy] ?? block.strategy}
                            </span>
                          </td>
                          <td className="px-3 py-2">
                            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${CRIT_COLOR[block.criticality] ?? "text-muted-foreground bg-muted border border-border"}`}>
                              {block.criticality}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })()}
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
