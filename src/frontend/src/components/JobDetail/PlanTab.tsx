import { getJobPlan, getJobTrustReport } from "@/api/jobs";
import type {
  BlockOverride,
  JobStatusValue,
  TrustReportBlock,
  TrustReportResponse,
} from "@/api/types";
import { useQuery } from "@tanstack/react-query";
import { Eye, Shield, Wrench, XCircle } from "lucide-react";
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
  const CONFIDENCE_PCT: Record<string, number> = {
    high: 90,
    medium: 65,
    low: 40,
    very_low: 20,
    unknown: 0,
  };
  // Use exact score if available, otherwise fall back to band estimate
  const confidencePct = trustReport
    ? Math.round(
        (trustReport.overall_confidence_score ??
          CONFIDENCE_PCT[overallConfidence] / 100) * 100,
      )
    : CONFIDENCE_PCT[overallConfidence];

  const RISK_BAR: Record<
    string,
    { width: string; color: string; label: string }
  > = {
    low: { width: "33%", color: "#22c55e", label: "Low" },
    medium: { width: "66%", color: "#f59e0b", label: "Medium" },
    high: { width: "100%", color: "#ef4444", label: "High" },
  };
  const riskBar = RISK_BAR[planData.overall_risk] ?? {
    width: "0%",
    color: "#9ca3af",
    label: planData.overall_risk,
  };

  return (
    <div className="h-full min-h-0 overflow-y-auto space-y-6 pb-6">
      {/* 1. Summary card */}
      <div className="rounded-lg border border-border bg-muted/40 p-4 space-y-1">
        {planData.summary ? (
          <p className="text-sm font-medium text-foreground text-left">
            {planData.summary}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground italic text-left">
            No summary available.
          </p>
        )}
        {planData.risk_explanation && (
          <p className="text-xs text-muted-foreground text-left">
            {planData.risk_explanation}
          </p>
        )}
      </div>

      {/* 2. Confidence + Risk bars side by side */}
      <div className="flex justify-center items-center gap-12 pt-2">
        {/* Confidence bar */}
        <div className="flex flex-col items-center gap-2">
          <div style={{ width: 160 }}>
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>Overall Confidence</span>
              <span
                className="font-semibold tabular-nums"
                style={{ color: confidenceColor }}
              >
                {confidencePct}%
              </span>
            </div>
            <div className="h-3 rounded-full bg-gray-100 overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${confidencePct}%`,
                  backgroundColor: confidenceColor,
                }}
              />
            </div>
          </div>
        </div>
        {/* Risk bar */}
        <div className="flex flex-col items-center gap-2">
          <div style={{ width: 160 }}>
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>Overall Risk</span>
              <span
                className="font-semibold capitalize"
                style={{ color: riskBar.color }}
              >
                {riskBar.label}
              </span>
            </div>
            <div className="h-3 rounded-full bg-gray-100 overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: riskBar.width, backgroundColor: riskBar.color }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* 3. Status summary strip */}
      {trustReport && (
        <div className="grid grid-cols-4 gap-3">
          <div className="rounded-lg border border-green-200 bg-green-50 p-3 flex items-center gap-3">
            <Shield size={18} className="text-green-600 shrink-0" aria-hidden />
            <div>
              <p className="text-xl font-bold text-green-700">
                {trustReport.auto_verified}
              </p>
              <p className="text-xs font-medium text-green-600 mt-0.5">
                Auto-verified
              </p>
            </div>
          </div>
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 flex items-center gap-3">
            <Eye size={18} className="text-amber-600 shrink-0" aria-hidden />
            <div>
              <p className="text-xl font-bold text-amber-700">
                {trustReport.needs_review}
              </p>
              <p className="text-xs font-medium text-amber-600 mt-0.5">
                Needs review
              </p>
            </div>
          </div>
          <div className="rounded-lg border border-border bg-muted/50 p-3 flex items-center gap-3">
            <Wrench
              size={18}
              className="text-muted-foreground shrink-0"
              aria-hidden
            />
            <div>
              <p className="text-xl font-bold text-muted-foreground">
                {trustReport.manual_todo}
              </p>
              <p className="text-xs font-medium text-muted-foreground mt-0.5">
                Manual TODO
              </p>
            </div>
          </div>
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 flex items-center gap-3">
            <XCircle size={18} className="text-red-600 shrink-0" aria-hidden />
            <div>
              <p className="text-xl font-bold text-red-700">
                {trustReport.failed_reconciliation}
              </p>
              <p className="text-xs font-medium text-red-600 mt-0.5">
                Failed recon
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 4. BlockPlanTable */}
      {planData?.block_plans && planData.block_plans.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Block plan</h3>
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
  );
}
