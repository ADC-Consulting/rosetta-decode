import { getJobAssessment } from "@/api/jobs";
import type {
  AssessmentReportResponse,
  BlockBreakdown,
  ComplexityTier,
  DataAssetInventory,
  EffortEstimate,
  FileInventoryItem,
  RiskFlag,
  RiskSeverity,
  ScopingReport,
  TranslationCategory,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { downloadMarkdown } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { Copy, Download } from "lucide-react";
import { toast } from "sonner";

interface AssessmentReportPanelProps {
  jobId: string;
}

// ── Color-coded badge maps (consistent across all sections) ───────────────────

const TIER_CLASSES: Record<ComplexityTier, string> = {
  simple: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  moderate:
    "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  complex: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const CATEGORY_CLASSES: Record<TranslationCategory, string> = {
  auto_translatable:
    "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  needs_review:
    "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  manual:
    "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
  untranslatable:
    "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const SEVERITY_CLASSES: Record<RiskSeverity, string> = {
  low: "bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-200",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  high: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const CATEGORY_LABELS: Record<TranslationCategory, string> = {
  auto_translatable: "Auto-translatable",
  needs_review: "Needs review",
  manual: "Manual",
  untranslatable: "Untranslatable",
};

function humanizeType(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\bproc\b/i, "PROC")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function tierClass(tier: ComplexityTier): string {
  return TIER_CLASSES[tier] ?? "bg-muted text-muted-foreground";
}

function categoryClass(category: TranslationCategory): string {
  return CATEGORY_CLASSES[category] ?? "bg-muted text-muted-foreground";
}

function severityClass(severity: RiskSeverity): string {
  return SEVERITY_CLASSES[severity] ?? "bg-muted text-muted-foreground";
}

// ── Shared building blocks ────────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-sm font-semibold text-foreground mb-2">{children}</h3>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-center">
      <p className="text-lg font-semibold tabular-nums">{value}</p>
      <p className="text-[11px] text-muted-foreground leading-tight">{label}</p>
    </div>
  );
}

// ── Sections ──────────────────────────────────────────────────────────────────

function HeaderStats({ report }: { report: ScopingReport }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <StatCard label="Files" value={report.total_files} />
      <StatCard label="Lines" value={report.total_lines.toLocaleString()} />
      <StatCard label="Blocks" value={report.total_blocks} />
    </div>
  );
}

function FileInventorySection({ items }: { items: FileInventoryItem[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <SectionTitle>File inventory</SectionTitle>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border bg-muted/40">
              <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                File
              </th>
              <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                Lines
              </th>
              <th className="px-3 py-2 text-right font-medium text-muted-foreground">
                Blocks
              </th>
              <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                Complexity
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={item.source_file}
                className="border-b border-border/50 last:border-b-0"
              >
                <td className="px-3 py-2 font-mono text-foreground truncate max-w-[260px]">
                  {item.source_file}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                  {item.line_count.toLocaleString()}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                  {item.block_count}
                </td>
                <td className="px-3 py-2">
                  <Badge
                    variant="outline"
                    className={`text-xs font-medium capitalize ${tierClass(item.complexity_tier)}`}
                  >
                    {item.complexity_tier}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BlockBreakdownSection({ breakdown }: { breakdown: BlockBreakdown }) {
  const rows = Object.entries(breakdown.counts_by_type).sort(
    (a, b) => b[1] - a[1],
  );
  if (rows.length === 0) return null;
  return (
    <div>
      <SectionTitle>Block breakdown</SectionTitle>
      <div className="space-y-1.5">
        {rows.map(([type, count]) => {
          const category = breakdown.category_by_type[type];
          return (
            <div
              key={type}
              className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-1.5"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="font-mono text-xs text-foreground truncate">
                  {humanizeType(type)}
                </span>
                <span className="text-xs tabular-nums text-muted-foreground">
                  ×{count}
                </span>
              </div>
              {category && (
                <Badge
                  variant="outline"
                  className={`text-xs font-medium ${categoryClass(category)}`}
                >
                  {CATEGORY_LABELS[category] ?? category}
                </Badge>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RiskFlagsSection({ flags }: { flags: RiskFlag[] }) {
  return (
    <div>
      <SectionTitle>Risk flags</SectionTitle>
      {flags.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No risk flags detected.
        </p>
      ) : (
        <div className="space-y-2">
          {flags.map((flag, i) => (
            <Card key={`${flag.kind}-${i}`} className="border-border">
              <CardContent className="p-3 space-y-1.5">
                <div className="flex items-start justify-between gap-2 flex-wrap">
                  <span className="font-mono text-xs text-muted-foreground">
                    {humanizeType(flag.kind)}
                  </span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Badge
                      variant="outline"
                      className={`text-xs font-medium capitalize ${severityClass(flag.severity)}`}
                    >
                      {flag.severity}
                    </Badge>
                    <Badge variant="secondary" className="text-xs tabular-nums">
                      {flag.count}
                    </Badge>
                  </div>
                </div>
                <p className="text-sm text-foreground leading-relaxed">
                  {flag.message}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function ChipList({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-1">
      <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
        {label}
      </p>
      <div className="flex flex-wrap gap-1">
        {items.map((item) => (
          <span
            key={item}
            className="font-mono text-[11px] bg-muted px-1.5 py-0.5 rounded border border-border"
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function DataAssetsSection({ assets }: { assets: DataAssetInventory }) {
  const hasAny =
    assets.libnames.length > 0 ||
    assets.input_datasets.length > 0 ||
    assets.output_datasets.length > 0 ||
    assets.external_file_paths.length > 0;
  return (
    <div>
      <SectionTitle>Data assets</SectionTitle>
      {!hasAny ? (
        <p className="text-sm text-muted-foreground">
          No data assets referenced.
        </p>
      ) : (
        <div className="space-y-3">
          {assets.libnames.length > 0 && (
            <div className="space-y-1">
              <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
                Libnames
              </p>
              <div className="flex flex-wrap gap-1.5">
                {assets.libnames.map((lib) => (
                  <span
                    key={lib.libref}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2.5 py-0.5 text-xs"
                  >
                    <span className="font-mono font-medium text-foreground">
                      {lib.libref}
                    </span>
                    <span className="text-muted-foreground">{lib.engine}</span>
                    {lib.path && (
                      <span className="font-mono text-[10px] text-muted-foreground truncate max-w-[180px]">
                        {lib.path}
                      </span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}
          <ChipList label="Input datasets" items={assets.input_datasets} />
          <ChipList label="Output datasets" items={assets.output_datasets} />
          <ChipList
            label="External file paths"
            items={assets.external_file_paths}
          />
        </div>
      )}
    </div>
  );
}

function EffortEstimateSection({ estimate }: { estimate: EffortEstimate }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <SectionTitle>Effort estimate</SectionTitle>
        {estimate.provisional && (
          <Badge
            variant="outline"
            className="text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 -mt-2"
          >
            Provisional
          </Badge>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2">
        <StatCard label="Low (days)" value={estimate.low_days} />
        <StatCard label="Mid (days)" value={estimate.mid_days} />
        <StatCard label="High (days)" value={estimate.high_days} />
      </div>
      <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">
        {estimate.basis}
      </p>
    </div>
  );
}

function NotesSection({ notes }: { notes: string[] }) {
  if (notes.length === 0) return null;
  return (
    <div>
      <SectionTitle>Notes</SectionTitle>
      <ul className="list-disc list-inside space-y-0.5">
        {notes.map((note, i) => (
          <li
            key={i}
            className="text-sm text-muted-foreground leading-relaxed"
          >
            {note}
          </li>
        ))}
      </ul>
    </div>
  );
}

function AssessmentReportLoaded({ data }: { data: AssessmentReportResponse }) {
  const { report } = data;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(data.markdown);
    toast.success("Copied to clipboard");
  };

  const handleDownload = () => {
    downloadMarkdown(data.markdown, `scoping-${data.job_id}.md`);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold text-foreground">
            Scoping assessment
          </h2>
          <p className="text-sm text-muted-foreground">{data.job_name}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopy}
            className="gap-1.5 text-xs"
          >
            <Copy size={12} />
            Copy
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDownload}
            className="gap-1.5 text-xs"
          >
            <Download size={12} />
            Download Markdown
          </Button>
        </div>
      </div>

      <HeaderStats report={report} />
      <FileInventorySection items={report.file_inventory} />
      <BlockBreakdownSection breakdown={report.block_breakdown} />
      <RiskFlagsSection flags={report.risk_flags} />
      <DataAssetsSection assets={report.data_assets} />
      <EffortEstimateSection estimate={report.effort_estimate} />
      <NotesSection notes={report.notes} />
    </div>
  );
}

export function AssessmentReportPanel({ jobId }: AssessmentReportPanelProps) {
  const { data, isLoading, error } = useQuery<AssessmentReportResponse>({
    queryKey: ["job", jobId, "assessment"],
    queryFn: () => getJobAssessment(jobId),
    enabled: !!jobId,
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-20 w-full rounded-md" />
        <Skeleton className="h-40 w-full rounded-md" />
        <Skeleton className="h-40 w-full rounded-md" />
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-sm text-destructive">
        Failed to load assessment report:{" "}
        {error instanceof Error ? error.message : "Unknown error"}
      </p>
    );
  }

  if (!data) return null;

  return <AssessmentReportLoaded data={data} />;
}

export default AssessmentReportPanel;
