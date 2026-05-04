import { cancelJob, openTraceStream } from "@/api/jobs";
import type {
  BlockDoneEvent,
  BlockStartEvent,
  JobDoneEvent,
  ReconResultEvent,
  TraceErrorEvent,
  TraceEvent,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  Loader2,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ConnectionStatus = "connecting" | "streaming" | "done" | "cancelled";
type BlockState = "running" | "error" | "no-recon" | "pass" | "fail";

interface LiveTraceDialogProps {
  jobId: string;
  jobName: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onJobDone?: (finalStatus: string) => void;
}

// ---------------------------------------------------------------------------
// Status chips
// ---------------------------------------------------------------------------

function FinalStatusChip({ status }: { status: string }): React.ReactElement {
  const isGood =
    status === "proposed" || status === "done" || status === "under_review";
  const isCancelled = status === "cancelled";
  if (isCancelled) {
    return (
      <Badge
        variant="outline"
        className="gap-1.5 text-[11px] px-2 py-0.5 text-yellow-600 dark:text-yellow-400 border-yellow-500/40"
      >
        <XCircle size={10} aria-hidden />
        Cancelled
      </Badge>
    );
  }
  if (isGood) {
    return (
      <Badge
        variant="outline"
        className="gap-1.5 text-[11px] px-2 py-0.5 text-green-600 dark:text-green-400 border-green-500/40"
      >
        <CheckCircle2 size={10} aria-hidden />
        {status}
      </Badge>
    );
  }
  return (
    <Badge
      variant="outline"
      className="gap-1.5 text-[11px] px-2 py-0.5 text-destructive border-destructive/40"
    >
      <XCircle size={10} aria-hidden />
      {status}
    </Badge>
  );
}

function StatusChip({
  status,
}: {
  status: ConnectionStatus;
}): React.ReactElement {
  if (status === "connecting") {
    return (
      <Badge
        variant="outline"
        className="gap-1.5 text-[11px] px-2 py-0.5 text-muted-foreground"
      >
        <Loader2 size={10} className="animate-spin" aria-hidden />
        Connecting
      </Badge>
    );
  }
  if (status === "streaming") {
    return (
      <Badge
        variant="outline"
        className="gap-1.5 text-[11px] px-2 py-0.5 text-primary border-primary/40"
      >
        <Activity size={10} className="animate-pulse" aria-hidden />
        Live
      </Badge>
    );
  }
  if (status === "cancelled") {
    return (
      <Badge
        variant="outline"
        className="gap-1.5 text-[11px] px-2 py-0.5 text-destructive border-destructive/40"
      >
        <XCircle size={10} aria-hidden />
        Cancelled
      </Badge>
    );
  }
  return (
    <Badge
      variant="outline"
      className="gap-1.5 text-[11px] px-2 py-0.5 text-green-600 dark:text-green-400 border-green-500/40"
    >
      <CheckCircle2 size={10} aria-hidden />
      Done
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function deriveBlockState(group: GroupedBlock): BlockState {
  if (group.startEvent && !group.doneEvent) return "running";
  if (group.doneEvent?.status === "error") return "error";
  if (group.doneEvent && group.doneEvent.status === "pass" && !group.reconEvent)
    return "no-recon";
  if (group.reconEvent?.all_passed === true) return "pass";
  if (group.reconEvent && group.reconEvent.all_passed === false) return "fail";
  return "running";
}

const CHECK_LABEL_MAP: Record<string, string> = {
  schema_parity: "Schema Parity",
  row_count: "Row Count",
  aggregate_parity: "Aggregate Parity",
};

function humanCheckLabel(name: string): string {
  return CHECK_LABEL_MAP[name] ?? name;
}

function blockStateTextClass(state: BlockState): string {
  switch (state) {
    case "running":
      return "text-muted-foreground";
    case "error":
      return "text-red-500";
    case "no-recon":
    case "pass":
      return "text-green-500";
    case "fail":
      return "text-red-500";
  }
}

function blockStateBorderClass(state: BlockState): string {
  switch (state) {
    case "running":
      return "border-muted";
    case "no-recon":
    case "pass":
      return "border-green-500";
    case "fail":
    case "error":
      return "border-red-500";
  }
}

function BlockStateIcon({
  state,
  size = 13,
}: {
  state: BlockState;
  size?: number;
}): React.ReactElement {
  switch (state) {
    case "running":
      return (
        <Loader2
          size={size}
          className="animate-spin text-muted-foreground"
          aria-hidden
        />
      );
    case "error":
    case "fail":
      return <XCircle size={size} className="text-red-500" aria-hidden />;
    case "no-recon":
    case "pass":
      return (
        <CheckCircle2 size={size} className="text-green-500" aria-hidden />
      );
  }
}

// ---------------------------------------------------------------------------
// ReconCheckList — shared between BlockGroup and PipelineSummaryBanner
// ---------------------------------------------------------------------------

function ReconCheckList({
  reconEvent,
}: {
  reconEvent: ReconResultEvent;
}): React.ReactElement {
  return (
    <div className="flex flex-col gap-1.5">
      {reconEvent.checks.map((check) => {
        const ok = check.status === "pass";
        return (
          <div key={check.name} className="flex flex-col gap-0.5">
            <div className="flex items-start gap-2 font-mono text-xs">
              {ok ? (
                <CheckCircle2
                  size={11}
                  className="shrink-0 mt-px text-green-600 dark:text-green-400"
                  aria-hidden
                />
              ) : (
                <XCircle
                  size={11}
                  className="shrink-0 mt-px text-red-500"
                  aria-hidden
                />
              )}
              <span
                className={`shrink-0 font-medium ${
                  ok ? "text-foreground" : "text-red-500"
                }`}
              >
                {humanCheckLabel(check.name)}
              </span>
            </div>
            {check.detail && check.detail.length > 0 && (
              <pre className="text-xs mt-1 whitespace-pre-wrap text-muted-foreground ml-5">
                {check.detail}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// BlockGroup — collapsible row
// ---------------------------------------------------------------------------

interface GroupedBlock {
  blockId: string;
  startEvent?: BlockStartEvent;
  doneEvent?: BlockDoneEvent;
  reconEvent?: ReconResultEvent;
}

function BlockGroup({
  group,
  isFirst,
  isLast,
  lastRef,
}: {
  group: GroupedBlock;
  isFirst: boolean;
  isLast: boolean;
  lastRef: React.RefObject<HTMLDivElement | null>;
}): React.ReactElement {
  const [userToggled, setExpanded] = useState<boolean | null>(null);
  const blockState = deriveBlockState(group);
  const hasRecon = !!group.reconEvent;
  const hasDone = !!group.doneEvent;
  const isRunning = blockState === "running";
  const attempt = group.doneEvent?.attempt ?? group.startEvent?.attempt;
  // Expandable whenever block has finished (done or has recon) or is running
  const canExpand = hasDone || hasRecon || isRunning;
  // Auto-expand when recon arrives; user toggle overrides
  const expanded = userToggled !== null ? userToggled : hasRecon;

  const textClass = blockStateTextClass(blockState);

  return (
    <div
      ref={isLast ? lastRef : undefined}
      className="flex items-stretch gap-2"
    >
      {/* Icon column with rail segments above/below */}
      <div
        className="flex flex-col items-center shrink-0"
        style={{ width: 14 }}
      >
        {/* Top rail — connects to previous row */}
        <div
          className={`w-px flex-none ${isFirst ? "h-1.75" : "h-1.75 bg-border"}`}
        />
        {/* Icon */}
        <div
          className="shrink-0 flex items-center justify-center"
          style={{ width: 14, height: 14 }}
        >
          <BlockStateIcon state={blockState} size={13} />
        </div>
        {/* Bottom rail — connects to next row */}
        <div className={`w-px flex-1 min-h-2 ${isLast ? "" : "bg-border"}`} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pb-1">
        <button
          type="button"
          disabled={!canExpand}
          onClick={() => canExpand && setExpanded(!expanded)}
          aria-expanded={canExpand ? expanded : undefined}
          className={`w-full flex items-center gap-2 rounded-sm px-1 py-1 text-left transition-colors
            ${
              canExpand
                ? "cursor-pointer hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                : "cursor-default opacity-100"
            }`}
        >
          {/* Block id — show only filename:line, strip leading directory */}
          <span
            className={`font-mono text-xs truncate flex-1 min-w-0 ${textClass}`}
          >
            {group.blockId.replace(/^.*[/]/, "")}
          </span>

          {/* Attempt pill */}
          {attempt !== undefined && (
            <Badge
              variant="secondary"
              className="px-1.5 py-0 text-[10px] tabular-nums shrink-0"
            >
              attempt {attempt}
            </Badge>
          )}

          {/* Chevron — shown whenever block can be expanded */}
          {canExpand && (
            <ChevronDown
              size={12}
              className={`shrink-0 transition-transform duration-150 text-muted-foreground ${expanded ? "rotate-180" : ""}`}
            />
          )}
        </button>

        {/* Detail section — recon checks, "running…" indicator, or "no ref" note */}
        {canExpand && expanded ? (
          <div className="ml-1 mb-1 mt-0.5 pl-2">
            {isRunning && !hasRecon ? (
              <span className="text-xs text-muted-foreground animate-pulse">
                running checks…
              </span>
            ) : hasRecon ? (
              <ReconCheckList reconEvent={group.reconEvent!} />
            ) : (
              <span className="text-xs text-muted-foreground">
                Executed — no reference file matched for this block
              </span>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PipelineSummaryBanner — full-width card for pipeline:full recon
// ---------------------------------------------------------------------------

function PipelineSummaryBanner({
  group,
}: {
  group: GroupedBlock;
}): React.ReactElement {
  const [userToggled, setExpanded] = useState<boolean | null>(null);
  const blockState = deriveBlockState(group);
  const hasRecon = !!group.reconEvent;
  const expanded = userToggled !== null ? userToggled : hasRecon;

  const borderClass = blockStateBorderClass(blockState);
  const textClass = blockStateTextClass(blockState);

  return (
    <div
      className={`mt-3 rounded-md border border-border border-l-4 ${borderClass} bg-card px-4 py-3`}
    >
      <div className="flex items-center gap-3">
        <BlockStateIcon state={blockState} size={14} />
        <span className={`font-semibold text-sm flex-1 ${textClass}`}>
          Full Pipeline Reconciliation
        </span>
        {group.doneEvent?.elapsed_ms !== undefined && (
          <Badge
            variant="secondary"
            className="text-[10px] px-1.5 py-0 tabular-nums shrink-0"
          >
            {(group.doneEvent.elapsed_ms / 1000).toFixed(1)}s
          </Badge>
        )}
        {hasRecon && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
            aria-label="Toggle pipeline reconciliation details"
            className="shrink-0 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded"
          >
            <ChevronDown
              size={14}
              className={`text-muted-foreground transition-transform duration-150 ${expanded ? "rotate-180" : ""}`}
            />
          </button>
        )}
      </div>
      {hasRecon && expanded && (
        <div className="mt-2 border-t border-border pt-2">
          <ReconCheckList reconEvent={group.reconEvent!} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error row
// ---------------------------------------------------------------------------

function ErrorRow({ event }: { event: TraceErrorEvent }): React.ReactElement {
  return (
    <div className="flex items-start gap-2 px-1 py-1">
      <span className="w-3.25 shrink-0 flex items-center justify-center">
        <XCircle size={13} className="text-destructive" aria-hidden />
      </span>
      <span className="font-mono text-sm text-destructive">
        {event.message}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// LiveTraceDialog
// ---------------------------------------------------------------------------

export default function LiveTraceDialog({
  jobId,
  jobName,
  open,
  onOpenChange,
  onJobDone,
}: LiveTraceDialogProps): React.ReactElement {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("connecting");
  const [elapsed, setElapsed] = useState(0);
  const [stopping, setStopping] = useState(false);
  const [finalStatus, setFinalStatus] = useState<string | null>(null);
  const lastItemRef = useRef<HTMLDivElement | null>(null);
  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // SSE lifecycle
  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEvents([]);
    setConnectionStatus("connecting");
    setElapsed(0);
    setFinalStatus(null);

    const es = openTraceStream(jobId);
    es.onopen = () => setConnectionStatus("streaming");
    es.onmessage = (e: MessageEvent) => {
      const event = JSON.parse(e.data as string) as TraceEvent;
      setEvents((prev) => [...prev, event]);
      if (event.event_type === "job_done") {
        setConnectionStatus("done");
        setFinalStatus((event as JobDoneEvent).final_status);
        es.close();
        onJobDone?.((event as JobDoneEvent).final_status);
      }
    };
    es.onerror = () => {
      setConnectionStatus("done");
      es.close();
    };
    return () => es.close();
  }, [open, jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Elapsed timer
  useEffect(() => {
    if (!open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setElapsed(0);
      return;
    }
    const start = Date.now();
    elapsedRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => {
      if (elapsedRef.current) clearInterval(elapsedRef.current);
    };
  }, [open]);

  // Freeze on terminal
  useEffect(() => {
    if (
      (connectionStatus === "done" || connectionStatus === "cancelled") &&
      elapsedRef.current
    ) {
      clearInterval(elapsedRef.current);
      elapsedRef.current = null;
    }
  }, [connectionStatus]);

  // Auto-scroll
  useEffect(() => {
    lastItemRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  // Group events by block_id
  const blockGroups = useMemo(() => {
    const groups = new Map<string, GroupedBlock>();
    const order: string[] = [];
    for (const event of events) {
      if (event.event_type === "block_start") {
        const id = (event as BlockStartEvent).block_id;
        if (!groups.has(id)) {
          groups.set(id, { blockId: id });
          order.push(id);
        }
        groups.get(id)!.startEvent = event as BlockStartEvent;
      } else if (event.event_type === "block_done") {
        const id = (event as BlockDoneEvent).block_id;
        if (!groups.has(id)) {
          groups.set(id, { blockId: id });
          order.push(id);
        }
        groups.get(id)!.doneEvent = event as BlockDoneEvent;
      } else if (event.event_type === "recon_result") {
        const id = (event as ReconResultEvent).block_id;
        if (!groups.has(id)) {
          groups.set(id, { blockId: id });
          order.push(id);
        }
        groups.get(id)!.reconEvent = event as ReconResultEvent;
      }
    }
    return order.map((id) => groups.get(id)!);
  }, [events]);

  const errorEvents = useMemo(
    () => events.filter((e) => e.event_type === "error") as TraceErrorEvent[],
    [events],
  );

  // Separate pipeline:full from regular blocks
  const regularGroups = useMemo(
    () => blockGroups.filter((g) => g.blockId !== "pipeline:full"),
    [blockGroups],
  );
  const pipelineGroup = useMemo(
    () => blockGroups.find((g) => g.blockId === "pipeline:full"),
    [blockGroups],
  );

  const isTerminal =
    connectionStatus === "done" || connectionStatus === "cancelled";

  const handleStop = async () => {
    if (isTerminal || stopping) return;
    setStopping(true);
    try {
      await cancelJob(jobId);
      setConnectionStatus("cancelled");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to cancel job");
    } finally {
      setStopping(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-2xl w-[95vw] h-[75vh] flex flex-col gap-0 p-0"
        aria-label="Live migration trace"
      >
        {/* Header */}
        <div className="px-6 pt-5 pb-4 border-b border-border shrink-0">
          <DialogHeader>
            <div className="flex items-center justify-between gap-3">
              <DialogTitle className="truncate text-base font-semibold">
                {jobName ?? jobId}
              </DialogTitle>
              {finalStatus ? (
                <FinalStatusChip status={finalStatus} />
              ) : (
                <StatusChip status={connectionStatus} />
              )}
            </div>
          </DialogHeader>
        </div>

        {/* Timeline body */}
        <div
          className="flex-1 overflow-y-auto px-4 py-2"
          role="log"
          aria-label="Trace events"
          aria-live="polite"
        >
          {events.length === 0 && connectionStatus === "connecting" && (
            <div className="flex items-center gap-2 text-muted-foreground text-xs font-mono px-1 py-2">
              <Loader2 size={12} className="animate-spin" aria-hidden />
              Connecting to stream…
            </div>
          )}

          {/* Block rows — rail is built into each row's icon column */}
          <div className="flex flex-col">
            {regularGroups.map((group, idx) => (
              <BlockGroup
                key={group.blockId}
                group={group}
                isFirst={idx === 0}
                isLast={
                  idx === regularGroups.length - 1 && errorEvents.length === 0
                }
                lastRef={lastItemRef}
              />
            ))}
          </div>

          {/* Pipeline-level summary banner */}
          {pipelineGroup && <PipelineSummaryBanner group={pipelineGroup} />}

          {errorEvents.map((ev, idx) => (
            <ErrorRow key={`err-${idx}`} event={ev} />
          ))}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-border shrink-0 flex items-center justify-between gap-3">
          <span
            className="text-xs text-muted-foreground font-mono tabular-nums"
            aria-label="Elapsed time"
          >
            {elapsed}s
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                void handleStop();
              }}
              disabled={isTerminal || stopping}
              aria-label="Stop job"
            >
              {stopping ? (
                <>
                  <Loader2
                    size={13}
                    className="animate-spin mr-1.5"
                    aria-hidden
                  />
                  Stopping…
                </>
              ) : (
                "Stop"
              )}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              aria-label="Close dialog"
            >
              Close
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
