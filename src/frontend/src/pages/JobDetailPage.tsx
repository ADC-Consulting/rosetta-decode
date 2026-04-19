import {
  downloadJob,
  getJob,
  getJobDoc,
  getJobLineage,
  getJobSources,
  refineJob,
  updateJobPythonCode,
} from "@/api/jobs";
import type { JobStatusValue } from "@/api/types";
import LineageGraph from "@/components/LineageGraph";
import TiptapEditor from "@/components/TiptapEditor";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { Editor } from "@monaco-editor/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download } from "lucide-react";
import { marked } from "marked";
import { Suspense, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_LABEL: Record<JobStatusValue, string> = {
  queued: "Queued",
  running: "Running",
  done: "Completed",
  failed: "Failed",
};

const STATUS_CLASS: Record<JobStatusValue, string> = {
  queued: "bg-muted text-muted-foreground",
  running: "bg-blue-500/20 text-blue-400",
  done: "bg-emerald-500/20 text-emerald-400",
  failed: "bg-red-500/20 text-red-400",
};

function StatusBadge({
  status,
}: {
  status: JobStatusValue;
}): React.ReactElement {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        STATUS_CLASS[status],
      )}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Editor tab (SAS left read-only, Python right editable)
// ---------------------------------------------------------------------------

function EditorTab({
  jobId,
  initialCode,
}: {
  jobId: string;
  initialCode: string;
}): React.ReactElement {
  const navigate = useNavigate();
  const [code, setCode] = useState(initialCode);
  const [saved, setSaved] = useState(false);
  const [showRefine, setShowRefine] = useState(false);
  const [hint, setHint] = useState("");
  const [selectedSasKey, setSelectedSasKey] = useState<string>("");

  const { data: sources, isLoading } = useQuery({
    queryKey: ["job", jobId, "sources"],
    queryFn: () => getJobSources(jobId),
    enabled: !!jobId,
  });

  const sasKeys = sources
    ? Object.keys(sources.sources).filter((k) => k.endsWith(".sas"))
    : [];
  const effectiveSasKey = selectedSasKey || sasKeys[0] || "";
  const sasSource =
    effectiveSasKey && sources ? (sources.sources[effectiveSasKey] ?? "") : "";

  const saveMutation = useMutation({
    mutationFn: () => updateJobPythonCode(jobId, code),
    onSuccess: () => {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Your changes could not be saved. Please try again.");
    },
  });

  const refineMutation = useMutation({
    mutationFn: () => refineJob(jobId, hint.trim() || undefined),
    onSuccess: (data) => {
      navigate(`/jobs/${data.job_id}`);
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "The refinement request could not be submitted. Please try again.");
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading sources…
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {sasKeys.length > 1 && (
        <div className="flex items-center gap-2">
          <label
            htmlFor="editor-file-select"
            className="text-xs font-medium text-muted-foreground shrink-0"
          >
            SAS file:
          </label>
          <select
            id="editor-file-select"
            value={effectiveSasKey}
            onChange={(e) => setSelectedSasKey(e.target.value)}
            className="rounded-md border border-border bg-background px-2 py-1 text-sm cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {sasKeys.map((k) => (
              <option key={k} value={k}>
                {k.split("/").pop() ?? k}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="flex gap-0 rounded-md overflow-hidden border border-border">
        {/* Left: SAS source — read-only */}
        <div className="flex flex-col flex-1 min-w-0">
          <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-muted border-b border-border shrink-0">
            SAS Source
          </div>
          <Suspense
            fallback={
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                Loading…
              </div>
            }
          >
            <Editor
              height="520px"
              value={sasSource}
              language="plaintext"
              theme="vs-dark"
              loading={
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  Loading…
                </div>
              }
              options={{
                readOnly: true,
                fontSize: 13,
                minimap: { enabled: false },
              }}
            />
          </Suspense>
        </div>

        <div className="w-px bg-border shrink-0" />

        {/* Right: Python — editable */}
        <div className="flex flex-col flex-1 min-w-0">
          <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground bg-muted border-b border-border shrink-0">
            Generated Python
          </div>
          <Suspense
            fallback={
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                Loading…
              </div>
            }
          >
            <Editor
              height="520px"
              value={code}
              language="python"
              theme="vs-dark"
              loading={
                <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                  Loading…
                </div>
              }
              onChange={(value) => setCode(value ?? "")}
              options={{ fontSize: 13, minimap: { enabled: false } }}
            />
          </Suspense>
        </div>
      </div>

      {/* Action row */}
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          className="cursor-pointer"
        >
          {saveMutation.isPending ? "Saving…" : "Save & Re-reconcile"}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowRefine((v) => !v)}
          className="cursor-pointer"
        >
          Refine migration
        </Button>
        {saved && (
          <span className="text-xs text-emerald-500 transition-opacity">
            Saved.
          </span>
        )}
      </div>

      {showRefine && (
        <div className="space-y-2 rounded-md border border-border p-4 bg-muted/20">
          <label htmlFor="refine-hint" className="text-sm font-medium">
            Refinement hint (optional)
          </label>
          <textarea
            id="refine-hint"
            value={hint}
            onChange={(e) => setHint(e.target.value)}
            placeholder="Describe what should be improved…"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm resize-none min-h-20 focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button
            size="sm"
            onClick={() => refineMutation.mutate()}
            disabled={refineMutation.isPending}
            className="cursor-pointer"
          >
            {refineMutation.isPending ? "Submitting…" : "Submit refinement"}
          </Button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Markdown renderer
// ---------------------------------------------------------------------------

function MarkdownDoc({ source }: { source: string }): React.ReactElement {
  const html = useMemo(() => marked.parse(source) as string, [source]);
  return (
    <article
      className="prose prose-sm dark:prose-invert max-w-none rounded-md border border-border bg-muted/20 p-4"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

// ---------------------------------------------------------------------------
// Report tab
// ---------------------------------------------------------------------------

function ReportTab({
  jobId,
  report,
  isDone,
}: {
  jobId: string;
  report: Record<string, unknown> | null;
  isDone: boolean;
}): React.ReactElement {
  const { data: docData } = useQuery({
    queryKey: ["job", jobId, "doc"],
    queryFn: () => getJobDoc(jobId),
    enabled: !!jobId && isDone,
  });

  if (!isDone) {
    return (
      <p className="text-sm text-muted-foreground">
        Report available once migration completes.
      </p>
    );
  }

  const reportHtml = `<pre><code>${JSON.stringify(report, null, 2)}</code></pre>`;

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold mb-2">Reconciliation report</h3>
        <TiptapEditor content={reportHtml} readOnly={true} />
      </div>
      <div>
        <h3 className="text-sm font-semibold mb-2">Migration summary</h3>
        {docData?.doc ? (
          <MarkdownDoc source={docData.doc} />
        ) : (
          <p className="text-sm text-muted-foreground">
            Summary not yet generated.
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lineage tab
// ---------------------------------------------------------------------------

function LineageTab({ jobId }: { jobId: string }): React.ReactElement {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["job", jobId, "lineage"],
    queryFn: () => getJobLineage(jobId),
    enabled: !!jobId,
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading lineage…
      </div>
    );
  }

  if (isError) {
    const msg = error instanceof Error ? error.message : "Unknown error";
    if (msg.includes("202") || msg.toLowerCase().includes("not ready")) {
      return (
        <p className="text-sm text-muted-foreground">
          Lineage not yet available.
        </p>
      );
    }
    toast.error("Lineage data could not be loaded. Please try again later.");
    return (
      <p className="text-sm text-muted-foreground">Could not load lineage.</p>
    );
  }

  if (!data) {
    return (
      <p className="text-sm text-muted-foreground">
        Lineage not yet available.
      </p>
    );
  }

  return <LineageGraph lineage={data} />;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function JobDetailPage(): React.ReactElement {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: job } = useQuery({
    queryKey: ["job", id],
    queryFn: () => getJob(id),
    enabled: !!id,
    refetchInterval: (q) =>
      q.state.data?.status === "queued" || q.state.data?.status === "running"
        ? 3000
        : false,
  });

  const shortId = id.length >= 8 ? `${id.slice(0, 8)}…` : id;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => navigate("/jobs")}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          aria-label="Back to migrations list"
        >
          <ArrowLeft size={15} />
          Migrations
        </button>
        <div className="flex flex-col gap-0">
          <span className="text-sm font-medium text-foreground">
            {job?.name ?? shortId}
          </span>
        </div>
        {job && <StatusBadge status={job.status} />}
        <div className="ml-auto">
          <Button
            variant="outline"
            size="sm"
            onClick={() => downloadJob(id)}
            className="flex items-center gap-1.5 cursor-pointer"
            aria-label="Download migration output"
          >
            <Download size={14} />
            Download
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="editor">
        <TabsList>
          <TabsTrigger value="editor">Editor</TabsTrigger>
          <TabsTrigger value="report">Report</TabsTrigger>
          <TabsTrigger value="lineage">Lineage</TabsTrigger>
        </TabsList>

        <TabsContent value="editor" className="mt-4">
          <EditorTab jobId={id} initialCode={job?.python_code ?? ""} />
        </TabsContent>

        <TabsContent value="report" className="mt-4">
          <ReportTab
            jobId={id}
            report={job?.report ?? null}
            isDone={job?.status === "done"}
          />
        </TabsContent>

        <TabsContent value="lineage" className="mt-4">
          <LineageTab jobId={id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
