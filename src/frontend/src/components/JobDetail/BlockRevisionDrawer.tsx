import { getBlockRevisions, restoreBlockRevision } from "@/api/jobs";
import type { BlockRevision } from "@/api/types";
import MonacoDiffViewer from "@/components/MonacoDiffViewer";
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

function TriggerIcon({ trigger }: { trigger: string }): React.ReactElement {
  const isHuman = trigger === "human-refine" || trigger === "restore" || trigger === "human";
  return (
    <span
      title={isHuman ? "Human edit" : "Agent generated"}
      className={cn(
        "inline-flex items-center justify-center w-5 h-5 rounded-full text-[11px] shrink-0",
        isHuman
          ? "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
          : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
      )}
    >
      {isHuman ? "👤" : "🤖"}
    </span>
  );
}

function ConfidenceBadge({ confidence }: { confidence: string }): React.ReactElement {
  const lower = confidence.toLowerCase();
  const cls =
    lower === "high"
      ? "bg-green-100 text-green-800"
      : lower === "medium"
        ? "bg-amber-100 text-amber-800"
        : "bg-red-100 text-red-800";
  return (
    <span className={cn("inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide", cls)}>
      {confidence}
    </span>
  );
}

function ReconciliationBadge({ status }: { status: "pass" | "fail" | null }): React.ReactElement {
  if (status === "pass")
    return <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold bg-green-100 text-green-800">✓ pass</span>;
  if (status === "fail")
    return <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold bg-red-100 text-red-800">✗ fail</span>;
  return <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold bg-muted text-muted-foreground">— n/a</span>;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  const diffMin = Math.floor((Date.now() - date.getTime()) / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `${diffD}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}


// ---------------------------------------------------------------------------
// RevisionRow
// ---------------------------------------------------------------------------

function RevisionRow({
  revision,
  previousCode,
  isLatest,
  isAccepted,
  jobId,
  blockId,
}: {
  revision: BlockRevision;
  previousCode: string;   // python_code from the revision before this one ("" for rev 1)
  isLatest: boolean;
  isAccepted?: boolean;
  jobId: string;
  blockId: string;
}): React.ReactElement {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(isLatest);
  const [restoring, setRestoring] = useState(false);

  const handleRestore = async (): Promise<void> => {
    setRestoring(true);
    try {
      await restoreBlockRevision(jobId, blockId, revision.id);
      await queryClient.invalidateQueries({ queryKey: ["block-revisions", jobId, blockId] });
      await queryClient.invalidateQueries({ queryKey: ["trust-report", jobId] });
      toast.success(`Restored to revision ${revision.revision_number}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Restore failed");
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className={cn(
      "rounded-md border bg-background overflow-hidden",
      isLatest ? "border-primary/40 shadow-sm" : "border-border",
    )}>
      {/* Header — click to expand/collapse */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left cursor-pointer hover:bg-muted/40 transition-colors"
      >
        <TriggerIcon trigger={revision.trigger} />
        <span className="text-xs font-semibold text-foreground">
          Rev {revision.revision_number}
        </span>
        {isLatest && (
          <span className="text-[10px] font-medium text-primary bg-primary/10 rounded px-1.5 py-0.5">
            Latest
          </span>
        )}
        <ConfidenceBadge confidence={revision.confidence} />
        <ReconciliationBadge status={revision.reconciliation_status} />
        <span className="ml-auto text-[11px] text-muted-foreground tabular-nums shrink-0">
          {formatTimestamp(revision.created_at)}
        </span>
        <span className="text-muted-foreground/50 text-xs ml-1 shrink-0">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {/* Notes */}
      {revision.notes && (
        <div className="px-3 pb-1">
          <p className="text-xs italic text-muted-foreground border-l-2 border-border pl-2">
            "{revision.notes}"
          </p>
        </div>
      )}

      {/* Monaco diff — original=previousCode, modified=this revision's code */}
      {expanded && (
        <div className="border-t border-border">
          <MonacoDiffViewer
            original={previousCode}
            modified={revision.python_code}
            readOnly
            height="320px"
          />
        </div>
      )}

      {/* Restore button */}
      {!isLatest && !isAccepted && (
        <div className="px-3 py-2 flex justify-end border-t border-border">
          <Button
            variant="outline"
            size="sm"
            className="h-6 text-[11px] px-2 cursor-pointer"
            onClick={() => void handleRestore()}
            disabled={restoring}
          >
            {restoring ? "Restoring…" : "Restore this version"}
          </Button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// BlockRevisionModal
// ---------------------------------------------------------------------------

export function BlockRevisionModal({
  open,
  onOpenChange,
  jobId,
  blockId,
  isAccepted,
}: BlockRevisionDrawerProps): React.ReactElement {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["block-revisions", jobId, blockId],
    queryFn: () => getBlockRevisions(jobId, blockId),
    enabled: open,
  });

  // Sorted newest-first. For each revision at index i, the "previous" code is
  // sorted[i+1].python_code, or "" for the oldest revision.
  const sorted = data
    ? [...data.revisions].sort((a, b) => b.revision_number - a.revision_number)
    : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] w-275 max-h-[88vh] flex flex-col">
        <DialogHeader className="shrink-0">
          <DialogTitle className="flex items-center gap-2">
            Block History —{" "}
            <code className="font-mono text-sm font-normal text-muted-foreground">
              {blockId.replace(/:\d+$/, "")}
            </code>
            {sorted.length > 0 && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {sorted.length} revision{sorted.length !== 1 ? "s" : ""}
              </span>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-3 mt-2 pr-1">
          {isLoading && (
            <p className="text-sm text-muted-foreground text-center py-8">Loading revisions…</p>
          )}
          {isError && (
            <p className="text-sm text-destructive text-center py-8">Failed to load revisions.</p>
          )}
          {data && sorted.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-8">
              No revisions yet — click Refine to generate the first one.
            </p>
          )}
          {sorted.map((rev, idx) => (
            <RevisionRow
              key={rev.id}
              revision={rev}
              previousCode={sorted[idx + 1]?.python_code ?? ""}
              isLatest={idx === 0}
              isAccepted={isAccepted}
              jobId={jobId}
              blockId={blockId}
            />
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default BlockRevisionModal;
