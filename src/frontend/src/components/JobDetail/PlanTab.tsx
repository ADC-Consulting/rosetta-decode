import { getJobPlan, getJobRunbook, getJobTrustReport, refineBlock } from "@/api/jobs";
import type {
  BlockOverride,
  BlockPlan,
  JobPlanResponse,
  JobStatusValue,
  RunbookEntry,
  RunbookResponse,
  TrustReportBlock,
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
import { Skeleton } from "@/components/ui/skeleton";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
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
import BeforeYouAcceptPanel from "./BeforeYouAcceptPanel";
import BlockPlanTable from "./BlockPlanTable";
import StatusChip from "./StatusChip";
import {
  CONFIDENCE_PCT,
  CONFIDENCE_TONE,
  CRITICALITY_TONE,
  RISK_LABEL,
  RISK_PCT,
  RISK_TONE,
  STRATEGY_LABEL,
  STRATEGY_TONE,
  TONE_HEX,
  type ConfidenceBand,
  type Criticality,
  type RiskLevel,
  type Strategy,
  type Tone,
} from "./status-colors";

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
// Criticality order (module-level, shared by AttentionTable and the
// criticality breakdown row in the metrics card). Color/tone comes from
// CRITICALITY_TONE in ./status-colors.ts.
// ---------------------------------------------------------------------------

const CRIT_ORDER: string[] = ["critical", "high", "medium", "low", "unknown"];

function criticalityTone(criticality: string): Tone {
  return CRITICALITY_TONE[criticality as Criticality] ?? "neutral";
}

// ---------------------------------------------------------------------------
// Confidence help content
// ---------------------------------------------------------------------------

const CONFIDENCE_HELP = `What the confidence score tells you:

• High (≥ 85%) — The translation agent was confident and, where a reference output was available, the Python output matched the SAS output exactly. Safe to treat as verified.

• Medium (65–84%) — The translation is likely correct but has not been fully verified, or the agent had some uncertainty. Worth a quick review.

• Low (40–64%) — The agent flagged uncertainty, or the output did not match the reference. Requires human review before the step can be trusted.

• Very Low (< 40%) — The agent had very low confidence, or the step failed reconciliation and was already low confidence. Likely needs manual rewrite.

What it does not guarantee:

A High confidence score does not mean the output is semantically correct in all edge cases — it means the automated checks passed and the LLM was confident. A human reviewer should still check any step that is business-critical.

Confidence is computed per step (DATA step, PROC, etc.), not per column or per row.

If no reference CSV was uploaded, there is no reconciliation to validate against — the score reflects LLM self-assessment only.

What criticality means:

Criticality is a post-translation signal that combines strategy, confidence, reconciliation outcome, and blast radius (how many downstream files depend on this step). It differs from Risk, which is a static pre-translation assessment of SAS construct complexity.

• Critical — Strategy is manual, or confidence was very low. Step needs human authoring or rewrite.
• High — Confidence was low, reconciliation failed, or this step feeds 3+ downstream files.
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
  const isZero = count === 0;
  const resolvedColorClasses = isZero
    ? "text-muted-foreground bg-muted/30 border-muted"
    : colorClasses;
  return (
    <button
      type="button"
      aria-pressed={isActive}
      onClick={() => !isZero && onFilterChange(isActive ? null : filterKey)}
      disabled={isZero}
      className={[
        "relative flex flex-col items-center justify-center gap-0.5 rounded-lg border p-3 min-w-[80px]",
        "select-none transition-all",
        resolvedColorClasses,
        isZero
          ? "cursor-default opacity-60"
          : isActive
            ? "cursor-pointer ring-2 ring-offset-1 ring-current shadow-sm"
            : "cursor-pointer hover:shadow-md hover:ring-1 hover:ring-border",
      ].join(" ")}
    >
      <span className="text-2xl font-bold tabular-nums leading-none">
        {total !== undefined && total > 0 ? `${count} / ${total}` : count}
      </span>
      <span className={`text-xs font-medium mt-0.5 leading-tight text-center ${isZero ? "text-muted-foreground" : ""}`}>
        {label}
      </span>
      {!isZero && (
        <ChevronDown
          size={12}
          className="absolute bottom-1.5 right-1.5 text-muted-foreground"
          aria-hidden
        />
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// InlineRunbook — collapsible "How to fix →" toggle embedded in an attention card
// ---------------------------------------------------------------------------

function InlineRunbook({ entry }: { entry: RunbookEntry }): React.ReactElement {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-border pt-2 mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs text-[var(--primary)] hover:underline cursor-pointer"
        aria-expanded={open}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        How to fix →
      </button>
      {open && (
        <div className="mt-2 space-y-2 pl-1">
          {entry.why_risky.length > 0 && (
            <div className="space-y-0.5">
              <p className="text-[11px] font-semibold text-foreground uppercase tracking-wide">
                Why it&apos;s risky
              </p>
              <ul className="list-disc list-inside space-y-0.5">
                {entry.why_risky.map((reason, i) => (
                  <li key={i} className="text-xs text-muted-foreground leading-relaxed">
                    {reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {entry.remediation_outline.length > 0 && (
            <div className="space-y-0.5">
              <p className="text-[11px] font-semibold text-foreground uppercase tracking-wide">
                Suggested remediation
              </p>
              <ol className="list-decimal list-inside space-y-0.5">
                {entry.remediation_outline.map((step, i) => (
                  <li key={i} className="text-xs text-muted-foreground leading-relaxed">
                    {step}
                  </li>
                ))}
              </ol>
            </div>
          )}
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
  runbookMap,
  manualTodo,
  onShowAll,
  onViewBlocks,
  onViewEtlTab,
  isAccepted,
}: {
  queue: TrustReportBlock[];
  blockPlanMap: Record<string, BlockPlan>;
  runbookMap: Record<string, RunbookEntry>;
  manualTodo: number;
  onShowAll: () => void;
  onViewBlocks: () => void;
  onViewEtlTab?: () => void;
  isAccepted: boolean;
}): React.ReactElement {
  const critOrderMap: Record<string, number> = Object.fromEntries(
    CRIT_ORDER.map((k, i) => [k, i])
  );
  const top5 = [...queue]
    .sort((a, b) => {
      if (a.strategy === "manual" && b.strategy !== "manual") return -1;
      if (b.strategy === "manual" && a.strategy !== "manual") return 1;
      return (critOrderMap[a.criticality] ?? 99) - (critOrderMap[b.criticality] ?? 99);
    })
    .slice(0, 5);
  const remaining = queue.length - top5.length;

  const strategyLabel = (strategy: string, reconciliation: string | null): string => {
    if (strategy === "manual") return "Manual — cannot auto-convert";
    if (reconciliation === "fail") return "Reconciliation failed";
    return "Needs review";
  };

  const strategyTone = (strategy: string, reconciliation: string | null): Tone => {
    if (strategy === "manual") return "danger";
    if (reconciliation === "fail") return "caution";
    return "warning";
  };

  const getRationale = (block: TrustReportBlock): string => {
    const bp = blockPlanMap[block.block_id];
    if (bp?.rationale) return bp.rationale;
    if (block.strategy === "manual") return `A ${block.block_type} step that requires manual implementation.`;
    if (block.reconciliation_status === "fail") return `A ${block.block_type} step that failed reconciliation.`;
    return `A ${block.block_type} step that needs review.`;
  };

  return (
    <div className="space-y-2">
      {manualTodo > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
          <AlertTriangle size={14} className="text-amber-600 shrink-0 mt-0.5" />
          <div className="flex flex-1 items-center justify-between gap-2 flex-wrap">
            <p className="text-xs text-amber-700">
              Manual steps require code edits in the ETL tab before this pipeline will run.
            </p>
            {onViewEtlTab && (
              <button
                type="button"
                onClick={onViewEtlTab}
                className="text-xs underline font-medium text-amber-700 hover:text-amber-900 shrink-0"
              >
                Go to ETL tab →
              </button>
            )}
          </div>
        </div>
      )}
      {top5.map(block => {
        const runbookEntry = runbookMap[block.block_id];
        return (
          <Card key={block.block_id} className="rounded-lg border border-border bg-card gap-0 py-0 ring-0">
            <CardContent className="px-4 py-3 space-y-1.5">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-mono text-xs text-foreground truncate">{block.block_id}</p>
                  <p className="font-mono text-xs text-muted-foreground truncate">{block.source_file}</p>
                </div>
                <StatusChip
                  tone={strategyTone(block.strategy, block.reconciliation_status)}
                  className="shrink-0"
                >
                  {strategyLabel(block.strategy, block.reconciliation_status)}
                </StatusChip>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">{getRationale(block)}</p>
              {isAccepted ? (
                onViewEtlTab && (
                  <button
                    type="button"
                    onClick={onViewEtlTab}
                    className="text-xs text-[var(--primary)] hover:underline"
                  >
                    View in ETL tab →
                  </button>
                )
              ) : (
                <button
                  type="button"
                  onClick={onViewBlocks}
                  className="text-xs text-[var(--primary)] hover:underline"
                >
                  View in steps table →
                </button>
              )}
              {runbookEntry && (
                <InlineRunbook entry={runbookEntry} />
              )}
            </CardContent>
          </Card>
        );
      })}
      {remaining > 0 && (
        <button type="button" onClick={onShowAll} className="text-xs text-[var(--primary)] hover:underline px-1">
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
  const critOrderMap: Record<string, number> = Object.fromEntries(
    CRIT_ORDER.map((k, i) => [k, i])
  );

  function ConfBadge({ value }: { value: string | null }): React.ReactElement {
    if (!value) return <span className="text-muted-foreground text-xs">—</span>;
    const tone = CONFIDENCE_TONE[value as ConfidenceBand] ?? "neutral";
    return <StatusChip tone={tone}>{value}</StatusChip>;
  }

  function ReconIcon({ value }: { value: "pass" | "fail" | null }): React.ReactElement {
    if (!value) return <span className="text-muted-foreground text-xs">—</span>;
    if (value === "pass") return <CheckCircle2 size={14} className="text-green-600" />;
    return <XCircle size={14} className="text-red-600" />;
  }

  const showBlastRadius = lineageAvailable === true;

  const sorted = [...queue].sort((a, b) => {
    const cDiff =
      (critOrderMap[a.criticality] ?? 99) - (critOrderMap[b.criticality] ?? 99);
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
            <th className="px-3 py-2 text-left font-medium">Step ID</th>
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
                <StatusChip tone={STRATEGY_TONE[block.strategy as Strategy] ?? "neutral"}>
                  {STRATEGY_LABEL[block.strategy as Strategy] ?? block.strategy}
                </StatusChip>
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
                <StatusChip tone={criticalityTone(block.criticality)}>
                  {block.criticality}
                </StatusChip>
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
  isAccepted = false,
  acceptedAt = null,
  onSwitchToEtlTab,
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
  isAccepted?: boolean;
  acceptedAt?: string | null;
  onSwitchToEtlTab?: () => void;
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

  // Runbook data — fetched eagerly (not behind a collapsed toggle) so we can
  // embed inline "How to fix" toggles in the attention cards.
  const { data: runbookData } = useQuery<RunbookResponse>({
    queryKey: ["job", jobId, "runbook"],
    queryFn: () => getJobRunbook(jobId),
    enabled: trustReportEnabled,
  });

  const runbookMap: Record<string, RunbookEntry> = runbookData
    ? Object.fromEntries(runbookData.entries.map(e => [e.block_id, e]))
    : {};

  const trustBlocks: Record<string, TrustReportBlock> = trustReport
    ? Object.fromEntries(trustReport.blocks.map((b) => [b.block_id, b]))
    : {};

  const isProposed = jobStatus === "proposed";
  const [showFullDesc, setShowFullDesc] = useState(false);
  const [blocksCollapsed, setBlocksCollapsed] = useState(true);
  const [attentionView, setAttentionView] = useState<"cards" | "table">("cards");
  const [attentionCollapsed, setAttentionCollapsed] = useState(false);
  const [activeStatFilter, setActiveStatFilter] =
    useState<StatFilterKey | null>(null);
  const blocksRef = useRef<HTMLDivElement>(null);
  const attentionRef = useRef<HTMLDivElement>(null);
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

  const overallConfidence: ConfidenceBand = trustReport?.overall_confidence ?? "unknown";
  // Bar-fill color needs a computed inline style (the <Progress> fill is driven by a CSS
  // variable), so this is the one place that reads the hex bridge instead of a Tailwind class —
  // see the TONE_HEX comment in status-colors.ts.
  const confidenceColor = TONE_HEX[CONFIDENCE_TONE[overallConfidence]];
  const confidencePct = trustReport
    ? Math.round(
        (trustReport.overall_confidence_score ??
          CONFIDENCE_PCT[overallConfidence] / 100) * 100,
      )
    : CONFIDENCE_PCT[overallConfidence];

  const riskLevel = planData.overall_risk as RiskLevel;
  const riskBar = {
    color: TONE_HEX[RISK_TONE[riskLevel]] ?? TONE_HEX.neutral,
    label: RISK_LABEL[riskLevel] ?? planData.overall_risk,
  };

  const stripLibref = (d: string): string => {
    if (!d.includes(".") || /\.(csv|xlsx|xpt|sas7bdat|parquet|json|txt)$/i.test(d)) return d;
    return d.substring(d.indexOf(".") + 1);
  };
  const allInputs = new Set(planData.block_plans.flatMap(b => b.input_datasets));
  const allOutputs = new Set(planData.block_plans.flatMap(b => b.output_datasets));
  const externalInputs = [...allInputs].filter(d => !allOutputs.has(d)).sort().map(stripLibref);
  const finalOutputs = [...allOutputs].filter(d => !allInputs.has(d)).sort().map(stripLibref);

  // Step type breakdown for the composition line (point 4)
  const compositionCounts = planData.block_plans.reduce(
    (acc, bp) => {
      const t = bp.block_type?.toLowerCase() ?? "";
      if (t === "data" || t === "data_step") acc.data += 1;
      else if (t.startsWith("proc") || t === "generic_proc") acc.proc += 1;
      else if (t === "macro") acc.macro += 1;
      else if (bp.strategy === "manual") acc.manual += 1;
      return acc;
    },
    { data: 0, proc: 0, macro: 0, manual: 0 },
  );

  const compositionParts: string[] = [];
  if (compositionCounts.data > 0) compositionParts.push(`${compositionCounts.data} DATA`);
  if (compositionCounts.proc > 0) compositionParts.push(`${compositionCounts.proc} PROC`);
  if (compositionCounts.macro > 0) compositionParts.push(`${compositionCounts.macro} Macros`);
  if (compositionCounts.manual > 0) compositionParts.push(`${compositionCounts.manual} Manual`);

  // Attention queue — only render when non-empty (point 5)
  const attentionQueueLength = trustReport?.review_queue.length ?? 0;

  // Helper: expand steps and scroll to them
  const expandAndScrollToSteps = () => {
    setBlocksCollapsed(false);
    setTimeout(
      () =>
        blocksRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        }),
      50,
    );
  };

  // Helper: expand the Needs Attention section and scroll to it
  const expandAndScrollToAttention = () => {
    setAttentionCollapsed(false);
    setTimeout(
      () =>
        attentionRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        }),
      50,
    );
  };

  // Shared stat filter change handler
  const handleStatFilterChange = (key: StatFilterKey | null) => {
    setActiveStatFilter(key);
    if (key === "needs_review" || key === "manual_todo") {
      expandAndScrollToAttention();
    } else if (key !== null) {
      expandAndScrollToSteps();
    }
  };

  return (
    <TooltipProvider>
      {/*
        "Manifest" brand scope (F88) — locally overrides --primary/--radius/--font-sans/--font-mono
        for this subtree only (see .brand-manifest in index.css). Scoped here rather than globally
        per the 2026-08-26 decision to roll the new visual language out to the Plan tab +
        BlockPlanTable first, not the whole app.
      */}
      <div className="brand-manifest h-full min-h-0 overflow-y-auto space-y-4 pb-6 [scrollbar-gutter:stable]">
        {/* Pipeline description — above verdict strip */}
        {planData.summary && (
          <div>
            <p className={`text-sm text-foreground leading-relaxed ${!showFullDesc ? "line-clamp-3" : ""}`}>
              {planData.summary}
            </p>
            {planData.summary.length > 200 && (
              <button
                type="button"
                onClick={() => setShowFullDesc((v) => !v)}
                className="text-xs text-muted-foreground underline cursor-pointer mt-0.5"
              >
                {showFullDesc ? "Show less" : "Show more"}
              </button>
            )}
          </div>
        )}

        {/* Reads / Produces row */}
        {(externalInputs.length > 0 || finalOutputs.length > 0) && (
          <div className="flex flex-wrap items-center gap-y-1 gap-x-2">
            {externalInputs.length > 0 && (
              <div className="flex flex-wrap items-center gap-1">
                <span className="text-xs text-muted-foreground shrink-0">Reads:</span>
                {externalInputs.map((f) => (
                  <span
                    key={f}
                    className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-mono
                      bg-muted text-muted-foreground border border-border mr-1 mb-1"
                  >
                    {f}
                  </span>
                ))}
              </div>
            )}
            {finalOutputs.length > 0 && (
              <div className="flex flex-wrap items-center gap-1">
                <span className="text-xs text-muted-foreground shrink-0">Produces:</span>
                {finalOutputs.map((f) => (
                  <span
                    key={f}
                    className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-mono
                      bg-muted text-muted-foreground border border-border mr-1 mb-1"
                  >
                    {f}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Missing dependencies callout — non-accepted: shown before verdict strip as a blocking concern */}
        {!isAccepted && planData.missing_dependencies && planData.missing_dependencies.length > 0 && (
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

        {/* Verdict strip — accepted state overrides the green/amber/red states */}
        {isAccepted ? (
          <div className="rounded-lg border border-l-4 border-l-[var(--primary)] bg-[var(--primary)]/5 px-4 py-3 flex items-start gap-3">
            <CheckCircle2 size={18} className="text-[var(--primary)] shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-foreground">Delivered — Accepted</p>
              <p className="text-sm text-muted-foreground">
                {acceptedAt
                  ? `Accepted on ${new Date(acceptedAt).toLocaleDateString(undefined, {
                      month: "long",
                      day: "numeric",
                      year: "numeric",
                    })}.`
                  : "This migration has been accepted."}
                {" "}All editors are read-only.
              </p>
            </div>
          </div>
        ) : (
          trustReport && (() => {
            const verdict = getVerdict(trustReport);
            const style = VERDICT_STYLES[verdict];
            const { Icon } = style;
            const attentionCount = trustReport.needs_review + trustReport.failed_reconciliation;
            const manualCount = trustReport.manual_todo;
            const consequence =
              verdict === "green"
                ? "All steps verified — safe to accept."
                : verdict === "amber"
                ? `${attentionCount} step${attentionCount !== 1 ? "s" : ""} need review before accepting.`
                : `${manualCount} step${manualCount !== 1 ? "s" : ""} cannot be auto-converted — manual implementation required before this pipeline will run.`;
            const headline =
              verdict === "green"
                ? "Ready to accept"
                : verdict === "amber"
                ? "Review recommended"
                : "Not ready to accept";
            if (verdict === "amber") return null;
            return (
              <div className={`rounded-lg border ${style.border} px-4 py-3 flex items-start gap-3`}>
                <Icon size={18} className={`${style.iconColor} shrink-0 mt-0.5`} />
                <div>
                  <p className={`text-sm font-semibold ${style.headlineColor}`}>{headline}</p>
                  <p className={`text-sm ${style.textColor}`}>{consequence}</p>
                </div>
              </div>
            );
          })()
        )}

        {/* Missing dependencies callout — accepted: shown after verdict strip in past tense, no action text */}
        {isAccepted && planData.missing_dependencies && planData.missing_dependencies.length > 0 && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 space-y-1.5">
            <div className="flex items-center gap-2">
              <AlertTriangle size={14} className="text-amber-600 shrink-0" />
              <p className="text-sm font-medium text-amber-800">
                {planData.missing_dependencies.length} dependenc{planData.missing_dependencies.length === 1 ? "y was" : "ies were"} unavailable during translation
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
          </div>
        )}

        {/* Lineage unavailable notice */}
        {trustReport && !trustReport.lineage_available && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            Blast radius unavailable — lineage enrichment did not run for this job.
          </div>
        )}

        {/*
          Unified summary card (F88 / "Manifest" mockup structure) — a single Card containing, top
          to bottom: a 3px top-edge status bar (red when sensitive data is detected, brand teal
          otherwise), the PII/sensitive-data warning (when present), the confidence/risk bars, the
          4 stat tiles, the criticality row, and the "Before you accept" footer. Replaces the
          previously separate bordered PII banner + standalone metrics card. Data bindings below
          are unchanged from before this restructure — only the layout/markup changed.
        */}
        {(() => {
          const piiSignals = planData.sensitive_data_findings
            ? [...new Set(planData.sensitive_data_findings.map(f => f.matched_signal))].sort()
            : [];
          const piiColumnCount = planData.sensitive_data_findings?.length ?? 0;
          const hasPii = piiSignals.length > 0;

          return (
            <Card className="gap-0 py-0">
              <div
                className={cn("h-[3px] shrink-0", hasPii ? "bg-red-500" : "bg-[var(--primary)]")}
                aria-hidden="true"
              />

              {hasPii && (
                <div className="flex items-start gap-2.5 border-b border-border px-6 py-3.5">
                  <AlertTriangle size={15} className="text-red-600 shrink-0 mt-0.5" />
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    <span className="font-semibold text-red-600">
                      Sensitive data detected — {piiColumnCount} column{piiColumnCount !== 1 ? "s" : ""}.
                    </span>{" "}
                    Signals matched: <span className="font-mono">{piiSignals.join(", ")}</span>. Ensure
                    data handling complies with applicable regulations before accepting.
                  </p>
                </div>
              )}

              <CardContent className="px-6 py-5">
                {/* Confidence / risk bars */}
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 mb-6">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                        LLM confidence
                        <Dialog>
                          <DialogTrigger
                            className="text-muted-foreground hover:text-foreground transition-colors"
                            aria-label="What does confidence mean?"
                          >
                            <Info size={12} />
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
                      </span>
                      <span
                        className="text-[15px] font-bold tabular-nums"
                        style={{ color: confidenceColor }}
                      >
                        {confidencePct}%
                      </span>
                    </div>
                    <Progress
                      value={confidencePct}
                      className="h-1.5 **:data-[slot=progress-indicator]:bg-(--bar-fill)"
                      style={{ "--bar-fill": confidenceColor } as React.CSSProperties}
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                        Risk
                      </span>
                      <span className="text-[15px] font-bold capitalize" style={{ color: riskBar.color }}>
                        {riskBar.label}
                      </span>
                    </div>
                    <Progress
                      value={RISK_PCT[riskLevel] ?? 0}
                      className="h-1.5 **:data-[slot=progress-indicator]:bg-(--bar-fill)"
                      style={{ "--bar-fill": riskBar.color } as React.CSSProperties}
                    />
                  </div>
                </div>

                {/* Stat tiles + criticality + composition line */}
                {trustReport && (
                  <div className="space-y-2 mb-6">
                    <div className="grid grid-cols-4 gap-3.5">
                      <StatCard
                        filterKey="auto_verified"
                        count={trustReport.auto_verified}
                        total={trustReport.total_blocks}
                        label="Auto-verified"
                        colorClasses="text-green-700 bg-green-50 border-green-200"
                        activeFilter={activeStatFilter}
                        onFilterChange={handleStatFilterChange}
                      />
                      <StatCard
                        filterKey="needs_review"
                        count={trustReport.needs_review}
                        total={trustReport.total_blocks}
                        label="Needs review"
                        colorClasses="text-amber-700 bg-amber-50 border-amber-200"
                        activeFilter={activeStatFilter}
                        onFilterChange={handleStatFilterChange}
                      />
                      <StatCard
                        filterKey="manual_todo"
                        count={trustReport.manual_todo}
                        total={trustReport.total_blocks}
                        label="Manual TODO"
                        colorClasses="text-amber-700 bg-amber-50 border-amber-200"
                        activeFilter={activeStatFilter}
                        onFilterChange={handleStatFilterChange}
                      />
                      <StatCard
                        filterKey="failed_reconciliation"
                        count={trustReport.failed_reconciliation}
                        total={trustReport.total_blocks}
                        label="Failed reconciliation"
                        colorClasses="text-red-700 bg-red-50 border-red-200"
                        activeFilter={activeStatFilter}
                        onFilterChange={handleStatFilterChange}
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
                    {/* Criticality breakdown row */}
                    {(() => {
                      const critCounts: Record<string, number> = {};
                      for (const block of trustReport.blocks) {
                        const key = block.criticality ?? "unknown";
                        critCounts[key] = (critCounts[key] ?? 0) + 1;
                      }
                      const pills = CRIT_ORDER.filter(k => (critCounts[k] ?? 0) > 0);
                      if (pills.length === 0) return null;
                      return (
                        <div className="flex items-center gap-2 flex-wrap pt-1">
                          <span className="text-xs text-muted-foreground shrink-0">Criticality:</span>
                          {pills.map(k => (
                            <StatusChip key={k} tone={criticalityTone(k)}>
                              {k} {critCounts[k]}
                            </StatusChip>
                          ))}
                        </div>
                      );
                    })()}
                    {/* Step type composition line */}
                    {compositionParts.length > 0 && (
                      <p className="text-xs text-muted-foreground pt-0.5">
                        {compositionParts.join(" · ")}
                      </p>
                    )}
                  </div>
                )}

                {!isAccepted && trustReport && planData && (
                  <div className="border-t border-border pt-5">
                    <BeforeYouAcceptPanel
                      trustReport={trustReport}
                      planData={planData}
                      jobName="This migration"
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })()}

        {/* Needs attention section — only rendered when there are items (point 5) */}
        {trustReport && attentionQueueLength > 0 && (
          <div ref={attentionRef} className="space-y-2">
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
                <Badge variant="secondary" className="text-xs font-mono">
                  {attentionQueueLength}
                </Badge>
              </button>
              {/* Cards/Table toggle */}
              {!attentionCollapsed && (
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
              {/* Re-translate button */}
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
                    "Re-translate failed steps"
                  )}
                </Button>
              )}
            </div>

            {/* Body */}
            {!attentionCollapsed && (() => {
              const filteredAttentionQueue = (() => {
                const q = trustReport.review_queue;
                if (activeStatFilter === "manual_todo") return q.filter(b => b.strategy === "manual");
                if (activeStatFilter === "needs_review")
                  return q.filter(b => b.strategy !== "manual" && b.reconciliation_status !== "fail");
                if (activeStatFilter === "failed_reconciliation")
                  return q.filter(b => b.reconciliation_status === "fail");
                return q; // null or "auto_verified" — show all
              })();
              return attentionView === "cards" ? (
                <AttentionCards
                  queue={filteredAttentionQueue}
                  blockPlanMap={blockPlanMap}
                  runbookMap={runbookMap}
                  manualTodo={trustReport.manual_todo}
                  onShowAll={() => setAttentionView("table")}
                  onViewBlocks={() => {
                    setBlocksCollapsed(false);
                    blocksRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                  onViewEtlTab={onSwitchToEtlTab}
                  isAccepted={isAccepted}
                />
              ) : (
                <AttentionTable
                  queue={filteredAttentionQueue}
                  lineageAvailable={trustReport.lineage_available}
                />
              );
            })()}
          </div>
        )}

        {/* Steps section — default collapsed (point 7) */}
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
              <h2 className="text-sm font-semibold text-foreground">Steps</h2>
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
      </div>
    </TooltipProvider>
  );
}
