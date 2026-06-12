import { getJobPlan, getJobTrustReport, refineBlock } from "@/api/jobs";
import type {
  BlockOverride,
  BlockPlan,
  JobPlanResponse,
  JobStatusValue,
  TrustReportBlock,
  TrustReportFile,
  TrustReportResponse,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Info,
  Loader2,
  XCircle,
} from "lucide-react";
import { useRef, useState } from "react";
import BlockPlanTable from "./BlockPlanTable";
import ChangelogFeed from "./ChangelogFeed";
import ReportTab from "./ReportTab";

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
// Verdict strip
// ---------------------------------------------------------------------------

type VerdictState = "green" | "amber" | "red";

function getVerdict(trustReport: TrustReportResponse): VerdictState {
  if (trustReport.manual_todo > 0) return "red";
  if (trustReport.needs_review > 0 || trustReport.failed_reconciliation > 0) return "amber";
  return "green";
}

const VERDICT_STYLES: Record<
  VerdictState,
  {
    border: string;
    iconColor: string;
    headlineColor: string;
    textColor: string;
    Icon: React.ElementType;
  }
> = {
  green: {
    border: "border-l-4 border-l-green-500 bg-green-50",
    iconColor: "text-green-600",
    headlineColor: "text-green-800",
    textColor: "text-green-700",
    Icon: CheckCircle2,
  },
  amber: {
    border: "border-l-4 border-l-amber-500 bg-amber-50",
    iconColor: "text-amber-600",
    headlineColor: "text-amber-800",
    textColor: "text-amber-700",
    Icon: AlertTriangle,
  },
  red: {
    border: "border-l-4 border-l-red-500 bg-red-50",
    iconColor: "text-red-600",
    headlineColor: "text-red-800",
    textColor: "text-red-700",
    Icon: XCircle,
  },
};

// ---------------------------------------------------------------------------
// Confidence help content
// ---------------------------------------------------------------------------

const CONFIDENCE_HELP = `What the confidence score tells you:

• High (≥ 85%) — The translation agent was confident and, where a reference output was available, the Python output matched the SAS output exactly. Safe to treat as verified.

• Medium (65–84%) — The translation is likely correct but has not been fully verified, or the agent had some uncertainty. Worth a quick review.

• Low (40–64%) — The agent flagged uncertainty, or the output did not match the reference. Requires human review before the block can be trusted.

• Very Low (< 40%) — The agent had very low confidence, or the block failed reconciliation and was already low confidence. Likely needs manual rewrite.

What it does not guarantee:

A High confidence score does not mean the output is semantically correct in all edge cases — it means the automated checks passed and the LLM was confident. A human reviewer should still check any block that is business-critical.

Confidence is computed per block (DATA step, PROC, etc.), not per column or per row.

If no reference CSV was uploaded, there is no reconciliation to validate against — the score reflects LLM self-assessment only.

What criticality means:

Criticality is a post-translation signal that combines strategy, confidence, reconciliation outcome, and blast radius (how many downstream files depend on this block). It differs from Risk, which is a static pre-translation assessment of SAS construct complexity.

• Critical — Strategy is manual, or confidence was very low. Block needs human authoring or rewrite.
• High — Confidence was low, reconciliation failed, or this block feeds 3+ downstream files.
• Medium — Translation ran with medium confidence. Worth a spot check before accepting.
• Low — High confidence, reconciliation passed, minimal downstream impact.`;

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
// FileSection
// ---------------------------------------------------------------------------

function FileSection({ file }: { file: TrustReportFile }): React.ReactElement {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 text-left text-sm font-medium
          hover:bg-muted/40 transition-colors cursor-pointer"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="font-mono text-xs truncate">{file.source_file}</span>
        <span className="text-muted-foreground ml-2 shrink-0">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-border px-4 py-3 grid grid-cols-2 gap-x-8 gap-y-1 text-sm">
          <span className="text-muted-foreground">Total blocks</span>
          <span>{file.total_blocks}</span>
          <span className="text-muted-foreground">Auto-verified</span>
          <span className="text-green-700">{file.auto_verified}</span>
          <span className="text-muted-foreground">Needs review</span>
          <span className="text-amber-700">{file.needs_review}</span>
          <span className="text-muted-foreground">Manual TODO</span>
          <span className="text-muted-foreground">{file.manual_todo}</span>
          <span className="text-muted-foreground">Failed reconciliation</span>
          <span className="text-red-700">{file.failed_reconciliation}</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AttentionCards
// ---------------------------------------------------------------------------

function AttentionCards({
  queue,
  blockPlanMap,
  manualTodo,
  onShowAll,
  onViewBlocks,
}: {
  queue: TrustReportBlock[];
  blockPlanMap: Record<string, BlockPlan>;
  manualTodo: number;
  onShowAll: () => void;
  onViewBlocks: () => void;
}): React.ReactElement {
  const CRIT_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
  const top5 = [...queue]
    .sort((a, b) => {
      if (a.strategy === "manual" && b.strategy !== "manual") return -1;
      if (b.strategy === "manual" && a.strategy !== "manual") return 1;
      return (CRIT_ORDER[a.criticality] ?? 99) - (CRIT_ORDER[b.criticality] ?? 99);
    })
    .slice(0, 5);
  const remaining = queue.length - top5.length;

  const strategyLabel = (strategy: string, reconciliation: string | null): string => {
    if (strategy === "manual") return "Manual — cannot auto-convert";
    if (reconciliation === "fail") return "Reconciliation failed";
    return "Needs review";
  };

  const strategyColor = (strategy: string, reconciliation: string | null): string => {
    if (strategy === "manual") return "text-red-700 bg-red-50 border border-red-200";
    if (reconciliation === "fail") return "text-orange-700 bg-orange-50 border border-orange-200";
    return "text-amber-700 bg-amber-50 border border-amber-200";
  };

  const getRationale = (block: TrustReportBlock): string => {
    const bp = blockPlanMap[block.block_id];
    if (bp?.rationale) return bp.rationale;
    if (block.strategy === "manual") return `A ${block.block_type} block that requires manual implementation.`;
    if (block.reconciliation_status === "fail") return `A ${block.block_type} block that failed reconciliation.`;
    return `A ${block.block_type} block that needs review.`;
  };

  return (
    <div className="space-y-2">
      {manualTodo > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
          <AlertTriangle size={14} className="text-amber-600 shrink-0 mt-0.5" />
          <p className="text-xs text-amber-700">
            Manual blocks require code edits in the ETL tab before this pipeline will run.
          </p>
        </div>
      )}
      {top5.map(block => (
        <div key={block.block_id} className="rounded-lg border border-border bg-card px-4 py-3 space-y-1.5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="font-mono text-xs text-foreground truncate">{block.block_id}</p>
              <p className="font-mono text-xs text-muted-foreground truncate">{block.source_file}</p>
            </div>
            <span
              className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium shrink-0 ${strategyColor(block.strategy, block.reconciliation_status)}`}
            >
              {strategyLabel(block.strategy, block.reconciliation_status)}
            </span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">{getRationale(block)}</p>
          <button
            type="button"
            onClick={onViewBlocks}
            className="text-xs text-primary hover:underline"
          >
            View in blocks table →
          </button>
        </div>
      ))}
      {remaining > 0 && (
        <button type="button" onClick={onShowAll} className="text-xs text-primary hover:underline px-1">
          + {remaining} more · Show all →
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AttentionTable
// ---------------------------------------------------------------------------

function AttentionTable({
  queue,
  lineageAvailable,
}: {
  queue: TrustReportBlock[];
  lineageAvailable: boolean;
}): React.ReactElement {
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
  const CONF_COLOR: Record<string, string> = {
    high: "text-green-700 bg-green-50 border border-green-200",
    medium: "text-amber-700 bg-amber-50 border border-amber-200",
    low: "text-red-700 bg-red-50 border border-red-200",
    very_low: "text-red-700 bg-red-50 border border-red-200",
  };

  function ConfBadge({ value }: { value: string | null }): React.ReactElement {
    if (!value) return <span className="text-muted-foreground text-xs">—</span>;
    const cls = CONF_COLOR[value] ?? "text-muted-foreground bg-muted border border-border";
    return (
      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${cls}`}>
        {value}
      </span>
    );
  }

  function ReconIcon({ value }: { value: "pass" | "fail" | null }): React.ReactElement {
    if (!value) return <span className="text-muted-foreground text-xs">—</span>;
    if (value === "pass") return <CheckCircle2 size={14} className="text-green-600" />;
    return <XCircle size={14} className="text-red-600" />;
  }

  const showBlastRadius = lineageAvailable === true;

  const sorted = [...queue].sort((a, b) => {
    const cDiff =
      (CRIT_ORDER[a.criticality] ?? 99) - (CRIT_ORDER[b.criticality] ?? 99);
    if (cDiff !== 0) return cDiff;
    const aBlast = a.blast_radius ?? -1;
    const bBlast = b.blast_radius ?? -1;
    return bBlast - aBlast;
  });

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-muted/50 text-xs text-muted-foreground">
            <th className="px-3 py-2 text-left font-medium">Block ID</th>
            <th className="px-3 py-2 text-left font-medium">Source file</th>
            <th className="px-3 py-2 text-left font-medium">Strategy</th>
            <th className="px-3 py-2 text-left font-medium">Self confidence</th>
            <th className="px-3 py-2 text-left font-medium">Verified confidence</th>
            <th className="px-3 py-2 text-left font-medium">Reconciliation</th>
            <th className="px-3 py-2 text-left font-medium">Criticality</th>
            <th className="px-3 py-2 text-left font-medium">Human review</th>
            {showBlastRadius && (
              <th className="px-3 py-2 text-left font-medium">Blast radius</th>
            )}
          </tr>
        </thead>
        <tbody>
          {sorted.map((block) => (
            <tr key={block.block_id} className="border-t border-border">
              <td className="px-3 py-2 font-mono text-xs text-muted-foreground max-w-[160px] truncate">
                {block.block_id}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-muted-foreground max-w-[160px] truncate">
                {block.source_file}
              </td>
              <td className="px-3 py-2">
                <span
                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                    STRAT_COLOR[block.strategy] ?? "bg-muted text-muted-foreground"
                  }`}
                >
                  {STRAT_LABEL[block.strategy] ?? block.strategy}
                </span>
              </td>
              <td className="px-3 py-2">
                <ConfBadge value={block.self_confidence} />
              </td>
              <td className="px-3 py-2">
                <ConfBadge value={block.verified_confidence} />
              </td>
              <td className="px-3 py-2">
                <ReconIcon value={block.reconciliation_status} />
              </td>
              <td className="px-3 py-2">
                <span
                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                    CRIT_COLOR[block.criticality] ??
                    "text-muted-foreground bg-muted border border-border"
                  }`}
                >
                  {block.criticality}
                </span>
              </td>
              <td className="px-3 py-2">
                {block.human_review_required ? (
                  <CheckCircle2 size={14} className="text-red-600" />
                ) : (
                  <span className="text-muted-foreground text-xs">—</span>
                )}
              </td>
              {showBlastRadius && (
                <td className="px-3 py-2 text-xs tabular-nums text-muted-foreground">
                  {block.blast_radius ?? "—"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
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
  doc,
  nonTechnicalDoc,
  isDone,
  onDocChange,
  onSave,
  isSaving,
  restoreKey,
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
  doc?: string | null;
  nonTechnicalDoc?: string | null;
  isDone?: boolean;
  onDocChange?: (doc: string) => void;
  onSave?: () => void;
  isSaving?: boolean;
  restoreKey?: number;
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
  const [reportCollapsed, setReportCollapsed] = useState(() => doc == null);
  const [byFileCollapsed, setByFileCollapsed] = useState(true);
  const [historyCollapsed, setHistoryCollapsed] = useState(true);
  const [attentionView, setAttentionView] = useState<"cards" | "table">("cards");
  const [attentionCollapsed, setAttentionCollapsed] = useState(false);
  const [activeStatFilter, setActiveStatFilter] =
    useState<StatFilterKey | null>(null);
  const blocksRef = useRef<HTMLDivElement>(null);
  const [isRefiningAll, setIsRefiningAll] = useState(false);

  const blockPlanMap: Record<string, BlockPlan> = planData
    ? Object.fromEntries(planData.block_plans.map(bp => [bp.block_id, bp]))
    : {};

  const handleRefineAllFailed = async () => {
    if (!trustReport || isRefiningAll) return;
    const failedBlocks = trustReport.blocks.filter(
      b => b.reconciliation_status === "fail"
    );
    if (failedBlocks.length === 0) return;
    setIsRefiningAll(true);
    try {
      for (const block of failedBlocks) {
        await refineBlock(jobId, block.block_id, { notes: null, hint: null });
      }
      onBlockRefineSuccess?.();
    } finally {
      setIsRefiningAll(false);
    }
  };

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

  const allInputs = new Set(planData.block_plans.flatMap(b => b.input_datasets));
  const allOutputs = new Set(planData.block_plans.flatMap(b => b.output_datasets));
  const externalInputs = [...allInputs].filter(d => !allOutputs.has(d)).sort();
  const finalOutputs = [...allOutputs].filter(d => !allInputs.has(d)).sort();

  function truncateList(items: string[], max = 4): string {
    if (items.length <= max) return items.join(", ");
    return `${items.slice(0, max).join(", ")} +${items.length - max} more`;
  }

  return (
    <TooltipProvider>
      <div className="h-full min-h-0 overflow-y-auto space-y-4 pb-6">
        {/* Pipeline description — above verdict strip */}
        {planData.summary && (
          <p className="text-sm text-foreground leading-relaxed">
            {planData.summary}
          </p>
        )}

        {/* Reads / Produces row */}
        {(externalInputs.length > 0 || finalOutputs.length > 0) && (
          <p className="text-xs text-muted-foreground">
            {externalInputs.length > 0 && (
              <span><span className="font-medium text-foreground">Reads:</span> {truncateList(externalInputs)}</span>
            )}
            {externalInputs.length > 0 && finalOutputs.length > 0 && (
              <span className="mx-2">·</span>
            )}
            {finalOutputs.length > 0 && (
              <span><span className="font-medium text-foreground">Produces:</span> {truncateList(finalOutputs)}</span>
            )}
          </p>
        )}

        {/* Missing dependencies callout */}
        {planData.missing_dependencies && planData.missing_dependencies.length > 0 && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 space-y-1.5">
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} className="text-amber-600 shrink-0" />
              <p className="text-sm font-medium text-amber-800">
                {planData.missing_dependencies.length} missing dependenc{planData.missing_dependencies.length === 1 ? "y" : "ies"} detected
              </p>
            </div>
            <ul className="text-xs text-amber-700 space-y-0.5 pl-5 list-disc">
              {planData.missing_dependencies.slice(0, 3).map(dep => (
                <li key={`${dep.type}:${dep.name}`}>
                  <span className="font-mono">{dep.name}</span>
                  {" "}
                  <span className="text-amber-600">
                    ({dep.type}, {dep.reference_count} {dep.reference_count === 1 ? "ref" : "refs"})
                  </span>
                </li>
              ))}
              {planData.missing_dependencies.length > 3 && (
                <li className="list-none text-amber-600">
                  +{planData.missing_dependencies.length - 3} more
                </li>
              )}
            </ul>
            <p className="text-xs text-amber-600">Re-upload with these files included to improve translation quality.</p>
          </div>
        )}

        {/* Sensitive data warning banner */}
        {(() => {
          const piiSignals = planData.sensitive_data_findings
            ? [...new Set(planData.sensitive_data_findings.map(f => f.matched_signal))].sort()
            : [];
          const piiColumnCount = planData.sensitive_data_findings?.length ?? 0;
          return piiSignals.length > 0 && (
            <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 flex items-start gap-3">
              <AlertTriangle size={14} className="text-red-600 shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                <p className="text-sm font-medium text-red-800">
                  Sensitive data detected ({piiColumnCount} column{piiColumnCount !== 1 ? "s" : ""})
                </p>
                <p className="text-xs text-red-700">
                  Signals matched: {piiSignals.join(", ")}. Ensure data handling complies with applicable
                  regulations before accepting.
                </p>
              </div>
            </div>
          );
        })()}

        {/* Metrics card — confidence/risk/stat cards only */}
        <Card className="border-border bg-muted/30">
          <CardContent className="p-0">
            {/* Stats centered */}
            <div className="flex items-center justify-center gap-4 px-5 py-2 flex-wrap">
              {/* Confidence bar */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground shrink-0">
                  LLM confidence
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
                <Dialog>
                  <DialogTrigger asChild>
                    <button
                      type="button"
                      className="text-muted-foreground hover:text-foreground transition-colors ml-1"
                      aria-label="What does confidence mean?"
                    >
                      <Info size={14} />
                    </button>
                  </DialogTrigger>
                  <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
                    <DialogHeader>
                      <DialogTitle>Confidence &amp; criticality</DialogTitle>
                    </DialogHeader>
                    <pre className="text-sm text-foreground whitespace-pre-wrap font-sans leading-relaxed">
                      {CONFIDENCE_HELP}
                    </pre>
                  </DialogContent>
                </Dialog>
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

        {/* Verdict strip */}
        {trustReport && (() => {
          const verdict = getVerdict(trustReport);
          const style = VERDICT_STYLES[verdict];
          const { Icon } = style;
          const attentionCount = trustReport.needs_review + trustReport.failed_reconciliation;
          const manualCount = trustReport.manual_todo;
          const consequence =
            verdict === "green"
              ? "All blocks verified — safe to accept."
              : verdict === "amber"
              ? `${attentionCount} block${attentionCount !== 1 ? "s" : ""} need review before accepting.`
              : `${manualCount} block${manualCount !== 1 ? "s" : ""} cannot be auto-converted — manual implementation required before this pipeline will run.`;
          const headline =
            verdict === "green"
              ? "Ready to accept"
              : verdict === "amber"
              ? "Review recommended"
              : "Not ready to accept";
          return (
            <div className={`rounded-lg border ${style.border} px-4 py-3 flex items-start gap-3`}>
              <Icon size={18} className={`${style.iconColor} shrink-0 mt-0.5`} />
              <div>
                <p className={`text-sm font-semibold ${style.headlineColor}`}>{headline}</p>
                <p className={`text-sm ${style.textColor}`}>{consequence}</p>
              </div>
            </div>
          );
        })()}

        {/* Lineage unavailable notice */}
        {trustReport && !trustReport.lineage_available && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            Blast radius unavailable — lineage enrichment did not run for this job.
          </div>
        )}

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

        {/* Report panel */}
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setReportCollapsed((v) => !v)}
            className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
          >
            {reportCollapsed
              ? <ChevronRight size={14} className="text-muted-foreground shrink-0" />
              : <ChevronDown size={14} className="text-muted-foreground shrink-0" />}
            <h2 className="text-sm font-semibold text-foreground">Report</h2>
          </button>
          {!reportCollapsed && (
            isDone ? (
              <ReportTab
                isDone={isDone ?? false}
                doc={doc ?? null}
                nonTechnicalDoc={nonTechnicalDoc ?? null}
                onDocChange={onDocChange}
                onSave={onSave}
                isSaving={isSaving ?? false}
                restoreKey={restoreKey ?? 0}
              />
            ) : (
              <p className="text-sm text-muted-foreground px-1">No documentation generated yet.</p>
            )
          )}
        </div>

        {trustReport?.files && trustReport.files.length > 0 && (
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setByFileCollapsed((v) => !v)}
              className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
            >
              {byFileCollapsed ? (
                <ChevronRight size={14} className="text-muted-foreground shrink-0" />
              ) : (
                <ChevronDown size={14} className="text-muted-foreground shrink-0" />
              )}
              <h2 className="text-sm font-semibold text-foreground">By file</h2>
              <Badge variant="secondary" className="text-xs font-mono">
                {trustReport.files.length}
              </Badge>
            </button>
            {!byFileCollapsed && (
              <div className="space-y-2">
                {trustReport.files.map((file) => (
                  <FileSection key={file.source_file} file={file} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Migration history section */}
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setHistoryCollapsed(v => !v)}
            className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
          >
            {historyCollapsed
              ? <ChevronRight size={14} className="text-muted-foreground shrink-0" />
              : <ChevronDown size={14} className="text-muted-foreground shrink-0" />}
            <h2 className="text-sm font-semibold text-foreground">Migration history</h2>
          </button>
          {!historyCollapsed && (
            <ChangelogFeed jobId={jobId} />
          )}
        </div>

        {/* Needs attention section */}
        {trustReport && (
          <div className="space-y-2">
            {/* Header row */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setAttentionCollapsed(v => !v)}
                className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
              >
                {attentionCollapsed ? (
                  <ChevronRight size={14} className="text-muted-foreground shrink-0" />
                ) : (
                  <ChevronDown size={14} className="text-muted-foreground shrink-0" />
                )}
                <h2 className="text-sm font-semibold text-foreground">Needs attention</h2>
                {trustReport.review_queue.length > 0 && (
                  <Badge variant="secondary" className="text-xs font-mono">
                    {trustReport.review_queue.length}
                  </Badge>
                )}
              </button>
              {/* Cards/Table toggle — only when there are items */}
              {!attentionCollapsed && trustReport.review_queue.length > 0 && (
                <div className="flex rounded-md border border-border overflow-hidden text-xs ml-1">
                  <button
                    type="button"
                    onClick={() => setAttentionView("cards")}
                    className={`px-2 py-1 transition-colors ${
                      attentionView === "cards"
                        ? "bg-foreground text-background"
                        : "bg-background text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    Cards
                  </button>
                  <button
                    type="button"
                    onClick={() => setAttentionView("table")}
                    className={`px-2 py-1 transition-colors ${
                      attentionView === "table"
                        ? "bg-foreground text-background"
                        : "bg-background text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    Table
                  </button>
                </div>
              )}
              {/* Re-translate button (moved from Review queue header) */}
              {trustReport.failed_reconciliation > 0 && jobStatus !== "accepted" && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleRefineAllFailed}
                  disabled={isRefiningAll}
                  className="ml-auto text-xs h-7"
                >
                  {isRefiningAll ? (
                    <><Loader2 size={14} className="animate-spin mr-1" />Re-translating…</>
                  ) : (
                    "Re-translate failed blocks"
                  )}
                </Button>
              )}
            </div>

            {/* Body */}
            {!attentionCollapsed && (
              trustReport.review_queue.length === 0 ? (
                <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3">
                  <CheckCircle2 size={16} className="text-green-600 shrink-0" />
                  <p className="text-sm text-green-700">
                    All {trustReport.total_blocks} blocks verified — nothing needs attention.
                  </p>
                </div>
              ) : attentionView === "cards" ? (
                <AttentionCards
                  queue={trustReport.review_queue}
                  blockPlanMap={blockPlanMap}
                  manualTodo={trustReport.manual_todo}
                  onShowAll={() => setAttentionView("table")}
                  onViewBlocks={() => {
                    setBlocksCollapsed(false);
                    blocksRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                />
              ) : (
                <AttentionTable
                  queue={trustReport.review_queue}
                  lineageAvailable={trustReport.lineage_available}
                />
              )
            )}
          </div>
        )}


      </div>
    </TooltipProvider>
  );
}
