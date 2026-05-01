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
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Activity, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ConnectionStatus = "connecting" | "streaming" | "done" | "cancelled";

interface LiveTraceDialogProps {
  jobId: string;
  jobName: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onJobDone?: (finalStatus: string) => void;
}

// ---------------------------------------------------------------------------
// Status chip
// ---------------------------------------------------------------------------

function StatusChip({ status }: { status: ConnectionStatus }): React.ReactElement {
  if (status === "connecting") {
    return (
      <Badge variant="outline" className="gap-1.5 text-[11px] px-2 py-0.5 text-muted-foreground">
        <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" aria-hidden />
        Connecting
      </Badge>
    );
  }
  if (status === "streaming") {
    return (
      <Badge variant="outline" className="gap-1.5 text-[11px] px-2 py-0.5 text-primary border-primary/40">
        <Activity size={10} className="animate-pulse" aria-hidden />
        Live
      </Badge>
    );
  }
  if (status === "cancelled") {
    return (
      <Badge variant="outline" className="gap-1.5 text-[11px] px-2 py-0.5 text-destructive border-destructive/40">
        <XCircle size={10} aria-hidden />
        Cancelled
      </Badge>
    );
  }
  // done
  return (
    <Badge variant="outline" className="gap-1.5 text-[11px] px-2 py-0.5 text-green-600 dark:text-green-400 border-green-500/40">
      <CheckCircle2 size={10} aria-hidden />
      Done
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Timeline dot
// ---------------------------------------------------------------------------

type DotVariant =
  | "neutral"
  | "success"
  | "warning"
  | "destructive";

function TimelineDot({ variant }: { variant: DotVariant }): React.ReactElement {
  const colorMap: Record<DotVariant, string> = {
    neutral: "bg-muted-foreground",
    success: "bg-green-500",
    warning: "bg-yellow-500",
    destructive: "bg-destructive",
  };
  return (
    <span
      className={`shrink-0 h-2 w-2 rounded-full ${colorMap[variant]} ring-2 ring-background`}
      aria-hidden
    />
  );
}

function dotVariantForEvent(event: TraceEvent): DotVariant {
  switch (event.event_type) {
    case "block_start":
      return "neutral";
    case "block_done":
      return event.status === "pass" ? "success" : "warning";
    case "recon_result":
      return event.checks.every((c) => c.status === "pass") ? "success" : "warning";
    case "job_done":
      if (event.final_status === "done") return "success";
      if (event.final_status === "cancelled") return "destructive";
      return "destructive";
    case "error":
      return "destructive";
    default:
      return "neutral";
  }
}

// ---------------------------------------------------------------------------
// Individual event row renderers
// ---------------------------------------------------------------------------

function BlockStartRow({ event }: { event: BlockStartEvent }): React.ReactElement {
  return (
    <span className="flex items-center gap-2 font-mono text-sm text-foreground min-w-0">
      <Loader2 size={12} className="animate-spin shrink-0 text-muted-foreground" aria-hidden />
      <span className="text-muted-foreground shrink-0">▶</span>
      <span className="text-primary shrink-0">{event.agent}</span>
      <span className="text-muted-foreground shrink-0">/</span>
      <span className="truncate">{event.block_id}</span>
      <span className="text-muted-foreground text-xs shrink-0">attempt {event.attempt}/3</span>
    </span>
  );
}

function BlockDoneRow({ event }: { event: BlockDoneEvent }): React.ReactElement {
  const passed = event.status === "pass";
  return (
    <span className="flex items-center gap-2 font-mono text-sm min-w-0">
      <span
        className={`shrink-0 ${passed ? "text-green-600 dark:text-green-400" : "text-yellow-600 dark:text-yellow-400"}`}
        aria-hidden
      >
        {passed ? "✓" : "✗"}
      </span>
      <span className={`truncate ${passed ? "text-green-600 dark:text-green-400" : "text-yellow-600 dark:text-yellow-400"}`}>
        {event.block_id}
      </span>
      {passed ? (
        <span className="text-muted-foreground text-xs shrink-0">
          {(event.elapsed_ms / 1000).toFixed(1)}s
        </span>
      ) : (
        <span className="text-muted-foreground text-xs shrink-0">
          failed (attempt {event.attempt})
        </span>
      )}
    </span>
  );
}

function ReconResultRow({ event }: { event: ReconResultEvent }): React.ReactElement {
  return (
    <div className="flex flex-col gap-1 ml-6 mt-0.5">
      {event.checks.map((check) => {
        const ok = check.status === "pass";
        return (
          <div key={check.name} className="flex items-center gap-2 font-mono text-xs">
            <Badge
              variant="outline"
              className={
                ok
                  ? "text-green-700 dark:text-green-400 border-green-500/40 px-1.5 py-0 text-[10px]"
                  : "text-yellow-700 dark:text-yellow-400 border-yellow-500/40 px-1.5 py-0 text-[10px]"
              }
            >
              {ok ? "pass" : "fail"}
            </Badge>
            <span className="text-foreground shrink-0">{check.name}</span>
            {!ok && check.detail && (
              <span className="text-muted-foreground truncate">{check.detail}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function JobDoneRow({ event }: { event: JobDoneEvent }): React.ReactElement {
  const success = event.final_status === "done";
  return (
    <div
      className={`w-full flex items-center justify-center gap-2 rounded-md px-4 py-2 font-semibold text-sm
        ${success
          ? "bg-green-500/10 text-green-700 dark:text-green-400 border border-green-500/30"
          : "bg-destructive/10 text-destructive border border-destructive/30"
        }`}
      role="status"
      aria-live="polite"
    >
      {success ? (
        <CheckCircle2 size={14} aria-hidden />
      ) : (
        <XCircle size={14} aria-hidden />
      )}
      Migration {event.final_status}
    </div>
  );
}

function TraceErrorRow({ event }: { event: TraceErrorEvent }): React.ReactElement {
  return (
    <span className="font-mono text-sm text-destructive flex items-center gap-1.5">
      <span aria-hidden>⚠</span>
      {event.message}
    </span>
  );
}

// ---------------------------------------------------------------------------
// EventRow — wraps each event in a timeline row
// ---------------------------------------------------------------------------

function EventRow({ event, isLast, lastRef }: {
  event: TraceEvent;
  isLast: boolean;
  lastRef: React.RefObject<HTMLDivElement | null>;
}): React.ReactElement | null {
  const isJobDone = event.event_type === "job_done";
  const isRecon = event.event_type === "recon_result";

  if (isJobDone) {
    return (
      <div ref={isLast ? lastRef : undefined} className="pt-1 pb-0.5 pl-6">
        <JobDoneRow event={event as JobDoneEvent} />
      </div>
    );
  }

  return (
    <div ref={isLast ? lastRef : undefined} className="flex items-start gap-3 group">
      {/* Timeline rail + dot */}
      <div className="flex flex-col items-center shrink-0 mt-1.5">
        <TimelineDot variant={dotVariantForEvent(event)} />
      </div>

      {/* Content */}
      <div className={`flex-1 min-w-0 pb-0.5 ${isRecon ? "" : "flex items-center"}`}>
        {event.event_type === "block_start" && <BlockStartRow event={event as BlockStartEvent} />}
        {event.event_type === "block_done" && <BlockDoneRow event={event as BlockDoneEvent} />}
        {event.event_type === "recon_result" && <ReconResultRow event={event as ReconResultEvent} />}
        {event.event_type === "error" && <TraceErrorRow event={event as TraceErrorEvent} />}
      </div>
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
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting");
  const [elapsed, setElapsed] = useState(0);
  const [stopping, setStopping] = useState(false);
  const lastItemRef = useRef<HTMLDivElement | null>(null);

  // SSE lifecycle
  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEvents([]);
    setConnectionStatus("connecting");
    setElapsed(0);

    const es = openTraceStream(jobId);

    es.onopen = () => {
      setConnectionStatus("streaming");
    };

    es.onmessage = (e: MessageEvent) => {
      const event = JSON.parse(e.data as string) as TraceEvent;
      setEvents((prev) => [...prev, event]);
      if (event.event_type === "job_done") {
        setConnectionStatus("done");
        es.close();
        onJobDone?.(event.final_status);
      }
    };

    es.onerror = () => {
      setConnectionStatus("done");
      es.close();
    };

    return () => {
      es.close();
    };
  }, [open, jobId]); // eslint-disable-line react-hooks/exhaustive-deps
  // onJobDone intentionally excluded — caller should memoize if needed

  // Elapsed timer
  useEffect(() => {
    if (!open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setElapsed(0);
      return;
    }
    const start = Date.now();
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [open]);

  // Auto-scroll
  useEffect(() => {
    lastItemRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  const isTerminal = connectionStatus === "done" || connectionStatus === "cancelled";

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
        <div className="px-6 pt-6 pb-4 border-b border-border shrink-0">
          <DialogHeader>
            <div className="flex items-center justify-between gap-3">
              <DialogTitle className="truncate text-base font-semibold">
                {jobName ?? jobId}
              </DialogTitle>
              <StatusChip status={connectionStatus} />
            </div>
          </DialogHeader>
        </div>

        {/* Body — scrollable event list */}
        <div
          className="flex-1 overflow-y-auto px-6 py-4"
          role="log"
          aria-label="Trace events"
          aria-live="polite"
        >
          {/* Connecting placeholder */}
          {events.length === 0 && connectionStatus === "connecting" && (
            <div className="flex items-center gap-2 text-muted-foreground text-xs font-mono">
              <Loader2 size={12} className="animate-spin" aria-hidden />
              Connecting to stream…
            </div>
          )}

          {/* Timeline */}
          {events.length > 0 && (
            <div className="relative flex flex-col gap-2.5">
              {/* Vertical rail */}
              <div
                className="absolute left-0.75 top-2 bottom-2 w-px bg-border"
                aria-hidden
              />

              {events.map((event, idx) => (
                <EventRow
                  key={idx}
                  event={event}
                  isLast={idx === events.length - 1}
                  lastRef={lastItemRef}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <DialogFooter className="px-6 py-4 border-t border-border shrink-0 flex items-center justify-between sm:justify-between">
          {/* Left: elapsed */}
          <span
            className="text-xs text-muted-foreground font-mono tabular-nums"
            aria-label="Elapsed time"
          >
            {elapsed}s
          </span>

          {/* Right: action buttons */}
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
                  <Loader2 size={13} className="animate-spin mr-1.5" aria-hidden />
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
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
