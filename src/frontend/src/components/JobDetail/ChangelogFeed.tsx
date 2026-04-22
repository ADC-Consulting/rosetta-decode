import { getJobChangelog } from "@/api/jobs";
import type { ChangelogEntry } from "@/api/types";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

interface ChangelogFeedProps {
  jobId: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function triggerIcon(trigger: string): string {
  if (trigger === "agent") return "🤖";
  return "👤";
}

function ConfidenceBadge({ value }: { value: string }): React.ReactElement {
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
  if (!value) return <span className="text-xs text-muted-foreground">—</span>;
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

function StrategyBadge({ value }: { value: string }): React.ReactElement {
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200">
      {value}
    </span>
  );
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

const MAX_NOTES_LEN = 80;

function ChangelogEntryCard({ entry }: { entry: ChangelogEntry }): React.ReactElement {
  const [showDiff, setShowDiff] = useState(false);
  const [expandNotes, setExpandNotes] = useState(false);

  const notes = entry.notes ?? null;
  const notesShort = notes && notes.length > MAX_NOTES_LEN
    ? notes.slice(0, MAX_NOTES_LEN) + "…"
    : notes;
  const notesTooLong = notes !== null && notes.length > MAX_NOTES_LEN;

  return (
    <div className="relative pl-10">
      {/* Timeline icon */}
      <div
        className="absolute left-0 top-1 flex items-center justify-center w-7 h-7 rounded-full
                   bg-muted border border-border text-base leading-none"
        aria-hidden="true"
      >
        {triggerIcon(entry.trigger)}
      </div>

      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        {/* Top row */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-mono text-muted-foreground">{entry.block_id}</span>
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-muted text-muted-foreground border border-border">
            Rev {entry.revision_number}
          </span>
          <StrategyBadge value={entry.strategy} />
          <ConfidenceBadge value={entry.confidence} />
          <ReconciliationBadge value={entry.reconciliation_status} />
          <span className="ml-auto text-muted-foreground whitespace-nowrap">
            {formatTimestamp(entry.created_at)}
          </span>
        </div>

        {/* Notes */}
        {notes && (
          <p className="text-sm italic text-muted-foreground">
            &ldquo;{expandNotes ? notes : notesShort}&rdquo;
            {notesTooLong && (
              <button
                type="button"
                className="ml-1 text-xs text-primary hover:underline cursor-pointer"
                onClick={() => setExpandNotes((e) => !e)}
              >
                {expandNotes ? "collapse" : "expand"}
              </button>
            )}
          </p>
        )}

        {/* Diff */}
        {entry.diff_vs_previous && (
          <>
            <button
              type="button"
              className="text-xs text-primary hover:underline cursor-pointer"
              onClick={() => setShowDiff((d) => !d)}
            >
              {showDiff ? "Hide diff" : "Show diff"}
            </button>
            {showDiff && (
              <pre className="mt-2 text-xs overflow-x-auto rounded bg-muted p-3 whitespace-pre-wrap font-mono leading-relaxed">
                {entry.diff_vs_previous.split("\n").map((line, i) => {
                  let cls = "";
                  if (line.startsWith("+")) cls = "text-green-700";
                  else if (line.startsWith("-")) cls = "text-red-700";
                  else if (line.startsWith("@")) cls = "text-blue-600";
                  return (
                    <span key={i} className={cls}>
                      {line}
                      {"\n"}
                    </span>
                  );
                })}
              </pre>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ChangelogFeed({ jobId }: ChangelogFeedProps): React.ReactElement {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["job", jobId, "changelog"],
    queryFn: () => getJobChangelog(jobId),
    enabled: !!jobId,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading changelog…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Could not load changelog.
      </div>
    );
  }

  const entries = [...data.entries].reverse();

  if (entries.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-6">
        No refinements yet — refine a block from the Plan tab to see history here.
      </div>
    );
  }

  return (
    <div className="space-y-4 py-2">
      {entries.map((entry) => (
        <ChangelogEntryCard key={entry.id} entry={entry} />
      ))}
    </div>
  );
}
