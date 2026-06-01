import { getJobTrustReport } from "@/api/jobs";
import type { TrustReportBlock, TrustReportFile } from "@/api/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Info, XCircle } from "lucide-react";
import { useState } from "react";

interface EvaluationTabProps {
  jobId: string;
  jobStatus: string;
}

// ── Confidence metric help content ────────────────────────────────────────────

const CONFIDENCE_HELP = `What the confidence score tells you:

• High (≥ 85%) — The translation agent was confident and, where a reference output was available, the Python output matched the SAS output exactly. Safe to treat as verified.

• Medium (65–84%) — The translation is likely correct but has not been fully verified, or the agent had some uncertainty. Worth a quick review.

• Low (40–64%) — The agent flagged uncertainty, or the output did not match the reference. Requires human review before the block can be trusted.

• Very Low (< 40%) — The agent had very low confidence, or the block failed reconciliation and was already low confidence. Likely needs manual rewrite.

What it does not guarantee:

A High confidence score does not mean the output is semantically correct in all edge cases — it means the automated checks passed and the LLM was confident. A human reviewer should still check any block that is business-critical.

Confidence is computed per block (DATA step, PROC, etc.), not per column or per row.

If no reference CSV was uploaded, there is no reconciliation to validate against — the score reflects LLM self-assessment only.`;

// ── Helpers ───────────────────────────────────────────────────────────────────

const CRITICALITY_CLASSES: Record<string, string> = {
  critical: "text-red-700 bg-red-50 border border-red-200",
  high: "text-orange-700 bg-orange-50 border border-orange-200",
  normal: "text-amber-700 bg-amber-50 border border-amber-200",
  low: "text-green-700 bg-green-50 border border-green-200",
};

function CriticalityBadge({ value }: { value: string }): React.ReactElement {
  const cls = CRITICALITY_CLASSES[value] ?? "text-muted-foreground bg-muted border border-border";
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${cls}`}>
      {value}
    </span>
  );
}

function ConfidenceBadge({ value }: { value: string | null }): React.ReactElement {
  if (!value) return <span className="text-muted-foreground">—</span>;
  const classes: Record<string, string> = {
    high: "text-green-700 bg-green-50 border border-green-200",
    medium: "text-amber-700 bg-amber-50 border border-amber-200",
    low: "text-red-700 bg-red-50 border border-red-200",
  };
  const cls = classes[value] ?? "text-muted-foreground bg-muted border border-border";
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${cls}`}>
      {value}
    </span>
  );
}

function ReconciliationBadge({ value }: { value: "pass" | "fail" | null }): React.ReactElement {
  if (!value) return <span className="text-muted-foreground">—</span>;
  if (value === "pass") {
    return <CheckCircle2 size={14} className="text-green-600" aria-label="pass" />;
  }
  return <XCircle size={14} className="text-red-600" aria-label="fail" />;
}

const STRATEGY_COLOR = {
  translated: "bg-green-100 text-green-800",
  translated_with_review: "bg-amber-100 text-amber-800",
  manual: "bg-red-100 text-red-800",
} as const;

const STRATEGY_LABELS = {
  translated: "Translated",
  translated_with_review: "Review needed",
  manual: "Manual",
} as const;

function StrategyBadge({ value }: { value: string }): React.ReactElement {
  const colorClass =
    STRATEGY_COLOR[value as keyof typeof STRATEGY_COLOR] ?? "bg-muted text-muted-foreground";
  const label = STRATEGY_LABELS[value as keyof typeof STRATEGY_LABELS] ?? value;
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${colorClass}`}>
      {label}
    </span>
  );
}

function SummaryCard({
  label,
  count,
  badgeClass,
}: {
  label: string;
  count: number;
  badgeClass: string;
}): React.ReactElement {
  return (
    <div className="flex-1 rounded-lg border border-border bg-card p-4 flex flex-col gap-2 min-w-0">
      <span className="text-xs text-muted-foreground font-medium truncate">{label}</span>
      <span className={`text-2xl font-bold ${badgeClass}`}>{count}</span>
    </div>
  );
}

function FileSection({ file }: { file: TrustReportFile }): React.ReactElement {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 text-left text-sm font-medium hover:bg-muted/40 transition-colors cursor-pointer"
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

const CRITICALITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  normal: 2,
  low: 3,
};

function ReviewQueueRow({
  block,
  lineageAvailable,
}: {
  block: TrustReportBlock;
  lineageAvailable: boolean;
}): React.ReactElement {
  return (
    <tr className="border-t border-border text-sm">
      <td className="px-3 py-2 font-mono text-xs text-muted-foreground max-w-[160px] truncate">
        {block.block_id}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground max-w-[120px] truncate">
        {block.source_file}
      </td>
      <td className="px-3 py-2">
        <StrategyBadge value={block.strategy} />
      </td>
      <td className="px-3 py-2">
        <ConfidenceBadge value={block.self_confidence} />
      </td>
      <td className="px-3 py-2">
        <ConfidenceBadge value={block.verified_confidence} />
      </td>
      <td className="px-3 py-2">
        <ReconciliationBadge value={block.reconciliation_status} />
      </td>
      <td className="px-3 py-2">
        <CriticalityBadge value={block.criticality} />
      </td>
      <td className="px-3 py-2 text-center">
        {block.human_review_required ? (
          <CheckCircle2 size={14} className="text-red-600 mx-auto" aria-label="required" />
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      {lineageAvailable && (
        <td className="px-3 py-2 text-xs text-muted-foreground">
          {block.blast_radius !== null ? block.blast_radius : "—"}
        </td>
      )}
    </tr>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const ENABLED_STATUSES = new Set(["proposed", "accepted", "done"]);

export default function EvaluationTab({
  jobId,
  jobStatus,
}: EvaluationTabProps): React.ReactElement {
  const enabled = ENABLED_STATUSES.has(jobStatus);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["job", jobId, "trust-report"],
    queryFn: () => getJobTrustReport(jobId),
    enabled: !!jobId && enabled,
  });

  if (!enabled) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Evaluation is available once the migration is proposed.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading evaluation…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Could not load evaluation data.
      </div>
    );
  }

  const overallColors: Record<string, string> = {
    high: "text-green-700 bg-green-50 border border-green-200",
    medium: "text-amber-700 bg-amber-50 border border-amber-200",
    low: "text-red-700 bg-red-50 border border-red-200",
    unknown: "text-muted-foreground bg-muted border border-border",
  };
  const overallClass = overallColors[data.overall_confidence] ?? overallColors.unknown;

  const topRisky = [...data.review_queue]
    .sort((a, b) => {
      const cDiff =
        (CRITICALITY_ORDER[a.criticality] ?? 99) - (CRITICALITY_ORDER[b.criticality] ?? 99);
      if (cDiff !== 0) return cDiff;
      const aConf = typeof a.blast_radius === "number" ? a.blast_radius : -1;
      const bConf = typeof b.blast_radius === "number" ? b.blast_radius : -1;
      return bConf - aConf;
    })
    .slice(0, 10);

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto px-4 py-6 space-y-8">
        {/* Summary cards */}
        <div className="flex gap-3 flex-wrap">
          <SummaryCard
            label="Auto-verified"
            count={data.auto_verified}
            badgeClass="text-green-700"
          />
          <SummaryCard
            label="Needs review"
            count={data.needs_review}
            badgeClass="text-amber-700"
          />
          <SummaryCard
            label="Manual TODO"
            count={data.manual_todo}
            badgeClass="text-muted-foreground"
          />
          <SummaryCard
            label="Failed reconciliation"
            count={data.failed_reconciliation}
            badgeClass="text-red-700"
          />
        </div>

        {/* Overall confidence + help */}
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground font-medium">Overall confidence</span>
          <span
            className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${overallClass}`}
          >
            {data.overall_confidence}
          </span>
          <span className="text-xs text-muted-foreground">
            {data.auto_verified} / {data.total_blocks} blocks auto-verified
          </span>
          <Dialog>
            <DialogTrigger asChild>
              <button
                type="button"
                className="ml-1 text-muted-foreground hover:text-foreground transition-colors"
                aria-label="What does confidence mean?"
              >
                <Info size={15} />
              </button>
            </DialogTrigger>
            <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Confidence metric</DialogTitle>
              </DialogHeader>
              <pre className="text-sm text-foreground whitespace-pre-wrap font-sans leading-relaxed">
                {CONFIDENCE_HELP}
              </pre>
            </DialogContent>
          </Dialog>
        </div>

        {/* Lineage notice */}
        {!data.lineage_available && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            Blast radius unavailable — lineage enrichment did not run for this job.
          </div>
        )}

        {/* Top risky blocks */}
        <section>
          <h2 className="text-sm font-semibold text-foreground mb-3">
            Top Risky Blocks
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              (sorted by criticality, max 10)
            </span>
          </h2>
          {topRisky.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              All blocks verified — nothing needs attention
            </p>
          ) : (
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
                    {data.lineage_available && (
                      <th className="px-3 py-2 text-left font-medium">Blast radius</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {topRisky.map((block) => (
                    <ReviewQueueRow
                      key={block.block_id}
                      block={block}
                      lineageAvailable={data.lineage_available}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Per-file breakdown */}
        {data.files.length > 0 && (
          <section>
            <h2 className="text-sm font-semibold text-foreground mb-3">Per-file Breakdown</h2>
            <div className="space-y-2">
              {data.files.map((file) => (
                <FileSection key={file.source_file} file={file} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
