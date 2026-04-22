import { getBlockRevisions, restoreBlockRevision } from "@/api/jobs";
import type { BlockRevision } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

interface BlockRevisionDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  jobId: string;
  blockId: string;
  isAccepted?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function triggerIcon(trigger: string): string {
  if (trigger === "human-refine" || trigger === "restore") return "👤";
  return "🤖";
}

function confidenceBadge(confidence: string): React.ReactElement {
  const lower = confidence.toLowerCase();
  const cls =
    lower === "high"
      ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
      : lower === "medium"
        ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
        : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        cls,
      )}
    >
      {confidence}
    </span>
  );
}

function reconciliationBadge(
  status: "pass" | "fail" | null,
): React.ReactElement {
  if (status === "pass") {
    return (
      <span className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-semibold bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300">
        ✓ pass
      </span>
    );
  }
  if (status === "fail") {
    return (
      <span className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-semibold bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300">
        ✗ fail
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold bg-muted text-muted-foreground">
      — n/a
    </span>
  );
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  const now = Date.now();
  const diffMs = now - date.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `${diffD}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ---------------------------------------------------------------------------
// Side-by-side diff parser
// ---------------------------------------------------------------------------

function parseDiffSideBySide(diff: string): {
  left: string[];
  right: string[];
} {
  const left: string[] = [];
  const right: string[] = [];
  for (const line of diff.split("\n")) {
    if (line.startsWith("-")) {
      left.push(line.slice(1));
      right.push("");
    } else if (line.startsWith("+")) {
      left.push("");
      right.push(line.slice(1));
    } else {
      const l = line.startsWith("\\") ? "" : line.replace(/^[ @]/, "");
      left.push(l);
      right.push(l);
    }
  }
  return { left, right };
}

// ---------------------------------------------------------------------------
// Inline diff block
// ---------------------------------------------------------------------------

function InlineDiffBlock({ diff }: { diff: string }): React.ReactElement {
  const lines = diff.split("\n");
  return (
    <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-muted/40 p-2 text-[11px] leading-relaxed font-mono">
      {lines.map((line, i) => {
        const cls = line.startsWith("+")
          ? "text-green-700 dark:text-green-400"
          : line.startsWith("-")
            ? "text-red-700 dark:text-red-400"
            : "text-muted-foreground";
        return (
          <span key={i} className={cn("block", cls)}>
            {line || " "}
          </span>
        );
      })}
    </pre>
  );
}

// ---------------------------------------------------------------------------
// RevisionRow
// ---------------------------------------------------------------------------

function RevisionRow({
  revision,
  isLatest,
  isAccepted,
  jobId,
  blockId,
  diffMode,
}: {
  revision: BlockRevision;
  isLatest: boolean;
  isAccepted?: boolean;
  jobId: string;
  blockId: string;
  diffMode: "inline" | "side-by-side";
}): React.ReactElement {
  const queryClient = useQueryClient();
  const [showDiff, setShowDiff] = useState(false);
  const [restoring, setRestoring] = useState(false);

  const handleRestore = async (): Promise<void> => {
    setRestoring(true);
    try {
      await restoreBlockRevision(jobId, blockId, revision.id);
      await queryClient.invalidateQueries({
        queryKey: ["block-revisions", jobId, blockId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["trust-report", jobId],
      });
      toast.success(`Restored to revision ${revision.revision_number}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Restore failed");
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className="rounded-md border border-border bg-background p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-base leading-none" aria-hidden>
          {triggerIcon(revision.trigger)}
        </span>
        <span className="text-xs font-semibold text-foreground">
          Rev {revision.revision_number}
        </span>
        {confidenceBadge(revision.confidence)}
        {reconciliationBadge(revision.reconciliation_status)}
        <span className="ml-auto text-[11px] text-muted-foreground tabular-nums">
          {formatTimestamp(revision.created_at)}
        </span>
      </div>

      {revision.notes && (
        <p className="text-xs italic text-muted-foreground border-l-2 border-border pl-2">
          "{revision.notes}"
        </p>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        {revision.diff_vs_previous && (
          <button
            onClick={() => setShowDiff((v) => !v)}
            className="text-[11px] text-primary underline-offset-2 hover:underline cursor-pointer"
          >
            {showDiff ? "Hide diff" : "Show diff"}
          </button>
        )}
        {!isLatest && !isAccepted && (
          <Button
            variant="outline"
            size="sm"
            className="h-6 text-[11px] px-2 cursor-pointer ml-auto"
            onClick={() => void handleRestore()}
            disabled={restoring}
            aria-label={`Restore revision ${revision.revision_number}`}
          >
            {restoring ? "Restoring…" : "Restore"}
          </Button>
        )}
      </div>

      {showDiff && revision.diff_vs_previous && (
        <>
          {diffMode === "inline" ? (
            <InlineDiffBlock diff={revision.diff_vs_previous} />
          ) : (
            (() => {
              const { left, right } = parseDiffSideBySide(
                revision.diff_vs_previous,
              );
              return (
                <div className="grid grid-cols-2 gap-2 font-mono text-xs mt-2">
                  <div>
                    <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1 px-1">
                      Before
                    </div>
                    <pre className="overflow-x-auto rounded border border-border bg-muted/20 p-1">
                      {left.map((l, i) => (
                        <div
                          key={i}
                          className={cn(
                            "flex gap-2",
                            l === ""
                              ? "bg-gray-50 opacity-30"
                              : "bg-red-50 text-red-700",
                          )}
                        >
                          <span className="select-none text-muted-foreground/50 w-6 text-right shrink-0">
                            {i + 1}
                          </span>
                          <span>{l || " "}</span>
                        </div>
                      ))}
                    </pre>
                  </div>
                  <div>
                    <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1 px-1">
                      After
                    </div>
                    <pre className="overflow-x-auto rounded border border-border bg-muted/20 p-1">
                      {right.map((l, i) => (
                        <div
                          key={i}
                          className={cn(
                            "flex gap-2",
                            l === ""
                              ? "bg-gray-50 opacity-30"
                              : "bg-green-50 text-green-700",
                          )}
                        >
                          <span className="select-none text-muted-foreground/50 w-6 text-right shrink-0">
                            {i + 1}
                          </span>
                          <span>{l || " "}</span>
                        </div>
                      ))}
                    </pre>
                  </div>
                </div>
              );
            })()
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// BlockRevisionModal (exported as both names for compatibility)
// ---------------------------------------------------------------------------

export function BlockRevisionModal({
  open,
  onOpenChange,
  jobId,
  blockId,
  isAccepted,
}: BlockRevisionDrawerProps): React.ReactElement {
  const [diffMode, setDiffMode] = useState<"inline" | "side-by-side">("inline");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["block-revisions", jobId, blockId],
    queryFn: () => getBlockRevisions(jobId, blockId),
    enabled: open,
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[92vw] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            Block History —{" "}
            <code className="font-mono text-sm">
              {blockId.replace(/:\d+$/, "")}
            </code>
          </DialogTitle>
          <div className="flex items-center gap-2 mt-2">
            <span className="text-xs text-muted-foreground">Diff view:</span>
            <button
              onClick={() => setDiffMode("inline")}
              className={
                "px-2 py-0.5 rounded text-xs border cursor-pointer transition-colors " +
                (diffMode === "inline"
                  ? "bg-foreground text-background border-foreground"
                  : "bg-background text-muted-foreground border-border hover:border-foreground")
              }
            >
              Inline
            </button>
            <button
              onClick={() => setDiffMode("side-by-side")}
              className={
                "px-2 py-0.5 rounded text-xs border cursor-pointer transition-colors " +
                (diffMode === "side-by-side"
                  ? "bg-foreground text-background border-foreground"
                  : "bg-background text-muted-foreground border-border hover:border-foreground")
              }
            >
              Side by side
            </button>
          </div>
        </DialogHeader>

        <div className="space-y-3 mt-2">
          {isLoading && (
            <p className="text-sm text-muted-foreground text-center py-8">
              Loading revisions…
            </p>
          )}

          {isError && (
            <p className="text-sm text-destructive text-center py-8">
              Failed to load revisions.
            </p>
          )}

          {data && data.revisions.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-8">
              No revisions yet — click Refine to create the first one.
            </p>
          )}

          {data &&
            [...data.revisions]
              .sort((a, b) => b.revision_number - a.revision_number)
              .map((rev, idx) => (
                <RevisionRow
                  key={rev.id}
                  revision={rev}
                  isLatest={idx === 0}
                  isAccepted={isAccepted}
                  jobId={jobId}
                  blockId={blockId}
                  diffMode={diffMode}
                />
              ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// Default export kept for backward compatibility — same component
export default BlockRevisionModal;
