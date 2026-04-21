import type { BlockOverride, BlockPlan } from "@/api/types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import NoteDialog from "./NoteDialog";
import { RISK_CELL, RISK_LABELS, STRATEGY_LABELS } from "./constants";

export default function BlockPlanTable({
  blockPlans,
  isProposed,
  overrides,
  savingBlockId,
  onStrategyChange,
  onRiskChange,
  onNoteChange,
}: {
  blockPlans: BlockPlan[];
  isProposed: boolean;
  overrides: Record<string, BlockOverride>;
  savingBlockId: string | null;
  onStrategyChange: (blockId: string, value: string) => void;
  onRiskChange: (blockId: string, value: string) => void;
  onNoteChange: (blockId: string, value: string) => void;
}): React.ReactElement {
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
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Effort
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Rationale
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground text-center w-16">
              Note
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {blockPlans.map((bp) => (
            <tr key={bp.block_id} className="hover:bg-muted/30">
              <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                {bp.block_id.replace(/:\d+$/, "")}
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

