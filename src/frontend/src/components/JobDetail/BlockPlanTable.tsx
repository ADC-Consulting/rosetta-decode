import type { BlockOverride, BlockPlan, TrustReportBlock } from "@/api/types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import BlockRefineDialog from "./BlockRefineDialog";
import BlockRevisionDrawer from "./BlockRevisionDrawer";
import NoteDialog from "./NoteDialog";
import { RISK_CELL, RISK_LABELS, STRATEGY_LABELS } from "./constants";

const CONFIDENCE_ORDER: Record<string, number> = {
  low: 0,
  medium: 1,
  high: 2,
  unknown: 3,
};

const CONFIDENCE_BADGE: Record<string, string> = {
  high: "bg-green-100 text-green-700 border border-green-200",
  medium: "bg-amber-100 text-amber-700 border border-amber-200",
  low: "bg-red-100 text-red-700 border border-red-200",
  unknown: "bg-muted text-muted-foreground border border-border",
};

interface BlockPlanTableProps {
  blockPlans: BlockPlan[];
  isProposed: boolean;
  overrides: Record<string, BlockOverride>;
  savingBlockId: string | null;
  onStrategyChange: (blockId: string, value: string) => void;
  onRiskChange: (blockId: string, value: string) => void;
  onNoteChange: (blockId: string, value: string) => void;
  trustBlocks?: Record<string, TrustReportBlock>;
  jobId: string;
  isAccepted?: boolean;
  blockNotes?: Record<string, string>;
}

export default function BlockPlanTable({
  blockPlans,
  isProposed,
  overrides,
  savingBlockId,
  onStrategyChange,
  onRiskChange,
  onNoteChange,
  trustBlocks = {},
  jobId,
  isAccepted,
  blockNotes,
}: BlockPlanTableProps): React.ReactElement {
  const [refineBlockId, setRefineBlockId] = useState<string | null>(null);
  const [historyBlockId, setHistoryBlockId] = useState<string | null>(null);

  const sorted = [...blockPlans].sort((a, b) => {
    const ta = trustBlocks[a.block_id];
    const tb = trustBlocks[b.block_id];
    const attA = ta?.needs_attention ? 0 : 1;
    const attB = tb?.needs_attention ? 0 : 1;
    if (attA !== attB) return attA - attB;
    const confA = CONFIDENCE_ORDER[ta?.self_confidence ?? "unknown"] ?? 3;
    const confB = CONFIDENCE_ORDER[tb?.self_confidence ?? "unknown"] ?? 3;
    return confA - confB;
  });

  const hasTrustData = Object.keys(trustBlocks).length > 0;

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-muted/50 text-left">
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Block
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground text-right w-12">
              Line
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Type
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground w-44">
              Strategy
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground w-20">
              Risk
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground w-24">
              Confidence
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground w-16">
              Recon
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Effort
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Rationale
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground text-center w-16">
              Note
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground text-center w-28">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {sorted.map((bp) => {
            const trust = trustBlocks[bp.block_id];
            const needsAttention = trust?.needs_attention ?? false;
            return (
            <tr
              key={bp.block_id}
              className={`hover:bg-muted/30 ${needsAttention ? "border-l-2 border-l-amber-400" : ""}`}
            >
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
              <td className="px-3 py-2 font-mono text-xs text-muted-foreground text-right tabular-nums w-12">
                {bp.start_line ?? "—"}
              </td>
              <td className="px-3 py-2 font-mono text-xs">{bp.block_type}</td>
              <td className="px-3 py-2 text-xs">
                {isProposed ? (
                  <Select
                    value={overrides[bp.block_id]?.strategy ?? bp.strategy}
                    onValueChange={(v) => v && onStrategyChange(bp.block_id, v)}
                  >
                    <SelectTrigger
                      size="sm"
                      className="text-xs h-6 w-40 cursor-pointer"
                    >
                      <SelectValue>
                        {(v: string | null) =>
                          v ? (STRATEGY_LABELS[v] ?? v) : ""
                        }
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(STRATEGY_LABELS).map(([value, label]) => (
                        <SelectItem
                          key={value}
                          value={value}
                          className="text-xs cursor-pointer"
                        >
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <span>
                    {STRATEGY_LABELS[
                      overrides[bp.block_id]?.strategy ?? bp.strategy
                    ] ??
                      overrides[bp.block_id]?.strategy ??
                      bp.strategy}
                  </span>
                )}
              </td>
              <td className="px-3 py-2 text-xs">
                {isProposed ? (
                  <Select
                    value={overrides[bp.block_id]?.risk ?? bp.risk}
                    onValueChange={(v) => v && onRiskChange(bp.block_id, v)}
                  >
                    <SelectTrigger
                      size="sm"
                      className={`text-xs h-6 w-20 font-semibold cursor-pointer ${RISK_CELL[(overrides[bp.block_id]?.risk ?? bp.risk) as "low" | "medium" | "high"]}`}
                    >
                      <SelectValue>
                        {(v: string | null) =>
                          v
                            ? (RISK_LABELS[v as "low" | "medium" | "high"] ?? v)
                            : ""
                        }
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {(["low", "medium", "high"] as const).map((r) => (
                        <SelectItem
                          key={r}
                          value={r}
                          className={`text-xs font-semibold cursor-pointer ${RISK_CELL[r]}`}
                        >
                          {RISK_LABELS[r]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <span
                    className={`font-semibold ${RISK_CELL[(overrides[bp.block_id]?.risk ?? bp.risk) as "low" | "medium" | "high"]}`}
                  >
                    {
                      RISK_LABELS[
                        (overrides[bp.block_id]?.risk ?? bp.risk) as
                          | "low"
                          | "medium"
                          | "high"
                      ]
                    }
                  </span>
                )}
              </td>
              <td className="px-3 py-2 text-xs w-24">
                {hasTrustData ? (
                  trust ? (
                    <span
                      className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium capitalize ${CONFIDENCE_BADGE[trust.self_confidence] ?? CONFIDENCE_BADGE["unknown"]}`}
                    >
                      {trust.self_confidence}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
              <td className="px-3 py-2 text-xs w-16">
                {hasTrustData ? (
                  trust?.reconciliation_status === "pass" ? (
                    <span className="text-green-600 font-bold" aria-label="Pass">&#10003;</span>
                  ) : trust?.reconciliation_status === "fail" ? (
                    <span className="text-red-600 font-bold" aria-label="Fail">&#10007;</span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
              <td className="px-3 py-2 text-xs capitalize">
                {bp.estimated_effort}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {bp.rationale}
              </td>
              <td className="px-3 py-2 text-xs text-center w-16">
                {isProposed ? (
                  <NoteDialog
                    blockId={bp.block_id}
                    currentNote={overrides[bp.block_id]?.note ?? ""}
                    isSaving={savingBlockId === bp.block_id}
                    onSave={onNoteChange}
                  />
                ) : (
                  <span className="text-muted-foreground">
                    {overrides[bp.block_id]?.note ?? ""}
                  </span>
                )}
              </td>
              <td className="px-3 py-2 text-xs text-center w-28">
                <div className="flex items-center justify-center gap-1">
                  <button
                    onClick={() => setRefineBlockId(bp.block_id)}
                    disabled={isAccepted}
                    className={
                      "rounded px-1.5 py-0.5 text-[11px] font-medium transition-colors cursor-pointer " +
                      (isAccepted
                        ? "text-muted-foreground cursor-not-allowed opacity-50"
                        : "text-primary hover:bg-primary/10")
                    }
                    aria-label={`Refine block ${bp.block_id}`}
                  >
                    Refine
                  </button>
                  <button
                    onClick={() => setHistoryBlockId(bp.block_id)}
                    className="rounded px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                    aria-label={`View revision history for block ${bp.block_id}`}
                  >
                    History
                  </button>
                </div>
              </td>
            </tr>
          );
          })}
        </tbody>
      </table>

      {refineBlockId && (
        <BlockRefineDialog
          open={refineBlockId !== null}
          onOpenChange={(open) => { if (!open) setRefineBlockId(null); }}
          jobId={jobId}
          blockId={refineBlockId}
          blockNote={blockNotes?.[refineBlockId] ?? overrides[refineBlockId]?.note ?? null}
          isAccepted={isAccepted}
        />
      )}

      {historyBlockId && (
        <BlockRevisionDrawer
          open={historyBlockId !== null}
          onOpenChange={(open) => { if (!open) setHistoryBlockId(null); }}
          jobId={jobId}
          blockId={historyBlockId}
          isAccepted={isAccepted}
        />
      )}
    </div>
  );
}

