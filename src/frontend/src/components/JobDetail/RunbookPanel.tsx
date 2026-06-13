import { getJobRunbook } from "@/api/jobs";
import type { RunbookEntry, RunbookResponse } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

interface RunbookPanelProps {
  jobId: string;
}

const CRITICALITY_CLASSES: Record<string, string> = {
  critical: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  high: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
};

const STRATEGY_CLASSES: Record<string, string> = {
  translated: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  translated_with_review: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  manual: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

function criticalityClass(criticality: string): string {
  return (
    CRITICALITY_CLASSES[criticality] ??
    "bg-muted text-muted-foreground"
  );
}

function strategyClass(strategy: string): string {
  return (
    STRATEGY_CLASSES[strategy] ??
    "bg-muted text-muted-foreground"
  );
}

interface EntryCardProps {
  entry: RunbookEntry;
}

function EntryCard({ entry }: EntryCardProps) {
  const hasDatasets =
    entry.input_datasets.length > 0 || entry.output_datasets.length > 0;

  return (
    <Card className="border-border">
      <CardContent className="p-4 space-y-3">
        {/* Header row */}
        <div className="flex items-start justify-between gap-2 flex-wrap">
          <div className="min-w-0">
            <p className="font-mono text-xs text-foreground truncate max-w-[300px]">
              {entry.block_id}
            </p>
            <p className="font-mono text-xs text-muted-foreground">
              {entry.source_file}:{entry.start_line}
            </p>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap shrink-0">
            <Badge
              className={`text-xs font-medium capitalize ${criticalityClass(entry.criticality)}`}
              variant="outline"
            >
              {entry.criticality}
            </Badge>
            <Badge
              className={`text-xs font-medium capitalize ${strategyClass(entry.strategy)}`}
              variant="outline"
            >
              {entry.strategy.replace(/_/g, " ")}
            </Badge>
          </div>
        </div>

        {/* Datasets row */}
        {hasDatasets && (
          <div className="flex flex-wrap gap-3">
            {entry.input_datasets.length > 0 && (
              <div className="space-y-1">
                <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
                  Inputs
                </p>
                <div className="flex flex-wrap gap-1">
                  {entry.input_datasets.map((ds) => (
                    <span
                      key={ds}
                      className="font-mono text-[11px] bg-muted px-1.5 py-0.5 rounded border border-border"
                    >
                      {ds}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {entry.output_datasets.length > 0 && (
              <div className="space-y-1">
                <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
                  Outputs
                </p>
                <div className="flex flex-wrap gap-1">
                  {entry.output_datasets.map((ds) => (
                    <span
                      key={ds}
                      className="font-mono text-[11px] bg-muted px-1.5 py-0.5 rounded border border-border"
                    >
                      {ds}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* What it does */}
        <div className="space-y-1">
          <p className="text-xs font-semibold text-foreground">What it does</p>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {entry.description}
          </p>
        </div>

        {/* Why it's risky */}
        {entry.why_risky.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-semibold text-foreground">Why it&apos;s risky</p>
            <ul className="list-disc list-inside space-y-0.5">
              {entry.why_risky.map((reason, i) => (
                <li key={i} className="text-sm text-muted-foreground leading-relaxed">
                  {reason}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Suggested remediation */}
        {entry.remediation_outline.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-semibold text-foreground">Suggested remediation</p>
            <ol className="list-decimal list-inside space-y-0.5">
              {entry.remediation_outline.map((step, i) => (
                <li key={i} className="text-sm text-muted-foreground leading-relaxed">
                  {step}
                </li>
              ))}
            </ol>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface RunbookLoadedProps {
  data: RunbookResponse;
}

function RunbookLoaded({ data }: RunbookLoadedProps) {
  const handleCopy = async () => {
    await navigator.clipboard.writeText(data.markdown);
    toast.success("Copied to clipboard");
  };

  return (
    <div className="space-y-3 pt-2">
      {data.entries.map((entry) => (
        <EntryCard key={entry.block_id} entry={entry} />
      ))}
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

export function RunbookPanel({ jobId }: RunbookPanelProps) {
  const [collapsed, setCollapsed] = useState(true);

  const { data, isLoading, error } = useQuery<RunbookResponse>({
    queryKey: ["job", jobId, "runbook"],
    queryFn: () => getJobRunbook(jobId),
    enabled: !collapsed,
  });

  const entryCount = data?.total_entries ?? 0;

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
        <h2 className="text-sm font-semibold text-foreground">
          Remediation runbook
        </h2>
        {data && entryCount > 0 && (
          <Badge variant="secondary" className="text-xs font-mono">
            {entryCount} critical/high
          </Badge>
        )}
      </button>

      {!collapsed && (
        <div className="pl-1">
          {isLoading && (
            <div className="space-y-2">
              <Skeleton className="h-32 w-full rounded-md" />
              <Skeleton className="h-32 w-full rounded-md" />
            </div>
          )}
          {error && (
            <p className="text-sm text-destructive">
              Failed to load runbook:{" "}
              {error instanceof Error ? error.message : "Unknown error"}
            </p>
          )}
          {data && entryCount === 0 && (
            <p className="text-sm text-muted-foreground">
              No high-risk blocks — nothing to remediate.
            </p>
          )}
          {data && entryCount > 0 && <RunbookLoaded data={data} />}
        </div>
      )}
    </div>
  );
}
