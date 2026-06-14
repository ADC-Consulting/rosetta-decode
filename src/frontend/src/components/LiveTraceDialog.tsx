import { cancelJob, openTraceStream } from "@/api/jobs";
import type {
  BlockDoneEvent,
  BlockStartEvent,
  EnrichmentItemDoneEvent,
  JobDoneEvent,
  ParseResultEvent,
  PhaseDoneEvent,
  PhaseName,
  PhaseStartEvent,
  PhaseStatus,
  PlanResultEvent,
  ReconResultEvent,
  TraceErrorEvent,
  TraceEvent,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  Activity,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  Code2,
  GitMerge,
  Loader2,
  ScanText,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
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
// Phase config
// ---------------------------------------------------------------------------

const PHASE_ORDER: PhaseName[] = [
  "parse_analysis",
  "migration_planning",
  "translation",
  "assembly_recon",
  "enrichment",
];

interface PhaseData {
  status: PhaseStatus;
  elapsedMs?: number;
  parseResult?: ParseResultEvent;
  planResult?: PlanResultEvent;
  enrichmentItems: Partial<
    Record<"lineage" | "documentation" | "plain_english", "done" | "skipped" | "error">
  >;
}

const PHASE_ICONS: Record<PhaseName, LucideIcon> = {
  parse_analysis: ScanText,
  migration_planning: ClipboardList,
  translation: Code2,
  assembly_recon: GitMerge,
  enrichment: BookOpen,
};

const PHASE_LABELS: Record<PhaseName, string> = {
  parse_analysis: "Parsing & Analysis",
  migration_planning: "Migration Planning",
  translation: "Code Translation",
  assembly_recon: "Assembly & Validation",
  enrichment: "Lineage & Documentation",
};

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
// ReconCheckList — shared between BlockGroup and Phase 4 children
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
// BlockGroup — collapsible row (unchanged)
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
// Detail panels
// ---------------------------------------------------------------------------

function ParseDetailPanel({
  data,
}: {
  data: ParseResultEvent;
}): React.ReactElement {
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-xs text-muted-foreground">
        {data.block_count} blocks · {data.file_count} files · {data.macro_var_count} macros
      </p>
      {data.block_type_counts && Object.keys(data.block_type_counts).length > 0 && (
        <div className="flex flex-wrap gap-1">
          {Object.entries(data.block_type_counts)
            .sort((a, b) => b[1] - a[1])
            .map(([type, count]) => (
              <span
                key={type}
                className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] bg-muted text-muted-foreground font-mono"
              >
                {type.replace("_", " ")} &times;{count}
              </span>
            ))}
        </div>
      )}
    </div>
  );
}

function PlanDetailPanel({
  data,
}: {
  data: PlanResultEvent;
}): React.ReactElement {
  const [showSummary, setShowSummary] = useState(false);
  const [showDeps, setShowDeps] = useState(false);
  const [showBlocks, setShowBlocks] = useState(false);
  const riskVariant = {
    low: "default",
    medium: "outline",
    high: "destructive",
  }[data.overall_risk] as "default" | "outline" | "destructive";

  const riskColor = (r: string) =>
    r === "high"
      ? "text-destructive"
      : r === "medium"
        ? "text-yellow-600 dark:text-yellow-400"
        : "text-green-600 dark:text-green-400";

  const strategyLabel = (s: string) =>
    (
      {
        translated: "Auto",
        translated_with_review: "Review",
        manual: "Manual",
      } as Record<string, string>
    )[s] ?? s;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Badge variant={riskVariant} className="text-xs">
          {data.overall_risk} risk
        </Badge>
        {data.review_block_count > 0 && (
          <span>{data.review_block_count} blocks flagged for review</span>
        )}
      </div>

      {data.summary && (
        <>
          <button
            onClick={() => setShowSummary((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground text-left"
          >
            {showSummary ? "Hide summary ▴" : "Show summary ▾"}
          </button>
          {showSummary && (
            <p className="text-xs text-muted-foreground leading-relaxed">
              {data.summary}
            </p>
          )}
        </>
      )}

      {data.cross_file_dependencies && data.cross_file_dependencies.length > 0 && (
        <>
          <button
            onClick={() => setShowDeps((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground text-left"
          >
            {showDeps
              ? "Hide cross-file dependencies ▴"
              : `Show cross-file dependencies (${data.cross_file_dependencies.length}) ▾`}
          </button>
          {showDeps && (
            <div className="flex flex-col gap-1">
              {data.cross_file_dependencies.map((dep, i) => {
                const match = dep.match(/^(Dataset\s+[\w.]+)/i);
                const label = match ? match[1].replace(/^Dataset\s+/i, "") : null;
                const body = label
                  ? dep.slice(match![1].length).replace(/^\s*[—–-]\s*|^,\s*|^\s+is\s+/, "is ").trim()
                  : dep;
                // Wrap .sas filenames in <code>
                const renderWithCode = (text: string) =>
                  text.split(/(\S+\.sas\b)/gi).map((part, j) =>
                    /\.sas$/i.test(part) ? (
                      <code key={j} className="font-mono bg-muted px-0.5 rounded text-[9px]">
                        {part}
                      </code>
                    ) : (
                      part
                    )
                  );
                return (
                  <div key={i} className="rounded bg-muted/40 px-2 py-1.5 text-[10px] leading-relaxed">
                    {label && (
                      <code className="font-mono font-semibold text-foreground bg-muted px-0.5 rounded text-[9px]">
                        {label}
                      </code>
                    )}{" "}
                    <span className="text-muted-foreground">{renderWithCode(label ? body : dep)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {data.block_plans && data.block_plans.length > 0 && (
        <>
          <button
            onClick={() => setShowBlocks((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground text-left"
          >
            {showBlocks
              ? "Hide block plan ▴"
              : `Show block plan (${data.block_plans.length} blocks) ▾`}
          </button>
          {showBlocks && (
            <div className="rounded border border-border overflow-hidden">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="bg-muted/50 text-muted-foreground">
                    <th className="text-left px-2 py-1 font-medium">Block</th>
                    <th className="text-left px-2 py-1 font-medium">Type</th>
                    <th className="text-left px-2 py-1 font-medium">Strategy</th>
                    <th className="text-left px-2 py-1 font-medium">Risk</th>
                  </tr>
                </thead>
                <tbody>
                  {data.block_plans.map((bp) => (
                    <tr key={bp.block_id} className="border-t border-border/50">
                      <td
                        className="px-2 py-1 font-mono truncate max-w-30"
                        title={bp.block_id}
                      >
                        {bp.block_id.split(":").pop()}
                      </td>
                      <td className="px-2 py-1 text-muted-foreground font-mono">
                        {bp.block_type.replace("_", " ")}
                      </td>
                      <td className="px-2 py-1">{strategyLabel(bp.strategy)}</td>
                      <td className={cn("px-2 py-1 font-medium", riskColor(bp.risk))}>
                        {bp.risk}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

const ENRICHMENT_LABELS = {
  lineage: "Lineage graph",
  documentation: "Technical docs",
  plain_english: "Plain-English summary",
} as const;

function PipelineSummaryBanner({
  group,
}: {
  group: GroupedBlock;
}): React.ReactElement {
  const [userToggled, setExpanded] = useState<boolean | null>(null);
  const blockState = deriveBlockState(group);
  const hasRecon = !!group.reconEvent;
  const expanded = userToggled !== null ? userToggled : hasRecon;
  const textClass = blockStateTextClass(blockState);
  const borderClass =
    blockState === "pass"
      ? "border-l-green-500"
      : blockState === "fail" || blockState === "error"
        ? "border-l-destructive"
        : blockState === "running"
          ? "border-l-blue-500"
          : "border-l-muted-foreground";
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
              aria-hidden
            />
          </button>
        )}
      </div>
      {hasRecon && expanded && group.reconEvent && (
        <div className="mt-2 pl-5">
          <ReconCheckList reconEvent={group.reconEvent} />
        </div>
      )}
    </div>
  );
}

function EnrichmentDetailPanel({
  items,
}: {
  items: PhaseData["enrichmentItems"];
}): React.ReactElement {
  return (
    <div className="flex flex-col gap-1">
      {(["lineage", "documentation", "plain_english"] as const).map((key) => {
        const s = items[key];
        const Icon =
          s === "done" ? CheckCircle2 : s === "error" ? XCircle : Loader2;
        const cls =
          s === "done"
            ? "text-green-500"
            : s === "error"
              ? "text-destructive"
              : "text-muted-foreground animate-spin";
        return (
          <div
            key={key}
            className="flex items-center gap-1.5 text-xs text-muted-foreground"
          >
            <Icon className={cn("h-3.5 w-3.5", cls)} />
            {ENRICHMENT_LABELS[key]}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PhaseRow — collapsible phase entry with vertical rail
// ---------------------------------------------------------------------------

function PhaseRow({
  icon,
  status,
  label,
  elapsedMs,
  expanded,
  onToggle,
  isLast,
  children,
}: {
  phase: PhaseName;
  status: PhaseStatus;
  icon: LucideIcon;
  label: string;
  elapsedMs?: number;
  expanded: boolean;
  onToggle: () => void;
  isLast: boolean;
  children?: React.ReactNode;
}): React.ReactElement {
  const iconClass = {
    pending: "text-muted-foreground",
    running: "text-primary animate-pulse",
    done: "text-green-500",
    error: "text-destructive",
  }[status];

  const PhaseIcon = icon;

  return (
    <Collapsible open={expanded} onOpenChange={onToggle}>
      <div className="flex gap-3">
        {/* vertical rail line */}
        <div className="flex flex-col items-center">
          <PhaseIcon className={cn("h-5 w-5 mt-0.5 shrink-0", iconClass)} />
          {!isLast && <div className="w-px flex-1 bg-border mt-1" />}
        </div>
        <div className="flex-1 pb-4 min-w-0">
          <CollapsibleTrigger className="flex items-center gap-2 w-full text-left group">
              <span
                className={cn(
                  "font-medium text-sm",
                  status === "pending" && "text-muted-foreground",
                )}
              >
                {label}
              </span>
              {elapsedMs !== undefined && (
                <Badge variant="secondary" className="text-xs font-mono">
                  {elapsedMs < 1000
                    ? `${elapsedMs}ms`
                    : elapsedMs < 60_000
                      ? `${(elapsedMs / 1000).toFixed(1)}s`
                      : `${Math.floor(elapsedMs / 60_000)}m ${Math.floor((elapsedMs % 60_000) / 1000)}s`}
                </Badge>
              )}
              {children && (
                <ChevronDown
                  className={cn(
                    "h-3.5 w-3.5 text-muted-foreground ml-auto transition-transform",
                    expanded && "rotate-180",
                  )}
                />
              )}
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-2">{children}</div>
          </CollapsibleContent>
        </div>
      </div>
    </Collapsible>
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
  const [finalElapsed, setFinalElapsed] = useState<number | null>(null);
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
    setFinalElapsed(null);

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

  // Derive start timestamp from first event (stable once events[0] exists)
  const startMs = events.length > 0 ? new Date(events[0].ts).getTime() : null;

  // Freeze final elapsed when job_done arrives
  useEffect(() => {
    if (finalElapsed !== null || startMs === null) return;
    const doneEv = events.find((e) => e.event_type === "job_done");
    if (doneEv) {
      const frozen = Math.floor((new Date(doneEv.ts).getTime() - startMs) / 1000);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setFinalElapsed(frozen);
      if (elapsedRef.current) clearInterval(elapsedRef.current);
    }
  }, [events, finalElapsed, startMs]);

  // Tick the live counter while the job is running
  useEffect(() => {
    if (!open || finalElapsed !== null || startMs === null) return;
    elapsedRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startMs) / 1000));
    }, 1000);
    return () => {
      if (elapsedRef.current) clearInterval(elapsedRef.current);
    };
  }, [open, finalElapsed, startMs]);

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
  const pipelineGroup = useMemo(
    () => blockGroups.find((g) => g.blockId === "pipeline:full"),
    [blockGroups],
  );

  // Derive phase map from events
  const phaseMap = useMemo<Record<PhaseName, PhaseData>>(() => {
    const map = Object.fromEntries(
      PHASE_ORDER.map((p) => [
        p,
        { status: "pending" as PhaseStatus, enrichmentItems: {} },
      ]),
    ) as Record<PhaseName, PhaseData>;

    for (const ev of events) {
      if (ev.event_type === "phase_start") {
        map[(ev as PhaseStartEvent).phase].status = "running";
      } else if (ev.event_type === "phase_done") {
        const pde = ev as PhaseDoneEvent;
        map[pde.phase].status = pde.status === "error" ? "error" : "done";
        map[pde.phase].elapsedMs = pde.elapsed_ms;
      } else if (ev.event_type === "parse_result") {
        map["parse_analysis"].parseResult = ev as ParseResultEvent;
      } else if (ev.event_type === "plan_result") {
        map["migration_planning"].planResult = ev as PlanResultEvent;
      } else if (ev.event_type === "enrichment_item_done") {
        const eid = ev as EnrichmentItemDoneEvent;
        map["enrichment"].enrichmentItems[eid.item] = eid.status;
      }
    }
    return map;
  }, [events]);

  // Expansion state — translation open by default
  const [expandedPhases, setExpandedPhases] = useState<Set<PhaseName>>(
    () => new Set<PhaseName>(["translation"]),
  );

  // Auto-expand running phase
  const activePhase = useMemo(
    () => PHASE_ORDER.find((p) => phaseMap[p].status === "running"),
    [phaseMap],
  );
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!activePhase) return;
    setExpandedPhases((prev) =>
      prev.has(activePhase) ? prev : new Set([...prev, activePhase]),
    );
  }, [activePhase]);

  // Auto-collapse completed non-translation phases after 1.2s — fires once per phase transition
  const collapsedDoneRef = useRef<Set<PhaseName>>(new Set());
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    PHASE_ORDER.filter((p) => p !== "translation").forEach((p) => {
      if (phaseMap[p].status === "done" && !collapsedDoneRef.current.has(p)) {
        collapsedDoneRef.current.add(p);
        timers.push(
          setTimeout(() => {
            setExpandedPhases((prev) => {
              if (!prev.has(p)) return prev;
              const s = new Set(prev);
              s.delete(p);
              return s;
            });
          }, 1200),
        );
      }
    });
    return () => timers.forEach(clearTimeout);
  }, [phaseMap]);
  /* eslint-enable react-hooks/set-state-in-effect */

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
          className="flex-1 overflow-y-auto"
          role="log"
          aria-label="Trace events"
          aria-live="polite"
        >
          {events.length === 0 && connectionStatus === "connecting" && (
            <div className="flex items-center gap-2 text-muted-foreground text-xs font-mono px-5 py-3">
              <Loader2 size={12} className="animate-spin" aria-hidden />
              Connecting to stream…
            </div>
          )}

          {/* 5-phase collapsible rail — only render phases that have started */}
          <div className="flex flex-col px-4 py-3">
            {PHASE_ORDER.filter((phase) => phaseMap[phase].status !== "pending").map((phase, i, visible) => {
              const data = phaseMap[phase];
              return (
                <PhaseRow
                  key={phase}
                  phase={phase}
                  status={data.status}
                  icon={PHASE_ICONS[phase]}
                  label={PHASE_LABELS[phase]}
                  elapsedMs={data.elapsedMs}
                  expanded={expandedPhases.has(phase)}
                  onToggle={() =>
                    setExpandedPhases((prev) => {
                      const s = new Set(prev);
                      if (s.has(phase)) s.delete(phase); else s.add(phase);
                      return s;
                    })
                  }
                  isLast={i === visible.length - 1}
                >
                  {phase === "parse_analysis" && data.parseResult && (
                    <ParseDetailPanel data={data.parseResult} />
                  )}
                  {phase === "migration_planning" && data.planResult && (
                    <PlanDetailPanel data={data.planResult} />
                  )}
                  {phase === "translation" && (
                    <>
                      {blockGroups
                        .filter((g) => g.blockId !== "pipeline:full")
                        .map((group, idx, arr) => (
                          <BlockGroup
                            key={group.blockId}
                            group={group}
                            isFirst={idx === 0}
                            isLast={idx === arr.length - 1}
                            lastRef={lastItemRef}
                          />
                        ))}
                      {pipelineGroup && (
                        <PipelineSummaryBanner group={pipelineGroup} />
                      )}
                    </>
                  )}
                  {phase === "assembly_recon" && !pipelineGroup && (
                    <p className="text-xs text-muted-foreground">No reference data — skipped</p>
                  )}
                  {phase === "enrichment" && (
                    <EnrichmentDetailPanel items={data.enrichmentItems} />
                  )}
                </PhaseRow>
              );
            })}
          </div>

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
            {(() => { const s = finalElapsed ?? elapsed; return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`; })()}
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
