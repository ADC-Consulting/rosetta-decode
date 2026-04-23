import { getBlockRevisions, getJobSources, saveBlockPython } from "@/api/jobs";
import { registerSasLanguage } from "./registerSasLanguage";
import type { BlockPlan, TrustReportBlock } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { Editor } from "@monaco-editor/react";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Code2,
  FileText,
  History,
  Info,
  Lock,
  Moon,
  Pencil,
  Sun,
  Wrench,
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import BlockRefineDialog from "./BlockRefineDialog";
import { BlockRevisionModal } from "./BlockRevisionDrawer";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BlockPlanTableProps {
  blockPlans: BlockPlan[];
  isProposed: boolean;
  trustBlocks?: Record<string, TrustReportBlock>;
  jobId: string;
  isAccepted?: boolean;
  onBlockRefineSuccess?: () => void;
  jobPythonCode?: string;
  generatedFiles?: Record<string, string>;
}

type GroupBy = "none" | "file" | "folder";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function groupBlocks(
  blocks: BlockPlan[],
  groupBy: GroupBy,
): Array<{ key: string; items: BlockPlan[] }> {
  if (groupBy === "none") return [{ key: "", items: blocks }];
  return Object.entries(
    blocks.reduce(
      (acc, bp) => {
        const key =
          groupBy === "file"
            ? bp.source_file
            : bp.source_file.includes("/")
              ? bp.source_file.split("/").slice(0, -1).join("/")
              : "(root)";
        (acc[key] ??= []).push(bp);
        return acc;
      },
      {} as Record<string, BlockPlan[]>,
    ),
  ).map(([key, items]) => ({ key, items }));
}

const STRATEGY_COLOR: Record<string, string> = {
  translate: "text-blue-700 bg-blue-50 border border-blue-200",
  translate_with_review: "text-amber-700 bg-amber-50 border border-amber-200",
  translate_best_effort: "text-orange-700 bg-orange-50 border border-orange-200",
  manual: "text-red-700 bg-red-50 border border-red-200",
  manual_ingestion: "text-red-700 bg-red-50 border border-red-200",
  skip: "text-muted-foreground bg-muted border border-border",
};

const STRATEGY_LABELS: Record<string, string> = {
  translate: "Auto-translate",
  translate_with_review: "Translate + review",
  translate_best_effort: "Best effort",
  manual: "Manual",
  manual_ingestion: "Manual ingestion",
  skip: "Skip",
};

const RISK_COLOR: Record<string, string> = {
  low: "text-green-700",
  medium: "text-amber-700",
  high: "text-red-700",
};

const RISK_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Mid",
  high: "High",
};

const CONFIDENCE_BAND_TEXT_COLOR: Record<string, string> = {
  high: "text-green-700",
  medium: "text-amber-700",
  low: "text-red-600",
  "very low": "text-red-800",
  unknown: "text-muted-foreground",
};

// ---------------------------------------------------------------------------
// Glossary dialog content
// ---------------------------------------------------------------------------

function GlossaryDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}): React.ReactElement {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Glossary</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 text-sm">
          <div>
            <p className="font-semibold mb-1">Risk levels</p>
            <p className="text-xs text-muted-foreground mb-1.5">
              Assigned by the migration planner before translation, based on static analysis of
              each block's SAS constructs. Reflects how likely the block is to need human
              intervention — not whether translation succeeded.
            </p>
            <ul className="space-y-1 text-muted-foreground text-xs">
              <li>
                <span className="font-medium text-green-700">Low</span> — Simple SET/filter/rename
                or straightforward PROC SQL SELECT.
              </li>
              <li>
                <span className="font-medium text-amber-700">Medium</span> — BY-group processing,
                MERGE with complex BY, multi-output DATA steps, CASE expressions.
              </li>
              <li>
                <span className="font-medium text-red-700">High</span> — CALL SYMPUT, dynamic
                dataset names, nested macros, %INCLUDE, deeply nested RETAIN loops, or unsupported
                PROC types.
              </li>
            </ul>
          </div>
          <div>
            <p className="font-semibold mb-1">Confidence score</p>
            <p className="text-xs text-muted-foreground mb-1.5">
              After translating each block, the LLM self-reports a score (0–1) reflecting how
              certain it is that the generated Python is semantically equivalent to the SAS source.
              Factors that lower confidence: complex RETAIN logic, ambiguous date arithmetic,
              macro-dependent variable names, or SAS idioms that required approximation. The
              overall confidence is the average across all translated blocks.
            </p>
            <ul className="space-y-1 text-muted-foreground text-xs">
              <li>
                <span className="font-medium">0.85–1.0</span> —{" "}
                <span className="text-green-700 font-medium">High</span>: LLM is certain, minimal
                review needed.
              </li>
              <li>
                <span className="font-medium">0.65–0.84</span> —{" "}
                <span className="text-amber-700 font-medium">Medium</span>: review recommended,
                especially edge cases.
              </li>
              <li>
                <span className="font-medium">0.40–0.64</span> —{" "}
                <span className="text-red-600 font-medium">Low</span>: manual inspection required
                before accepting.
              </li>
              <li>
                <span className="font-medium">&lt;0.40</span> —{" "}
                <span className="text-red-700 font-medium">Very Low</span>: high risk of incorrect
                output.
              </li>
            </ul>
          </div>
          <div>
            <p className="font-semibold mb-1">Strategies</p>
            <ul className="space-y-1 text-muted-foreground text-xs">
              <li>
                <span className="font-medium text-blue-700">translate</span> — Fully auto-converted
                to Python/PySpark.
              </li>
              <li>
                <span className="font-medium text-amber-700">translate_with_review</span> —
                Converted but flagged for human check (date semantics, format conversions, ambiguous
                merges).
              </li>
              <li>
                <span className="font-medium text-orange-700">translate_best_effort</span> —
                Partial translation; complex constructs approximated, may be incomplete.
              </li>
              <li>
                <span className="font-medium text-red-700">manual</span> — No Python equivalent
                exists; placeholder comment only. Requires human rewrite.
              </li>
              <li>
                <span className="font-medium text-muted-foreground">skip</span> — PROC PRINT /
                housekeeping; nothing emitted to the output pipeline.
              </li>
            </ul>
          </div>
          <div>
            <p className="font-semibold mb-1">Reconciliation status</p>
            <p className="text-xs text-muted-foreground mb-1.5">
              After translation, the generated Python is executed against the same input data as
              the original SAS. The output is compared on schema, row count, and aggregate values.
            </p>
            <ul className="space-y-1 text-muted-foreground text-xs">
              <li>
                <span className="font-medium text-green-700">Auto-verified</span> — schema, row
                count, and aggregates all match. Safe to accept.
              </li>
              <li>
                <span className="font-medium text-amber-700">Needs review</span> — translation ran
                but reconciliation flagged differences. Human check recommended.
              </li>
              <li>
                <span className="font-medium text-foreground">Manual TODO</span> — block has
                strategy manual or manual_ingestion; Python output requires human authoring.
              </li>
              <li>
                <span className="font-medium text-red-700">Failed recon</span> — Python code
                executed but output did not match the SAS reference data.
              </li>
            </ul>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function BlockPlanTable({
  blockPlans,
  trustBlocks = {},
  jobId,
  isAccepted,
  onBlockRefineSuccess,
  jobPythonCode,
  generatedFiles,
}: BlockPlanTableProps): React.ReactElement {
  const queryClient = useQueryClient();
  const [humanEditedBlocks, setHumanEditedBlocks] = useState<Set<string>>(new Set());
  const [refineBlockId, setRefineBlockId] = useState<string | null>(null);
  const [historyBlockId, setHistoryBlockId] = useState<string | null>(null);
  const [codeBlockId, setCodeBlockId] = useState<string | null>(null);
  const [codeSasFile, setCodeSasFile] = useState<string>("");
  const [sasCode, setSasCode] = useState<string>("");
  const [codeDialogPython, setCodeDialogPython] = useState<string>("");
  const [codeEditable, setCodeEditable] = useState(false);
  const [codeSaving, setCodeSaving] = useState(false);
  const [codeLoading, setCodeLoading] = useState(false);
  const [codeEditorDark, setCodeEditorDark] = useState(false);
  const initialCodeRef = useRef<string>("");

  useEffect(() => {
    if (!codeBlockId) return;
    void (async () => {
      setCodeLoading(true);
      try {
        const [history, sources] = await Promise.all([
          getBlockRevisions(jobId, codeBlockId),
          getJobSources(jobId),
        ]);
        const latest = history.revisions[0];
        setCodeDialogPython(
          latest?.python_code ??
            (() => {
              if (!generatedFiles) return jobPythonCode ?? "";
              const pyFile = codeSasFile.replace(/\.sas$/i, ".py");
              return (
                generatedFiles[pyFile] ??
                generatedFiles[
                  Object.keys(generatedFiles).find((k) =>
                    k.endsWith(pyFile.split("/").pop()!),
                  ) ?? ""
                ] ??
                jobPythonCode ??
                ""
              );
            })(),
        );
        const entry = sources.sources[codeSasFile]
          ? ([codeSasFile, sources.sources[codeSasFile]] as [string, string])
          : Object.entries(sources.sources).find(
              ([k]) =>
                k === codeSasFile ||
                k.endsWith("/" + codeSasFile) ||
                codeSasFile.endsWith(k),
            );
        setSasCode(entry ? entry[1] : "");
      } catch {
        setCodeDialogPython(initialCodeRef.current ?? "");
        setSasCode("");
      } finally {
        setCodeLoading(false);
      }
    })();
  }, [codeBlockId, jobId, codeSasFile, generatedFiles, jobPythonCode]);

  const [groupBy, setGroupBy] = useState<GroupBy>(() => {
    const files = new Set(blockPlans.map((b) => b.source_file));
    return files.size > 1 ? "folder" : "none";
  });
  const [activeStrategies, setActiveStrategies] = useState<Set<string>>(new Set());
  const [glossaryOpen, setGlossaryOpen] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const uniqueStrategies = [...new Set(blockPlans.map((b) => b.strategy))];

  function toggleStrategy(s: string): void {
    setActiveStrategies((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  }

  function toggleGroup(key: string): void {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const filtered =
    activeStrategies.size === 0
      ? blockPlans
      : blockPlans.filter((b) => activeStrategies.has(b.strategy));

  const groups = groupBlocks(filtered, groupBy);

  return (
    <TooltipProvider>
      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap mb-3">
        {/* Group by */}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Group by</span>
          <Select value={groupBy} onValueChange={(v) => setGroupBy(v as GroupBy)}>
            <SelectTrigger size="sm" className="h-7 text-xs w-[100px] cursor-pointer">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none" className="text-xs">None</SelectItem>
              <SelectItem value="file" className="text-xs">File</SelectItem>
              <SelectItem value="folder" className="text-xs">Folder</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Separator orientation="vertical" className="h-4" />

        {/* Strategy filter chips */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-muted-foreground shrink-0">Strategy</span>
          {uniqueStrategies.map((s) => (
            <button
              key={s}
              onClick={() => toggleStrategy(s)}
              aria-pressed={activeStrategies.has(s)}
              className={cn(
                "h-6 px-2 rounded-full text-[11px] font-medium border transition-colors cursor-pointer",
                activeStrategies.has(s)
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-background text-muted-foreground border-border hover:border-foreground/50",
              )}
            >
              {STRATEGY_LABELS[s] ?? s}
            </button>
          ))}
          {activeStrategies.size > 0 && (
            <button
              onClick={() => setActiveStrategies(new Set())}
              className="text-[11px] text-muted-foreground hover:text-foreground underline underline-offset-2 cursor-pointer"
            >
              Clear
            </button>
          )}
        </div>

        {/* Glossary button */}
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto h-7 gap-1.5 text-xs text-muted-foreground cursor-pointer"
          onClick={() => setGlossaryOpen(true)}
        >
          <Info size={13} />
          Glossary
        </Button>
      </div>

      <GlossaryDialog open={glossaryOpen} onOpenChange={setGlossaryOpen} />

      {/* Table */}
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="bg-muted/80 backdrop-blur-sm text-left border-b border-border">
              <th className="px-3 py-2 font-medium text-muted-foreground text-xs">Block</th>
              <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-20">Type</th>
              <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-36">
                Strategy
              </th>
              <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-14">Risk</th>
              <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-20">Confidence</th>
              <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-12 text-center">Why</th>
              <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-14 text-center">
                Recon
              </th>
              <th className="px-3 py-2 font-medium text-muted-foreground text-xs w-[88px] text-right pr-3">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {groups.map(({ key, items }) => (
              <React.Fragment key={key}>
                {/* Group header */}
                {groupBy !== "none" && (
                  <tr
                    aria-expanded={!collapsedGroups.has(key)}
                    className="bg-muted/20 cursor-pointer hover:bg-muted/40 select-none"
                    onClick={() => toggleGroup(key)}
                  >
                    <td colSpan={8} className="px-3 py-1.5">
                      <div className="flex items-center gap-2">
                        {collapsedGroups.has(key) ? (
                          <ChevronRight size={12} className="text-muted-foreground shrink-0" />
                        ) : (
                          <ChevronDown size={12} className="text-muted-foreground shrink-0" />
                        )}
                        <span className="text-xs font-semibold text-foreground font-mono">
                          {key}
                        </span>
                        <Badge variant="secondary" className="text-[10px] font-mono px-1.5">
                          {items.length}
                        </Badge>
                      </div>
                    </td>
                  </tr>
                )}

                {/* Rows */}
                {!collapsedGroups.has(key) &&
                  items.map((bp) => {
                    const trust = trustBlocks[bp.block_id];
                    const needsAttention = trust?.needs_attention ?? false;
                    const confPct =
                      typeof bp.confidence_score === "number"
                        ? `${(bp.confidence_score * 100).toFixed(0)}%`
                        : "—";
                    const bandKey = bp.confidence_band?.toLowerCase() ?? "unknown";
                    const bandTextCls =
                      CONFIDENCE_BAND_TEXT_COLOR[bandKey] ?? CONFIDENCE_BAND_TEXT_COLOR["unknown"];

                    const shortBlockId = (() => {
                      const raw = bp.block_id.replace(/:\d+$/, "");
                      const slash = raw.lastIndexOf("/");
                      return slash >= 0 ? raw.slice(slash + 1) : raw;
                    })();

                    return (
                      <tr
                        key={bp.block_id}
                        className={cn(
                          "hover:bg-muted/30 border-l-2 transition-colors",
                          needsAttention ? "border-l-amber-400" : "border-l-transparent",
                        )}
                      >
                        {/* Block */}
                        <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                          <div className="flex items-center gap-1.5">
                            {needsAttention && (
                              <AlertTriangle
                                className="text-amber-500 shrink-0"
                                size={12}
                                aria-hidden
                              />
                            )}
                            <span>{shortBlockId}</span>
                            {bp.start_line != null && (
                              <span className="text-[10px] text-muted-foreground/60 tabular-nums">
                                :{bp.start_line}
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Type */}
                        <td className="px-3 py-2 font-mono text-xs">{bp.block_type}</td>

                        {/* Strategy */}
                        <td className="px-3 py-2 text-xs">
                          <span
                            className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${STRATEGY_COLOR[bp.strategy] ?? ""}`}
                          >
                            {STRATEGY_LABELS[bp.strategy] ?? bp.strategy}
                          </span>
                        </td>

                        {/* Risk */}
                        <td className="px-3 py-2 text-xs">
                          <span className={`font-semibold ${RISK_COLOR[bp.risk] ?? ""}`}>
                            {RISK_LABELS[bp.risk] ?? bp.risk}
                          </span>
                        </td>

                        {/* Confidence */}
                        <td className="px-3 py-2 text-xs w-16">
                          <span className={cn("tabular-nums font-medium", bandTextCls)}>
                            {confPct}
                          </span>
                        </td>

                        {/* Rationale */}
                        <td className="px-3 py-2 text-center w-12">
                          {bp.rationale ? (
                            <Popover>
                              <PopoverTrigger
                                className="inline-flex items-center justify-center h-6 w-6 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                                aria-label="View rationale"
                              >
                                <FileText size={13} />
                              </PopoverTrigger>
                              <PopoverContent
                                side="top"
                                className="max-w-sm text-xs leading-relaxed"
                              >
                                {bp.rationale}
                              </PopoverContent>
                            </Popover>
                          ) : (
                            <span className="text-muted-foreground/50">—</span>
                          )}
                        </td>

                        {/* Recon */}
                        <td className="px-3 py-2 text-center w-14">
                          {trust?.reconciliation_status === "pass" ? (
                            <Badge className="bg-green-100 text-green-700 border-green-200 text-[10px] px-1.5 py-0">
                              Pass
                            </Badge>
                          ) : trust?.reconciliation_status === "fail" ? (
                            <Badge className="bg-red-100 text-red-700 border-red-200 text-[10px] px-1.5 py-0">
                              Fail
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground text-xs">—</span>
                          )}
                        </td>

                        {/* Actions */}
                        <td className="px-2 py-2 w-22">
                          <div className="flex items-center justify-end gap-0.5">
                            <Tooltip>
                              <TooltipTrigger
                                className="inline-flex items-center justify-center h-6 w-6 rounded-lg hover:bg-muted hover:text-foreground text-muted-foreground transition-colors cursor-pointer"
                                onClick={() => {
                                  initialCodeRef.current = jobPythonCode ?? "";
                                  setCodeEditable(false);
                                  setCodeDialogPython("");
                                  setCodeSasFile(bp.source_file);
                                  setCodeBlockId(bp.block_id);
                                }}
                                aria-label="View code"
                              >
                                <Code2 size={13} />
                              </TooltipTrigger>
                              <TooltipContent>View code</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                              <TooltipTrigger
                                className="inline-flex items-center justify-center h-6 w-6 rounded-lg hover:bg-muted hover:text-foreground text-muted-foreground transition-colors cursor-pointer disabled:opacity-50 disabled:pointer-events-none"
                                onClick={() => setRefineBlockId(bp.block_id)}
                                disabled={isAccepted}
                                aria-label={`Refine ${bp.block_id}`}
                              >
                                <Wrench size={13} />
                              </TooltipTrigger>
                              <TooltipContent>Refine with hint</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                              <TooltipTrigger
                                className={cn(
                                  "inline-flex items-center justify-center h-6 w-6 rounded-lg hover:bg-muted hover:text-foreground text-muted-foreground transition-colors cursor-pointer",
                                  humanEditedBlocks.has(bp.block_id) &&
                                    "border border-primary/40 text-primary bg-primary/5 hover:bg-primary/10",
                                )}
                                onClick={() => setHistoryBlockId(bp.block_id)}
                                aria-label={`History for ${bp.block_id}`}
                              >
                                <History size={13} />
                              </TooltipTrigger>
                              <TooltipContent>Revision history</TooltipContent>
                            </Tooltip>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {refineBlockId && (
        <BlockRefineDialog
          open={refineBlockId !== null}
          onOpenChange={(open) => {
            if (!open) setRefineBlockId(null);
          }}
          jobId={jobId}
          blockId={refineBlockId}
          isAccepted={isAccepted}
          onSuccess={() => {
            onBlockRefineSuccess?.();
          }}
        />
      )}

      {historyBlockId && (
        <BlockRevisionModal
          open={historyBlockId !== null}
          onOpenChange={(open) => {
            if (!open) setHistoryBlockId(null);
          }}
          jobId={jobId}
          blockId={historyBlockId}
          isAccepted={isAccepted}
        />
      )}

      <Dialog
        open={codeBlockId !== null}
        onOpenChange={(o) => {
          if (!o) setCodeBlockId(null);
        }}
      >
        <DialogContent className="max-w-6xl w-[95vw] h-[80vh] flex flex-col gap-0 p-0 overflow-hidden">
          {/* ── Title + toolbar ─────────────────────────────────────────────── */}
          <div className="flex items-center gap-3 px-5 py-3 border-b border-border shrink-0">
            {/* Block name */}
            <span className="text-sm font-semibold font-mono text-foreground truncate">
              {codeBlockId
                ? (() => {
                    const raw = codeBlockId.replace(/:\d+$/, "");
                    const slash = raw.lastIndexOf("/");
                    return slash >= 0 ? raw.slice(slash + 1) : raw;
                  })()
                : "Block Code"}
            </span>

            <div className="ml-auto flex items-center gap-1.5">
              {/* Theme toggle */}
              <button
                onClick={() => setCodeEditorDark((d) => !d)}
                aria-label={codeEditorDark ? "Switch to light theme" : "Switch to dark theme"}
                className="inline-flex items-center justify-center rounded p-1.5 text-muted-foreground border border-border hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
              >
                {codeEditorDark ? <Sun size={13} /> : <Moon size={13} />}
              </button>

              {/* Edit / Lock */}
              <button
                onClick={() => setCodeEditable((v) => !v)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium border border-border bg-background hover:bg-muted transition-colors cursor-pointer"
              >
                {codeEditable ? <><Lock size={12} /> Lock</> : <><Pencil size={12} /> Edit</>}
              </button>

              {/* Save */}
              {codeEditable && (
                <button
                  onClick={async () => {
                    if (!codeBlockId) return;
                    setCodeSaving(true);
                    try {
                      await saveBlockPython(jobId, codeBlockId, codeDialogPython);
                      setHumanEditedBlocks((prev) => new Set([...prev, codeBlockId]));
                      setCodeEditable(false);
                      void queryClient.invalidateQueries({
                        queryKey: ["block-revisions", jobId, codeBlockId],
                      });
                      setCodeBlockId(null);
                    } catch (err) {
                      toast.error(err instanceof Error ? err.message : "Could not save code.");
                    } finally {
                      setCodeSaving(false);
                    }
                  }}
                  disabled={codeSaving}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer transition-colors"
                >
                  {codeSaving ? "Saving…" : "Save"}
                </button>
              )}
            </div>
          </div>

          {/* ── Panel headers (identical height, separated by divider) ───────── */}
          <div className="grid grid-cols-2 border-b border-border shrink-0">
            {/* SAS header */}
            <div className="flex items-center gap-2 px-4 py-2 border-r border-border">
              <img src="/sas.svg" className="h-3.5 w-3.5 shrink-0" alt="" aria-hidden />
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                SAS — source
              </span>
            </div>
            {/* Python header */}
            <div className="flex items-center gap-2 px-4 py-2">
              <img src="/python.svg" className="h-3.5 w-3.5 shrink-0" alt="" aria-hidden />
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Python — generated
              </span>
              {codeEditable && (
                <span className="ml-1.5 text-[10px] text-amber-600 dark:text-amber-400 font-medium">
                  editing
                </span>
              )}
            </div>
          </div>

          {/* ── Editors ─────────────────────────────────────────────────────── */}
          <div className="grid grid-cols-2 flex-1 min-h-0">
            {/* SAS editor */}
            <div className="border-r border-border min-h-0 flex flex-col">
              {codeLoading ? (
                <div className="flex items-center justify-center flex-1 text-sm text-muted-foreground">
                  Loading…
                </div>
              ) : (
                <Editor
                  key={(codeBlockId ?? "none") + "-sas"}
                  height="100%"
                  language="sas"
                  beforeMount={registerSasLanguage}
                  value={sasCode}
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    fontSize: 13,
                    scrollBeyondLastLine: false,
                    padding: { top: 12 },
                  }}
                  theme={codeEditorDark ? "sas-dark" : "sas-light"}
                />
              )}
            </div>

            {/* Python editor */}
            <div className="min-h-0 flex flex-col">
              {codeLoading ? (
                <div className="flex items-center justify-center flex-1 text-sm text-muted-foreground">
                  Loading…
                </div>
              ) : (
                <Editor
                  key={codeBlockId ?? "none"}
                  height="100%"
                  language="python"
                  theme={codeEditorDark ? "vs-dark" : "vs"}
                  value={codeDialogPython}
                  onChange={(v) => setCodeDialogPython(v ?? "")}
                  options={{
                    readOnly: !codeEditable,
                    minimap: { enabled: false },
                    fontSize: 13,
                    scrollBeyondLastLine: false,
                    padding: { top: 12 },
                  }}
                />
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </TooltipProvider>
  );
}
