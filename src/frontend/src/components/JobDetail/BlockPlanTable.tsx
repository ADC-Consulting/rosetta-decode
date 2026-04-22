import type { BlockPlan, TrustReportBlock } from "@/api/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AlertTriangle, Clock, Info, Wrench } from "lucide-react";
import React, { useState } from "react";
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
  translate_best_effort:
    "text-orange-700 bg-orange-50 border border-orange-200",
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

const CONFIDENCE_BAND_COLOR: Record<string, string> = {
  high: "text-green-700 bg-green-50 border border-green-200",
  medium: "text-amber-700 bg-amber-50 border border-amber-200",
  low: "text-red-700 bg-red-50 border border-red-200",
  "very low": "text-red-900 bg-red-100 border border-red-300",
  unknown: "text-muted-foreground bg-muted border border-border",
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
            <ul className="space-y-1 text-muted-foreground">
              <li>
                <span className="font-medium text-green-700">Low</span> —
                Routine transformations, clear translation path
              </li>
              <li>
                <span className="font-medium text-amber-700">Medium</span> —
                Complex joins, BY-group logic, multi-output steps
              </li>
              <li>
                <span className="font-medium text-red-700">High</span> — Dynamic
                code, CALL SYMPUT, nested macros, solver calls
              </li>
            </ul>
          </div>
          <div>
            <p className="font-semibold mb-1">Confidence score</p>
            <ul className="space-y-1 text-muted-foreground">
              <li>
                <span className="font-medium">0.85–1.0</span> = High — LLM is
                certain
              </li>
              <li>
                <span className="font-medium">0.65–0.84</span> = Medium
              </li>
              <li>
                <span className="font-medium">0.40–0.64</span> = Low
              </li>
              <li>
                <span className="font-medium">&lt;0.40</span> = Very Low
              </li>
            </ul>
          </div>
          <div>
            <p className="font-semibold mb-1">Strategies</p>
            <ul className="space-y-1 text-muted-foreground">
              <li>
                <span className="font-medium text-blue-700">translate</span> —
                Auto-translated
              </li>
              <li>
                <span className="font-medium text-amber-700">
                  translate_with_review
                </span>{" "}
                — Translated but needs human check
              </li>
              <li>
                <span className="font-medium text-orange-700">
                  translate_best_effort
                </span>{" "}
                — Partial translation, may be incomplete
              </li>
              <li>
                <span className="font-medium text-red-700">manual</span> —
                Cannot be auto-translated, needs human
              </li>
              <li>
                <span className="font-medium text-muted-foreground">skip</span>{" "}
                — Intentionally excluded
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
}: BlockPlanTableProps): React.ReactElement {
  const [refineBlockId, setRefineBlockId] = useState<string | null>(null);
  const [historyBlockId, setHistoryBlockId] = useState<string | null>(null);
  const [groupBy, setGroupBy] = useState<GroupBy>(() => {
    const files = new Set(blockPlans.map((b) => b.source_file));
    return files.size > 1 ? "file" : "none";
  });
  const [activeStrategies, setActiveStrategies] = useState<Set<string>>(
    new Set(),
  );
  const [glossaryOpen, setGlossaryOpen] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    new Set(),
  );

  // unique strategies in the data
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
      <div className="flex items-center gap-3 flex-wrap mb-2">
        {/* Group by */}
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Group by</span>
          <Select
            value={groupBy}
            onValueChange={(v) => setGroupBy(v as GroupBy)}
          >
            <SelectTrigger
              size="sm"
              className="h-7 text-xs w-36 cursor-pointer"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none" className="text-xs cursor-pointer">
                No grouping
              </SelectItem>
              <SelectItem value="file" className="text-xs cursor-pointer">
                By file
              </SelectItem>
              <SelectItem value="folder" className="text-xs cursor-pointer">
                By folder
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Strategy filter chips */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {uniqueStrategies.map((s) => (
            <button
              key={s}
              onClick={() => toggleStrategy(s)}
              className={
                "px-2 py-0.5 rounded-full text-xs font-medium border transition-colors cursor-pointer " +
                (activeStrategies.has(s)
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-background text-muted-foreground border-border hover:border-foreground")
              }
            >
              {STRATEGY_LABELS[s] ?? s}
            </button>
          ))}
        </div>

        {/* Glossary info button */}
        <button
          onClick={() => setGlossaryOpen(true)}
          className="ml-auto p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
          aria-label="Open glossary"
        >
          <Info size={14} />
        </button>
      </div>

      <GlossaryDialog open={glossaryOpen} onOpenChange={setGlossaryOpen} />

      {/* Table */}
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted/50 text-left">
              <th className="px-3 py-2 font-medium text-muted-foreground">
                Block
              </th>
              <th className="px-3 py-2 font-medium text-muted-foreground w-12">
                Line
              </th>
              <th className="px-3 py-2 font-medium text-muted-foreground">
                Type
              </th>
              <th className="px-3 py-2 font-medium text-muted-foreground w-40">
                Strategy
              </th>
              <th className="px-3 py-2 font-medium text-muted-foreground w-16">
                Risk
              </th>
              <th className="px-3 py-2 font-medium text-muted-foreground w-28">
                Confidence
              </th>
              <th className="px-3 py-2 font-medium text-muted-foreground">
                Rationale
              </th>
              <th className="px-3 py-2 font-medium text-muted-foreground w-14 text-center">
                Recon
              </th>
              <th className="px-3 py-2 font-medium text-muted-foreground w-14 text-center">
                Refine
              </th>
              <th className="px-3 py-2 font-medium text-muted-foreground w-14 text-center">
                History
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {groups.map(({ key, items }) => (
              <React.Fragment key={key}>
                {/* Group header */}
                {groupBy !== "none" && (
                  <tr
                    key={`group-${key}`}
                    className="bg-muted/30 cursor-pointer hover:bg-muted/50"
                    onClick={() => toggleGroup(key)}
                  >
                    <td colSpan={10} className="px-3 py-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-foreground font-mono">
                          {key}
                        </span>
                        <span className="text-xs text-muted-foreground bg-muted border border-border rounded-full px-1.5 py-0.5">
                          {items.length}
                        </span>
                        <span className="ml-auto text-muted-foreground text-xs">
                          {collapsedGroups.has(key) ? "▸" : "▾"}
                        </span>
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
                    const bandKey =
                      bp.confidence_band?.toLowerCase() ?? "unknown";
                    const bandCls =
                      CONFIDENCE_BAND_COLOR[bandKey] ??
                      CONFIDENCE_BAND_COLOR["unknown"];

                    return (
                      <tr
                        key={bp.block_id}
                        className={`hover:bg-muted/30 ${needsAttention ? "border-l-2 border-l-amber-400" : ""}`}
                      >
                        {/* Block */}
                        <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            {needsAttention && (
                              <AlertTriangle
                                className="text-amber-500 shrink-0"
                                size={12}
                                aria-label="Needs attention"
                              />
                            )}
                            {bp.block_id.replace(/:\d+$/, "")}
                          </span>
                        </td>

                        {/* Line */}
                        <td className="px-3 py-2 font-mono text-xs text-muted-foreground w-12">
                          {bp.start_line ?? "—"}
                        </td>

                        {/* Type */}
                        <td className="px-3 py-2 font-mono text-xs">
                          {bp.block_type}
                        </td>

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
                          <span
                            className={`font-semibold ${RISK_COLOR[bp.risk] ?? ""}`}
                          >
                            {RISK_LABELS[bp.risk] ?? bp.risk}
                          </span>
                        </td>

                        {/* Confidence */}
                        <td className="px-3 py-2 text-xs w-28">
                          <div className="flex items-center gap-1">
                            <span className="tabular-nums">{confPct}</span>
                            {bp.confidence_band && (
                              <span
                                className={`inline-block px-1 py-0.5 rounded text-[10px] font-medium capitalize ${bandCls}`}
                              >
                                {bp.confidence_band}
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Rationale */}
                        <td className="px-3 py-2 text-xs text-muted-foreground max-w-xs text-left">
                          <span className="line-clamp-2">{bp.rationale}</span>
                        </td>

                        {/* Recon */}
                        <td className="px-3 py-2 text-xs text-center w-14">
                          {trust?.reconciliation_status === "pass" ? (
                            <span
                              className="text-green-600 font-bold"
                              aria-label="Pass"
                            >
                              ✓
                            </span>
                          ) : trust?.reconciliation_status === "fail" ? (
                            <span
                              className="text-red-600 font-bold"
                              aria-label="Fail"
                            >
                              ✗
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>

                        {/* Refine */}
                        <td className="px-3 py-2 text-center w-14">
                          <button
                            onClick={() => setRefineBlockId(bp.block_id)}
                            disabled={isAccepted}
                            aria-label={`Refine block ${bp.block_id}`}
                            className={
                              "inline-flex items-center justify-center rounded p-1 transition-colors cursor-pointer " +
                              (isAccepted
                                ? "opacity-40 cursor-not-allowed text-muted-foreground"
                                : "text-muted-foreground hover:text-foreground hover:bg-muted")
                            }
                          >
                            <Wrench size={14} />
                          </button>
                        </td>

                        {/* History */}
                        <td className="px-3 py-2 text-center w-14">
                          <button
                            onClick={() => setHistoryBlockId(bp.block_id)}
                            aria-label={`View history for block ${bp.block_id}`}
                            className="inline-flex items-center justify-center rounded p-1 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                          >
                            <Clock size={14} />
                          </button>
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
    </TooltipProvider>
  );
}
