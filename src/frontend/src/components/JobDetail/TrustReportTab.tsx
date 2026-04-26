import { getJobTrustReport } from "@/api/jobs";
import type { TrustReportBlock, TrustReportFile } from "@/api/types";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

interface TrustReportTabProps {
  jobId: string;
  jobStatus: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

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
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium text-green-700 bg-green-50 border border-green-200">
        pass ✓
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium text-red-700 bg-red-50 border border-red-200">
      fail ✗
    </span>
  );
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
    STRATEGY_COLOR[value as keyof typeof STRATEGY_COLOR] ??
    "bg-muted text-muted-foreground";
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

function ReviewQueueRow({ block }: { block: TrustReportBlock }): React.ReactElement {
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
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {block.blast_radius !== null ? block.blast_radius : "—"}
      </td>
    </tr>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const ENABLED_STATUSES = new Set(["proposed", "accepted", "done"]);

export default function TrustReportTab({
  jobId,
  jobStatus,
}: TrustReportTabProps): React.ReactElement {
  const enabled = ENABLED_STATUSES.has(jobStatus);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["job", jobId, "trust-report"],
    queryFn: () => getJobTrustReport(jobId),
    enabled: !!jobId && enabled,
  });

  if (!enabled) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Trust report is available once the migration is proposed.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading trust report…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Could not load trust report.
      </div>
    );
  }

  const overallColors: Record<string, string> = {
    high: "text-green-700 bg-green-50 border border-green-200",
    medium: "text-amber-700 bg-amber-50 border border-amber-200",
    low: "text-red-700 bg-red-50 border border-red-200",
    unknown: "text-muted-foreground bg-muted border border-border",
  };
  const overallClass =
    overallColors[data.overall_confidence] ?? overallColors.unknown;

  const attentionBlocks = data.review_queue.filter((b) => b.needs_attention);

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

        {/* Overall confidence */}
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground font-medium">
            Overall confidence
          </span>
          <span
            className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${overallClass}`}
          >
            {data.overall_confidence}
          </span>
          <span className="text-xs text-muted-foreground">
            {data.auto_verified} / {data.total_blocks} blocks auto-verified
          </span>
        </div>

        {/* Lineage notice */}
        {!data.lineage_available && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            Blast radius unavailable — lineage enrichment did not run for this job.
          </div>
        )}

        {/* Review queue */}
        <section>
          <h2 className="text-sm font-semibold text-foreground mb-3">Needs Attention</h2>
          {attentionBlocks.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              All blocks verified — nothing needs attention ✓
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
                    <th className="px-3 py-2 text-left font-medium">Blast radius</th>
                  </tr>
                </thead>
                <tbody>
                  {attentionBlocks.map((block) => (
                    <ReviewQueueRow key={block.block_id} block={block} />
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
