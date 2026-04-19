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
import FileTree from "@/components/FileTree";
import LineageGraph from "@/components/LineageGraph";
import TiptapEditor from "@/components/TiptapEditor";
import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { Monaco } from "@monaco-editor/react";
import { Editor } from "@monaco-editor/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download, Moon, Sun } from "lucide-react";
import { marked } from "marked";
import { Suspense, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

export const STATUS_LABEL: Record<JobStatusValue, string> = {
  queued: "Queued",
  running: "Running",
  done: "Completed",
  failed: "Failed",
};

const STATUS_PILL_CLASS: Record<JobStatusValue, string> = {
  queued: "bg-slate-600",
  running: "bg-blue-600",
  done: "bg-emerald-600",
  failed: "bg-red-600",
};

const STATUS_SHIMMER: Record<JobStatusValue, boolean> = {
  queued: true,
  running: true,
  done: false,
  failed: false,
};

export function StatusBadge({
  status,
}: {
  status: JobStatusValue;
}): React.ReactElement {
  const shimmer = STATUS_SHIMMER[status];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5",
        STATUS_PILL_CLASS[status],
      )}
    >
      {shimmer && (
        <style>{`@keyframes shimmer { from { background-position: 200% center; } to { background-position: -200% center; } }`}</style>
      )}
      <span
        className={cn("text-xs font-medium", !shimmer && "text-white")}
        style={
          shimmer
            ? {
                background:
                  status === "running"
                    ? "linear-gradient(90deg, #bfdbfe 25%, #eff6ff 50%, #bfdbfe 75%)"
                    : "linear-gradient(90deg, #e2e8f0 25%, #f8fafc 50%, #e2e8f0 75%)",
                backgroundSize: "200% 100%",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
                animation: "shimmer 3.5s linear infinite",
              }
            : undefined
        }
      >
        {STATUS_LABEL[status]}
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// SAS language registration
// ---------------------------------------------------------------------------

function registerSasLanguage(monaco: Monaco): void {
  if (monaco.languages.getLanguages().some((l) => l.id === "sas")) return;

  monaco.languages.register({ id: "sas" });

  monaco.languages.setMonarchTokensProvider("sas", {
    ignoreCase: true,
    keywords: [
      "DATA",
      "SET",
      "RUN",
      "PROC",
      "QUIT",
      "IF",
      "THEN",
      "ELSE",
      "DO",
      "END",
      "BY",
      "WHERE",
      "KEEP",
      "DROP",
      "MERGE",
      "OUTPUT",
      "RETAIN",
      "LENGTH",
      "FORMAT",
      "INFORMAT",
      "INPUT",
      "CARDS",
      "DATALINES",
      "SELECT",
      "WHEN",
      "OTHERWISE",
      "CLASS",
      "VAR",
      "MODEL",
      "TABLES",
      "FREQ",
      "MEANS",
      "SORT",
      "PRINT",
      "SQL",
      "CREATE",
      "TABLE",
      "AS",
      "FROM",
      "GROUP",
      "HAVING",
      "ORDER",
      "INTO",
      "INSERT",
      "DELETE",
      "UPDATE",
      "JOIN",
      "ON",
      "AND",
      "OR",
      "NOT",
      "IN",
      "LIKE",
      "BETWEEN",
      "CASE",
      "DISTINCT",
      "UNION",
      "OUTER",
      "INNER",
      "LEFT",
      "RIGHT",
      "FULL",
    ],
    macroKeywords: [
      "%LET",
      "%IF",
      "%THEN",
      "%ELSE",
      "%DO",
      "%END",
      "%MACRO",
      "%MEND",
      "%INCLUDE",
      "%PUT",
    ],
    tokenizer: {
      root: [
        // Block comments
        [/\/\*/, "comment", "@blockComment"],
        // Line comments (asterisk at statement start)
        [/^\s*\*[^;]*;/, "comment"],
        // Macro keywords
        [
          /%[a-zA-Z]+/,
          {
            cases: {
              "@macroKeywords": "keyword.macro",
              "@default": "variable.macro",
            },
          },
        ],
        // Macro variables
        [/&[a-zA-Z_][a-zA-Z0-9_]*/, "variable"],
        // Keywords
        [
          /[a-zA-Z_][a-zA-Z0-9_]*/,
          {
            cases: {
              "@keywords": "keyword",
              "@default": "identifier",
            },
          },
        ],
        // Strings
        [/"([^"\\]|\\.)*"/, "string"],
        [/'([^'\\]|\\.)*'/, "string"],
        // Numbers
        [/\d+\.?\d*([eE][+-]?\d+)?/, "number"],
        // Operators
        [/[=<>!|+\-*\/]/, "operator"],
        // Delimiters
        [/[;(),]/, "delimiter"],
      ],
      blockComment: [
        [/[^/*]+/, "comment"],
        [/\*\//, "comment", "@pop"],
        [/[/*]/, "comment"],
      ],
    },
  });

  monaco.editor.defineTheme("sas-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "4fc1ff", fontStyle: "bold" },
      { token: "keyword.macro", foreground: "c678dd", fontStyle: "bold" },
      { token: "variable", foreground: "e5c07b" },
      { token: "variable.macro", foreground: "e5c07b" },
      { token: "string", foreground: "e06c75" },
      { token: "comment", foreground: "5c6370", fontStyle: "italic" },
      { token: "number", foreground: "d19a66" },
      { token: "operator", foreground: "abb2bf" },
      { token: "delimiter", foreground: "abb2bf" },
      { token: "identifier", foreground: "abb2bf" },
    ],
    colors: {
      "editor.background": "#1e1e1e",
    },
  });

  monaco.editor.defineTheme("sas-light", {
    base: "vs",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "0070c1", fontStyle: "bold" },
      { token: "keyword.macro", foreground: "8700af", fontStyle: "bold" },
      { token: "variable", foreground: "795e26" },
      { token: "variable.macro", foreground: "795e26" },
      { token: "string", foreground: "a31515" },
      { token: "comment", foreground: "008000", fontStyle: "italic" },
      { token: "number", foreground: "09885a" },
      { token: "operator", foreground: "000000" },
      { token: "delimiter", foreground: "000000" },
      { token: "identifier", foreground: "000000" },
    ],
    colors: {
      "editor.background": "#ffffff",
    },
  });
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
  const [editorDark, setEditorDark] = useState(true);
  const monacoTheme = editorDark
    ? { sas: "sas-dark", python: "vs-dark" }
    : { sas: "sas-light", python: "vs" };
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

  const allPaths = sources ? Object.keys(sources.sources) : [];
  const sasKeys = allPaths.filter((k) => k.endsWith(".sas"));
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
      toast.error(
        err instanceof Error
          ? err.message
          : "Your changes could not be saved. Please try again.",
      );
    },
  });

  const refineMutation = useMutation({
    mutationFn: () => refineJob(jobId, hint.trim() || undefined),
    onSuccess: (data) => {
      navigate(`/jobs/${data.job_id}`);
    },
    onError: (err) => {
      toast.error(
        err instanceof Error
          ? err.message
          : "The refinement request could not be submitted. Please try again.",
      );
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading sources…
      </div>
    );
  }

  const breadcrumbParts = effectiveSasKey ? effectiveSasKey.split("/") : [];

  return (
    <div className="space-y-4">
      {/* Three-pane: Explorer | SAS | Python */}
      {/* Editor theme toggle */}
      <div className="flex justify-end gap-2 mb-1">
        <button
          type="button"
          aria-label={
            editorDark
              ? "Switch editor to light theme"
              : "Switch editor to dark theme"
          }
          onClick={() => setEditorDark((d) => !d)}
          className="flex items-center text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer border border-border rounded p-1.5"
        >
          {editorDark ? <Sun size={14} /> : <Moon size={14} />}
        </button>
      </div>
      <ResizablePanelGroup
        id="editor-panel-group"
        orientation="horizontal"
        className="rounded-md border border-border overflow-hidden"
        style={{ height: "calc(100vh - 240px)" }}
      >
        {/* Left: file tree */}
        <ResizablePanel defaultSize="22%" minSize="15%" maxSize="40%">
          <div
            className="flex flex-col h-full"
            style={{ background: editorDark ? "#1e1e1e" : "#fafafa" }}
          >
            <div
              className="h-8 flex items-center px-3 text-[10px] font-semibold tracking-widest uppercase shrink-0 text-muted-foreground border-b border-border"
              style={{ background: editorDark ? "#1e1e1e" : "#fafafa" }}
            >
              Explorer
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <FileTree
                paths={allPaths}
                selectedPath={effectiveSasKey || null}
                onSelect={(path) => {
                  if (path.endsWith(".sas")) setSelectedSasKey(path);
                  else setSelectedSasKey("");
                }}
                storageKey={`job-${jobId}`}
                theme={editorDark ? "dark" : "light"}
              />
            </div>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right: SAS + Python */}
        <ResizablePanel defaultSize="78%">
          <ResizablePanelGroup orientation="horizontal">
            {/* SAS source — read-only */}
            <ResizablePanel defaultSize="50%">
              <div className="flex flex-col h-full">
                <div
                  className="h-8 px-3 text-xs font-medium text-muted-foreground border-b border-border shrink-0 flex items-center"
                  style={{ background: editorDark ? "#1e1e1e" : "#fafafa" }}
                >
                  SAS Source
                  {effectiveSasKey && (
                    <span className="ml-2 text-[11px] text-muted-foreground/60">
                      {effectiveSasKey}
                    </span>
                  )}
                </div>
                {effectiveSasKey ? (
                  <Suspense
                    fallback={
                      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                        Loading…
                      </div>
                    }
                  >
                    <Editor
                      height="100%"
                      value={sasSource}
                      language="sas"
                      theme={monacoTheme.sas}
                      beforeMount={registerSasLanguage}
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
                ) : (
                  <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                    Select a .sas file
                  </div>
                )}
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            {/* Python — editable */}
            <ResizablePanel defaultSize="50%">
              <div className="flex flex-col h-full">
                <div
                  className="h-8 px-3 text-xs font-medium text-muted-foreground border-b border-border shrink-0 flex items-center gap-2"
                  style={{ background: editorDark ? "#1e1e1e" : "#fafafa" }}
                >
                  <span>Generated Python</span>
                  {breadcrumbParts.length > 0 && (
                    <span className="text-[11px] text-muted-foreground/60">
                      {breadcrumbParts.join(" / ")}
                    </span>
                  )}
                </div>
                <Suspense
                  fallback={
                    <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                      Loading…
                    </div>
                  }
                >
                  <Editor
                    height="100%"
                    value={code}
                    language="python"
                    theme={monacoTheme.python}
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
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
      </ResizablePanelGroup>

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
    <div className="flex gap-4 h-[calc(100vh-320px)] min-h-[300px]">
      <div className="flex flex-col flex-1 min-w-0">
        <h3 className="text-sm font-semibold mb-2 shrink-0">Reconciliation report</h3>
        <div className="flex-1 overflow-y-auto">
          <TiptapEditor content={reportHtml} readOnly={false} />
        </div>
      </div>
      <div className="flex flex-col flex-1 min-w-0">
        <h3 className="text-sm font-semibold mb-2 shrink-0">Migration summary</h3>
        <div className="flex-1 overflow-y-auto">
          {docData?.doc ? (
            <TiptapEditor
              content={marked.parse(docData.doc) as string}
              readOnly={false}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              Summary not yet generated.
            </p>
          )}
        </div>
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
