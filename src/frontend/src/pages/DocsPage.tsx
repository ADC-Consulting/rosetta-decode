import { getJobDoc, getJobPlan, getJobSources, getJobTrustReport, listJobs } from "@/api/jobs";
import type { JobPlanResponse, JobSummary, TrustReportResponse } from "@/api/types";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { extractMarkdown } from "@/components/JobDetail/utils";
import TiptapEditor from "@/components/TiptapEditor";
import { cn } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  File,
  FileCode2,
  FileSpreadsheet,
  Folder,
  FolderOpen,
  ScrollText,
  Database,
} from "lucide-react";
import { marked } from "marked";
import { useMemo, useState } from "react";

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SkeletonBar({ className }: { className?: string }): React.ReactElement {
  return (
    <div
      className={cn(
        "rounded bg-linear-to-r from-muted via-muted-foreground/10 to-muted",
        "bg-size-[200%_100%] animate-[shimmer_2s_linear_infinite]",
        className,
      )}
      aria-hidden="true"
    />
  );
}

// ── Badges ────────────────────────────────────────────────────────────────────

function ConfidenceBadge({ value }: { value: string | null }): React.ReactElement {
  if (!value) return <span className="text-muted-foreground">—</span>;
  const classes: Record<string, string> = {
    high: "text-green-700 bg-green-50 border border-green-200",
    medium: "text-amber-700 bg-amber-50 border border-amber-200",
    low: "text-red-700 bg-red-50 border border-red-200",
    very_low: "text-red-700 bg-red-50 border border-red-200",
  };
  const cls = classes[value] ?? "text-muted-foreground bg-muted border border-border";
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium uppercase ${cls}`}>
      {value.replace("_", " ")}
    </span>
  );
}

function RiskBadge({ value }: { value: string | null }): React.ReactElement {
  if (!value) return <span className="text-muted-foreground">—</span>;
  const classes: Record<string, string> = {
    low: "text-green-700 bg-green-50 border border-green-200",
    medium: "text-amber-700 bg-amber-50 border border-amber-200",
    high: "text-red-700 bg-red-50 border border-red-200",
  };
  const cls = classes[value] ?? "text-muted-foreground bg-muted border border-border";
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium uppercase ${cls}`}>
      {value} risk
    </span>
  );
}

function StatusChip({ status }: { status: "proposed" | "accepted" }): React.ReactElement {
  if (status === "accepted") {
    return <span className="text-xs font-medium text-emerald-500">Accepted</span>;
  }
  return (
    <>
      <style>{`@keyframes docs-shimmer{from{background-position:200% center}to{background-position:-200% center}}`}</style>
      <span
        className="text-xs font-medium"
        style={{
          display: "inline-block",
          backgroundImage: "linear-gradient(90deg,#f59e0b 20%,#fef3c7 50%,#f59e0b 80%)",
          backgroundSize: "200% 100%",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
          backgroundClip: "text",
          animation: "docs-shimmer 4s linear infinite",
        }}
      >
        Under Review
      </span>
    </>
  );
}

// ── Read-only file tree ───────────────────────────────────────────────────────

function fileIcon(name: string): React.ReactElement {
  const lower = name.toLowerCase();
  const cls = "h-3.5 w-3.5 shrink-0 text-muted-foreground";
  if (lower.endsWith(".sas")) return <FileCode2 className={cls} />;
  if (lower.endsWith(".sas7bdat")) return <Database className={cls} />;
  if (lower.endsWith(".xls") || lower.endsWith(".xlsx") || lower.endsWith(".csv"))
    return <FileSpreadsheet className={cls} />;
  if (lower.endsWith(".log")) return <ScrollText className={cls} />;
  return <File className={cls} />;
}

function FileTreeNode({
  name,
  children,
  depth,
}: {
  name: string;
  children?: string[];
  depth: number;
}): React.ReactElement {
  const [open, setOpen] = useState(false);
  const indent = { paddingLeft: `${0.75 + depth * 1}rem` };

  if (children !== undefined) {
    return (
      <>
        <li
          className="flex items-center py-1 text-sm border-b border-border/40 last:border-b-0 cursor-pointer hover:bg-muted/30 transition-colors"
          style={indent}
          onClick={() => setOpen((o) => !o)}
        >
          {open
            ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground mr-1" />
            : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground mr-1" />}
          {open
            ? <FolderOpen className="h-4 w-4 shrink-0 text-muted-foreground mr-1.5" />
            : <Folder className="h-4 w-4 shrink-0 text-muted-foreground mr-1.5" />}
          <span className="truncate text-foreground text-xs">{name}</span>
          <span className="ml-1.5 text-[10px] text-muted-foreground">
            {children.length} {children.length === 1 ? "file" : "files"}
          </span>
        </li>
        {open && children.map((f) => (
          <FileTreeNode key={f} name={f} depth={depth + 1} />
        ))}
      </>
    );
  }

  return (
    <li
      className="flex items-center gap-1.5 py-1 text-xs border-b border-border/40 last:border-b-0 text-muted-foreground"
      style={indent}
    >
      <span className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {fileIcon(name)}
      <span className="truncate">{name}</span>
    </li>
  );
}

function ReadOnlyFileTree({ jobId }: { jobId: string }): React.ReactElement {
  const [open, setOpen] = useState(false);
  const { data: sources } = useQuery({
    queryKey: ["job", jobId, "sources"],
    queryFn: () => getJobSources(jobId),
    enabled: open,
  });

  const grouped = useMemo(() => {
    if (!sources) return null;
    const paths = Object.keys(sources.sources);
    const folders: Record<string, string[]> = {};
    const loose: string[] = [];
    for (const p of paths) {
      const slash = p.lastIndexOf("/");
      if (slash > 0) {
        const dir = p.slice(0, slash);
        const file = p.slice(slash + 1);
        if (!folders[dir]) folders[dir] = [];
        folders[dir].push(file);
      } else {
        loose.push(p);
      }
    }
    return { folders, loose };
  }, [sources]);

  return (
    <div className="rounded-md border border-border bg-background">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors rounded-md"
        aria-expanded={open}
      >
        {open
          ? <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
        <FolderOpen className="h-3.5 w-3.5 shrink-0" />
        Source files
      </button>
      {open && (
        <ul className="border-t border-border" aria-label="Source files">
          {!grouped && (
            <li className="px-3 py-2 text-xs text-muted-foreground animate-pulse">Loading…</li>
          )}
          {grouped && grouped.loose.map((f) => (
            <FileTreeNode key={f} name={f} depth={0} />
          ))}
          {grouped && Object.entries(grouped.folders).map(([dir, files]) => (
            <FileTreeNode key={dir} name={dir} children={files} depth={0} />
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Card ──────────────────────────────────────────────────────────────────────

function DocCard({
  job,
  onOpen,
}: {
  job: JobSummary;
  onOpen: (jobId: string, tab: "tech" | "plain") => void;
}): React.ReactElement {
  const { data: trustReport } = useQuery<TrustReportResponse>({
    queryKey: ["job", job.job_id, "trust-report"],
    queryFn: () => getJobTrustReport(job.job_id),
  });
  const { data: planData } = useQuery<JobPlanResponse | null>({
    queryKey: ["job", job.job_id, "plan"],
    queryFn: () => getJobPlan(job.job_id),
  });

  const jobName = job.name ?? job.job_id.slice(0, 8) + "…";
  const formattedDate = new Date(job.created_at).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });

  return (
    <div className="rounded-md border border-border bg-card flex flex-col">
      <div className="p-4 flex flex-col gap-3 flex-1">
        <div className="flex items-center justify-between gap-2">
          <StatusChip status={job.status as "proposed" | "accepted"} />
          <RiskBadge value={planData?.overall_risk ?? null} />
        </div>

        <div>
          <p className="text-base font-semibold text-foreground leading-snug">{jobName}</p>
          {planData?.summary ? (
            <p className="mt-1 text-sm text-muted-foreground line-clamp-2 leading-relaxed">
              {planData.summary}
            </p>
          ) : (
            <div className="mt-2 space-y-1.5">
              <SkeletonBar className="h-3 w-full" />
              <SkeletonBar className="h-3 w-4/5" />
            </div>
          )}
        </div>

        <div className="border-t border-border pt-3 space-y-1.5">
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span className="flex items-center gap-1">
              <FolderOpen size={14} />
              {job.file_count} {job.file_count === 1 ? "file" : "files"}
            </span>
            {trustReport ? (
              <span className="flex items-center gap-1.5">
                Confidence: <ConfidenceBadge value={trustReport.overall_confidence} />
              </span>
            ) : (
              <SkeletonBar className="h-3 w-24" />
            )}
          </div>
          {trustReport ? (
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
              <span className="text-green-700">
                ✓ {trustReport.auto_verified}/{trustReport.total_blocks} auto-verified
              </span>
              <span className="text-amber-700">
                ⚠ {trustReport.needs_review} needs review
              </span>
              {trustReport.failed_reconciliation > 0 && (
                <span className="text-red-700">
                  ✗ {trustReport.failed_reconciliation} failed
                </span>
              )}
            </div>
          ) : (
            <SkeletonBar className="h-3 w-3/4" />
          )}
        </div>
      </div>

      <div className="px-4 pb-4 flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">{formattedDate}</span>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="outline" onClick={() => onOpen(job.job_id, "plain")}>
            Plain English
          </Button>
          <Button size="sm" variant="outline" onClick={() => onOpen(job.job_id, "tech")}>
            Technical
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Popup ─────────────────────────────────────────────────────────────────────

function DocPopup({
  jobId,
  tab,
  onTabChange,
  selectedJob,
  trustReport,
  planData,
  onClose,
}: {
  jobId: string | null;
  tab: "tech" | "plain";
  onTabChange: (tab: "tech" | "plain") => void;
  selectedJob: JobSummary | null;
  trustReport: TrustReportResponse | null;
  planData: JobPlanResponse | null;
  onClose: () => void;
}): React.ReactElement {
  const { data: doc, isLoading: docLoading } = useQuery({
    queryKey: ["job", jobId, "doc"],
    queryFn: () => getJobDoc(jobId!),
    enabled: !!jobId,
  });

  const techHtml = useMemo(
    () => (doc?.doc ? String(marked.parse(extractMarkdown(doc.doc))) : ""),
    [doc],
  );
  const plainHtml = useMemo(
    () =>
      doc?.non_technical_doc
        ? String(marked.parse(extractMarkdown(doc.non_technical_doc)))
        : "",
    [doc],
  );

  const jobName = selectedJob?.name ?? (selectedJob ? selectedJob.job_id.slice(0, 8) + "…" : "");
  const totalBlocks = trustReport?.total_blocks ?? 0;
  const autoVerified = trustReport?.auto_verified ?? 0;
  const needsReview = trustReport?.needs_review ?? 0;

  return (
    <Dialog open={!!jobId} onOpenChange={(open) => { if (!open) onClose(); }}>
      {/* Override the base DialogContent `grid gap-4` so flex layout works correctly */}
      <DialogContent className="flex! flex-col! gap-0! p-0! max-w-5xl w-[90vw] h-[85vh]! overflow-hidden">
        {/* Header */}
        <div className="px-6 pt-5 pb-4 flex items-start justify-between gap-4 shrink-0 border-b border-border">
          <div className="flex flex-col gap-2 min-w-0">
            <DialogTitle className="text-base font-semibold">{jobName}</DialogTitle>
            <div className="flex items-center flex-wrap gap-2">
              {selectedJob && <StatusChip status={selectedJob.status as "proposed" | "accepted"} />}
              {planData && <RiskBadge value={planData.overall_risk} />}
              {trustReport && <ConfidenceBadge value={trustReport.overall_confidence} />}
            </div>
          </div>
          <Tabs value={tab} onValueChange={(v) => onTabChange(v as "tech" | "plain")} className="shrink-0">
            <TabsList>
              <TabsTrigger value="plain">Plain English</TabsTrigger>
              <TabsTrigger value="tech">Technical</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto min-h-0 px-6 py-4">
          {jobId && (
            <div className="mb-4">
              <ReadOnlyFileTree jobId={jobId} />
            </div>
          )}
          {docLoading ? (
            <div className="flex items-center justify-center h-40">
              <div
                aria-label="Loading documentation"
                className="size-6 rounded-full border-2 border-border border-t-foreground animate-spin"
              />
            </div>
          ) : tab === "tech" ? (
            techHtml
              ? <TiptapEditor content={techHtml} readOnly />
              : <p className="text-sm text-muted-foreground">Technical documentation not yet generated.</p>
          ) : (
            plainHtml
              ? <TiptapEditor content={plainHtml} readOnly />
              : <p className="text-sm text-muted-foreground">Plain English summary not yet generated.</p>
          )}
        </div>

        {/* Footer */}
        <DialogFooter showCloseButton className="mx-0 mb-0 rounded-b-xl">
          {trustReport && (
            <span className="text-xs text-muted-foreground self-center mr-auto">
              {totalBlocks} total blocks · {autoVerified} auto-verified · {needsReview} needs review
            </span>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DocsPage(): React.ReactElement {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [popupTab, setPopupTab] = useState<"tech" | "plain">("plain");

  const { data: allJobs, isLoading } = useQuery<JobSummary[], Error>({
    queryKey: ["jobs"],
    queryFn: listJobs,
  });

  const jobs = useMemo(
    () => allJobs?.filter((j) => j.status === "proposed" || j.status === "accepted") ?? [],
    [allJobs],
  );

  const selectedJob = useMemo(
    () => jobs.find((j) => j.job_id === selectedJobId) ?? null,
    [jobs, selectedJobId],
  );

  const { data: popupTrustReport } = useQuery<TrustReportResponse>({
    queryKey: ["job", selectedJobId, "trust-report"],
    queryFn: () => getJobTrustReport(selectedJobId!),
    enabled: !!selectedJobId,
  });
  const { data: popupPlanData } = useQuery<JobPlanResponse | null>({
    queryKey: ["job", selectedJobId, "plan"],
    queryFn: () => getJobPlan(selectedJobId!),
    enabled: !!selectedJobId,
  });

  return (
    <div className="space-y-6">
      <style>{`@keyframes shimmer{from{background-position:200% center}to{background-position:-200% center}}`}</style>

      <div>
        <h1 className="text-xl font-semibold text-foreground">Documentation</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          LLM-generated migration summaries for reviewed and accepted migrations.
        </p>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {([0, 1, 2] as const).map((i) => (
            <div key={i} className="rounded-md border border-border bg-card p-4 space-y-3" aria-hidden="true">
              <div className="flex items-center justify-between">
                <SkeletonBar className="h-3 w-20" />
                <SkeletonBar className="h-3 w-16" />
              </div>
              <SkeletonBar className="h-4 w-2/3" />
              <SkeletonBar className="h-3 w-full" />
              <SkeletonBar className="h-3 w-4/5" />
              <div className="border-t border-border pt-3 space-y-1.5">
                <SkeletonBar className="h-3 w-1/2" />
                <SkeletonBar className="h-3 w-3/4" />
              </div>
              <div className="flex items-center justify-between pt-1">
                <SkeletonBar className="h-3 w-24" />
                <div className="flex gap-1.5">
                  <SkeletonBar className="h-7 w-24 rounded-md" />
                  <SkeletonBar className="h-7 w-24 rounded-md" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {!isLoading && jobs.length === 0 && (
        <div className="flex items-center justify-center py-16">
          <p className="text-sm text-muted-foreground">No completed migrations yet.</p>
        </div>
      )}

      {!isLoading && jobs.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {jobs.map((job) => (
            <DocCard key={job.job_id} job={job} onOpen={(id, t) => { setPopupTab(t); setSelectedJobId(id); }} />
          ))}
        </div>
      )}

      <DocPopup
        jobId={selectedJobId}
        tab={popupTab}
        onTabChange={setPopupTab}
        selectedJob={selectedJob}
        trustReport={popupTrustReport ?? null}
        planData={popupPlanData ?? null}
        onClose={() => setSelectedJobId(null)}
      />
    </div>
  );
}
