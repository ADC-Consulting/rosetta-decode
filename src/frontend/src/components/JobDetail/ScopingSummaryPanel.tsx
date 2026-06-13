import { getJobScopingSummary } from "@/api/jobs";
import type { PhaseTokens, ScopingSummaryResponse } from "@/api/types";
import React from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

interface ScopingSummaryPanelProps {
  jobId: string;
}

const PHASE_NAMES: Record<string, string> = {
  parse_analysis: "Parse & Analysis",
  migration_planning: "Migration Planning",
  translation: "Translation",
  assembly_recon: "Assembly & Reconciliation",
  enrichment: "Enrichment",
};

function phaseDisplayName(key: string): string {
  return PHASE_NAMES[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const BLOCK_NAMES: Record<string, string> = {
  data_step: "Data step",
  proc_sql: "PROC SQL",
  proc_means: "PROC MEANS",
  proc_freq: "PROC FREQ",
  proc_sort: "PROC SORT",
  proc_transpose: "PROC TRANSPOSE",
  macro: "Macro",
  generic_proc: "Generic PROC",
};

function blockDisplayName(key: string): string {
  return BLOCK_NAMES[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

interface PhaseTokenRowProps {
  phaseKey: string;
  tokens: PhaseTokens;
  phaseCost: number | null;
}

function PhaseTokenRow({ phaseKey, tokens, phaseCost }: PhaseTokenRowProps) {
  return (
    <tr className="border-t border-border">
      <td className="py-1 pr-3 text-xs text-muted-foreground">{phaseDisplayName(phaseKey)}</td>
      <td className="py-1 pr-3 text-xs tabular-nums text-right">{tokens.input_tokens.toLocaleString()}</td>
      <td className="py-1 pr-3 text-xs tabular-nums text-right">{tokens.output_tokens.toLocaleString()}</td>
      {phaseCost !== null && (
        <td className="py-1 text-xs tabular-nums text-right">${phaseCost.toFixed(4)}</td>
      )}
    </tr>
  );
}

interface BlockSubRowProps {
  blockKey: string;
  tokens: PhaseTokens;
  prices: { input_usd_per_mtok: number; output_usd_per_mtok: number } | null;
  showCost: boolean;
}

function BlockSubRow({ blockKey, tokens, prices, showCost }: BlockSubRowProps) {
  const cost =
    showCost && prices !== null
      ? (tokens.input_tokens * prices.input_usd_per_mtok +
          tokens.output_tokens * prices.output_usd_per_mtok) /
        1_000_000
      : null;

  return (
    <tr className="border-t border-border/50">
      <td className="py-0.5 pr-3 text-xs text-muted-foreground pl-6">
        ↳ {blockDisplayName(blockKey)}
      </td>
      <td className="py-0.5 pr-3 text-xs tabular-nums text-right text-muted-foreground">
        {tokens.input_tokens.toLocaleString()}
      </td>
      <td className="py-0.5 pr-3 text-xs tabular-nums text-right text-muted-foreground">
        {tokens.output_tokens.toLocaleString()}
      </td>
      {showCost && (
        <td className="py-0.5 text-xs tabular-nums text-right text-muted-foreground">
          {cost !== null ? `$${cost.toFixed(4)}` : "—"}
        </td>
      )}
    </tr>
  );
}

function ScopingSummaryLoaded({ data }: { data: ScopingSummaryResponse }) {
  const handleCopy = async () => {
    await navigator.clipboard.writeText(data.markdown);
    toast.success("Copied to clipboard");
  };

  const bom = data.bom;

  return (
    <div className="space-y-4 pt-2">
      {/* Model name */}
      {data.llm_model && (
        <p className="text-xs text-muted-foreground -mt-1">Model: {data.llm_model}</p>
      )}

      {/* BOM stat grid */}
      <div>
        <p className="text-xs font-semibold text-foreground mb-1.5">Bill of materials</p>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          {(
            [
              ["Total blocks", bom.total_blocks],
              ["DATA steps", bom.data_steps],
              ["PROCs", bom.procs],
              ["Macros", bom.macros],
              ["Untranslatable", bom.untranslatable],
              ["Human review", bom.human_review_required],
            ] as [string, number][]
          ).map(([label, value]) => (
            <div
              key={label}
              className="rounded-md border border-border bg-muted/30 px-3 py-2 text-center"
            >
              <p className="text-base font-semibold tabular-nums">{value}</p>
              <p className="text-[11px] text-muted-foreground leading-tight">{label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Risk distribution */}
      {Object.keys(bom.risk_buckets).length > 0 && (
        <div>
          <p className="text-xs font-semibold text-foreground mb-1.5">Risk distribution</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(bom.risk_buckets).map(([risk, count]) => (
              <span
                key={risk}
                className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-0.5 text-xs"
              >
                <span className="font-medium capitalize">{risk}</span>
                <span className="text-muted-foreground">{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* LLM usage */}
      {data.token_usage && (
        <div>
          <p className="text-xs font-semibold text-foreground mb-1.5">LLM token usage</p>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="pb-1 pr-3 text-left text-xs font-medium text-muted-foreground">
                    Phase
                  </th>
                  <th className="pb-1 pr-3 text-right text-xs font-medium text-muted-foreground">
                    Input tokens
                  </th>
                  <th
                    className={
                      data.cost
                        ? "pb-1 pr-3 text-right text-xs font-medium text-muted-foreground"
                        : "pb-1 text-right text-xs font-medium text-muted-foreground"
                    }
                  >
                    Output tokens
                  </th>
                  {data.cost && (
                    <th className="pb-1 text-right text-xs font-medium text-muted-foreground">
                      Est. cost (USD)
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.token_usage.phases).filter(([, tokens]) => tokens.input_tokens > 0 || tokens.output_tokens > 0).map(([phase, tokens]) => (
                  <React.Fragment key={phase}>
                    <PhaseTokenRow
                      phaseKey={phase}
                      tokens={tokens}
                      phaseCost={data.cost ? (data.cost.per_phase_usd[phase] ?? 0) : null}
                    />
                    {phase === "translation" &&
                      Object.keys(data.token_usage!.translation_by_block ?? {}).length > 0 &&
                      Object.entries(data.token_usage!.translation_by_block ?? {}).map(
                        ([blockKey, blockTokens]) => (
                          <BlockSubRow
                            key={`block-${blockKey}`}
                            blockKey={blockKey}
                            tokens={blockTokens}
                            prices={data.cost ? data.cost.prices : null}
                            showCost={data.cost !== null}
                          />
                        ),
                      )}
                  </React.Fragment>
                ))}
                <tr className="border-t-2 border-border">
                  <td className="py-1 pr-3 text-xs font-semibold">Total</td>
                  <td className="py-1 pr-3 text-xs tabular-nums text-right font-semibold">
                    {data.token_usage.total.input_tokens.toLocaleString()}
                  </td>
                  <td
                    className={
                      data.cost
                        ? "py-1 pr-3 text-xs tabular-nums text-right font-semibold"
                        : "py-1 text-xs tabular-nums text-right font-semibold"
                    }
                  >
                    {data.token_usage.total.output_tokens.toLocaleString()}
                  </td>
                  {data.cost && (
                    <td className="py-1 text-xs tabular-nums text-right font-semibold">
                      ${data.cost.total_usd.toFixed(4)}
                    </td>
                  )}
                </tr>
              </tbody>
            </table>
          </div>
          {data.cost && (
            <p className="text-[11px] text-muted-foreground mt-1.5">
              Costs are approximate. {data.cost.price_source} pricing ($
              {data.cost.prices.input_usd_per_mtok}/M in, $
              {data.cost.prices.output_usd_per_mtok}/M out).
            </p>
          )}
        </div>
      )}

      {/* Copy button placed at bottom for convenience */}
      <div className="flex justify-end pt-1">
        <Button
          variant="outline"
          size="sm"
          onClick={handleCopy}
          className="gap-1.5 text-xs"
        >
          <Copy size={12} />
          Copy as Markdown
        </Button>
      </div>
    </div>
  );
}

export function ScopingSummaryPanel({ jobId }: ScopingSummaryPanelProps) {
  const [collapsed, setCollapsed] = useState(true);

  const { data, isLoading, error } = useQuery<ScopingSummaryResponse>({
    queryKey: ["job", jobId, "scoping"],
    queryFn: () => getJobScopingSummary(jobId),
    enabled: !collapsed,
  });

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
        aria-expanded={!collapsed}
      >
        {collapsed ? (
          <ChevronRight size={14} className="text-muted-foreground shrink-0" />
        ) : (
          <ChevronDown size={14} className="text-muted-foreground shrink-0" />
        )}
        <h2 className="text-sm font-semibold text-foreground">Scoping summary</h2>
      </button>

      {!collapsed && (
        <div className="pl-1">
          {isLoading && (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full rounded-md" />
              <Skeleton className="h-8 w-full rounded-md" />
            </div>
          )}
          {error && (
            <p className="text-sm text-destructive">
              Failed to load scoping summary:{" "}
              {error instanceof Error ? error.message : "Unknown error"}
            </p>
          )}
          {data && <ScopingSummaryLoaded data={data} />}
        </div>
      )}
    </div>
  );
}
