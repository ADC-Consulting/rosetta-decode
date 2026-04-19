import {
  acceptJob,
  downloadJob,
  getJob,
  getJobDoc,
  getJobHistory,
  getJobLineage,
  getJobPlan,
  getJobSources,
  patchJobPlan,
  refineJob,
  updateJobPythonCode,
} from "@/api/jobs";
import type {
  BlockOverride,
  BlockPlan,
  JobHistoryEntry,
  JobStatusValue,
  PatchPlanRequest,
} from "@/api/types";
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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, Download, Moon, Sun, User } from "lucide-react";
import { marked } from "marked";
import { Suspense, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

/** Unwrap `{"markdown":"..."}` responses from older LLM calls. */
function extractMarkdown(raw: string): string {
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (
      parsed &&
      typeof parsed === "object" &&
      "markdown" in parsed &&
      typeof (parsed as Record<string, unknown>).markdown === "string"
    ) {
      return (parsed as { markdown: string }).markdown;
    }
  } catch {
    // not JSON — use as-is
  }
  return raw;
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

// eslint-disable-next-line react-refresh/only-export-components
export const STATUS_LABEL: Record<JobStatusValue, string> = {
  queued: "Queued",
  running: "Running",
  proposed: "Under Review",
  accepted: "Accepted",
  failed: "Failed",
  done: "Under Review", // legacy — worker pre-F3
};

const STATUS_PILL_CLASS: Record<JobStatusValue, string> = {
  queued: "bg-slate-600",
  running: "bg-blue-600",
  proposed: "bg-amber-500",
  done: "bg-amber-500", // legacy
  accepted: "bg-emerald-600",
  failed: "bg-red-600",
};

const STATUS_SHIMMER: Record<JobStatusValue, boolean> = {
  queued: true,
  running: true,
  proposed: true,
  done: false, // legacy — treat as terminal
  accepted: false,
  failed: false,
};

const POLLING_STATUSES: JobStatusValue[] = ["queued", "running", "proposed"];

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
                    : status === "proposed"
                      ? "linear-gradient(90deg, #fde68a 25%, #fffbeb 50%, #fde68a 75%)"
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
        [/[=<>!|+\-*/]/, "operator"],
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
  generatedFiles,
}: {
  jobId: string;
  initialCode: string;
  generatedFiles: Record<string, string> | null;
}): React.ReactElement {
  const navigate = useNavigate();
  const [editorDark, setEditorDark] = useState(false);
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

  // S-M: derive per-file Python from generated_files when available
  const perFileCode: string | null = (() => {
    if (!generatedFiles || !effectiveSasKey) return null;
    const basename = effectiveSasKey.split("/").pop() ?? effectiveSasKey;
    const pyKey = basename.replace(/\.sas$/i, ".py");
    return generatedFiles[pyKey] ?? null;
  })();
  const rightCode = perFileCode ?? code;
  const rightReadOnly = perFileCode !== null;

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
                  {rightReadOnly && (
                    <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 border border-blue-200 font-semibold">
                      per-file view
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
                    value={rightCode}
                    language="python"
                    theme={monacoTheme.python}
                    loading={
                      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                        Loading…
                      </div>
                    }
                    onChange={(value) => {
                      if (!rightReadOnly) setCode(value ?? "");
                    }}
                    options={{
                      fontSize: 13,
                      minimap: { enabled: false },
                      readOnly: rightReadOnly,
                    }}
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
// Plan tab
// ---------------------------------------------------------------------------

const RISK_BADGE: Record<"low" | "medium" | "high", string> = {
  low: "text-green-700 bg-green-50 border border-green-200",
  medium: "text-amber-700 bg-amber-50 border border-amber-200",
  high: "text-red-700 bg-red-50 border border-red-200",
};
const RISK_CELL: Record<"low" | "medium" | "high", string> = {
  low: "text-green-700",
  medium: "text-amber-700",
  high: "text-red-700",
};

function ReconSummaryCard({
  report,
}: {
  report: Record<string, unknown> | null;
}): React.ReactElement | null {
  if (!report) return null;
  const checks =
    (report.checks as Array<{ name: string; status: string }> | undefined) ??
    [];
  const passed = checks.filter((c) => c.status === "pass").length;
  const failed = checks.filter((c) => c.status !== "pass").length;
  const allPassed = failed === 0 && checks.length > 0;
  return (
    <div
      className={`rounded-lg border p-3 flex items-center gap-3 ${
        allPassed
          ? "border-emerald-200 bg-emerald-50"
          : "border-red-200 bg-red-50"
      }`}
    >
      <span
        className={`text-lg ${allPassed ? "text-emerald-600" : "text-red-500"}`}
      >
        {allPassed ? "✓" : "✗"}
      </span>
      <div>
        <p
          className={`text-sm font-semibold ${allPassed ? "text-emerald-700" : "text-red-700"}`}
        >
          {allPassed
            ? "Reconciliation passed"
            : "Reconciliation issues detected"}
        </p>
        <p className="text-xs text-muted-foreground">
          {passed} passed · {failed} failed · {checks.length} total checks
        </p>
        {!allPassed && (report.diff_summary as string | undefined) && (
          <p className="text-xs text-red-600 mt-1">
            {report.diff_summary as string}
          </p>
        )}
      </div>
    </div>
  );
}

function BlockPlanTable({
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
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Type
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Strategy
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Risk
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Effort
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Rationale
            </th>
            <th className="px-3 py-2 font-medium text-muted-foreground">
              Note
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {blockPlans.map((bp) => (
            <tr key={bp.block_id} className="hover:bg-muted/30">
              <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                {bp.block_id}
              </td>
              <td className="px-3 py-2 font-mono text-xs">{bp.block_type}</td>
              <td className="px-3 py-2 text-xs">
                {isProposed ? (
                  <select
                    value={overrides[bp.block_id]?.strategy ?? bp.strategy}
                    onChange={(e) =>
                      onStrategyChange(bp.block_id, e.target.value)
                    }
                    className="rounded border border-border bg-background px-1 py-0.5 text-xs"
                    aria-label={`Strategy for ${bp.block_id}`}
                  >
                    <option value="translate">translate</option>
                    <option value="stub">stub</option>
                    <option value="skip">skip</option>
                  </select>
                ) : (
                  <span className="capitalize">
                    {overrides[bp.block_id]?.strategy ?? bp.strategy}
                  </span>
                )}
              </td>
              <td
                className={`px-3 py-2 text-xs font-semibold capitalize ${RISK_CELL[bp.risk]}`}
              >
                {isProposed ? (
                  <select
                    value={overrides[bp.block_id]?.risk ?? bp.risk}
                    onChange={(e) => onRiskChange(bp.block_id, e.target.value)}
                    className="rounded border border-border bg-background px-1 py-0.5 text-xs font-normal"
                    aria-label={`Risk for ${bp.block_id}`}
                  >
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="high">high</option>
                  </select>
                ) : (
                  (overrides[bp.block_id]?.risk ?? bp.risk)
                )}
              </td>
              <td className="px-3 py-2 text-xs capitalize">
                {bp.estimated_effort}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {bp.rationale}
              </td>
              <td className="px-3 py-2 text-xs">
                {isProposed ? (
                  <div className="flex items-center gap-1">
                    <input
                      type="text"
                      placeholder="Add note…"
                      value={overrides[bp.block_id]?.note ?? ""}
                      onChange={(e) =>
                        onNoteChange(bp.block_id, e.target.value)
                      }
                      className="rounded border border-border bg-background px-1.5 py-0.5 text-xs w-28"
                      aria-label={`Note for ${bp.block_id}`}
                    />
                    {savingBlockId === bp.block_id && (
                      <span className="text-[10px] text-muted-foreground">
                        Saving…
                      </span>
                    )}
                  </div>
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

function PlanTab({
  jobId,
  isReviewable,
  jobStatus,
  report,
}: {
  jobId: string;
  isReviewable: boolean;
  jobStatus: JobStatusValue;
  report: Record<string, unknown> | null;
}): React.ReactElement {
  const queryClient = useQueryClient();
  const [overrides, setOverrides] = useState<Record<string, BlockOverride>>({});
  const [savingBlockId, setSavingBlockId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["job", jobId, "plan"],
    queryFn: () => getJobPlan(jobId),
    enabled: !!jobId && isReviewable,
  });

  const acceptMutation = useMutation({
    mutationFn: () => acceptJob(jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      toast.success("Migration accepted.");
    },
    onError: () => toast.error("Could not accept migration. Please try again."),
  });

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function saveOverride(blockId: string, override: BlockOverride): void {
    if (saveTimerRef.current !== null) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      setSavingBlockId(blockId);
      void patchJobPlan(jobId, {
        block_overrides: [override],
      } satisfies PatchPlanRequest).finally(() => setSavingBlockId(null));
    }, 500);
  }

  function handleStrategyChange(blockId: string, value: string): void {
    const current = overrides[blockId] ?? { block_id: blockId };
    const updated: BlockOverride = {
      ...current,
      block_id: blockId,
      strategy: value,
    };
    setOverrides((prev) => ({ ...prev, [blockId]: updated }));
    saveOverride(blockId, updated);
  }

  function handleRiskChange(blockId: string, value: string): void {
    const current = overrides[blockId] ?? { block_id: blockId };
    const updated: BlockOverride = {
      ...current,
      block_id: blockId,
      risk: value,
    };
    setOverrides((prev) => ({ ...prev, [blockId]: updated }));
    saveOverride(blockId, updated);
  }

  function handleNoteChange(blockId: string, value: string): void {
    const current = overrides[blockId] ?? { block_id: blockId };
    const updated: BlockOverride = {
      ...current,
      block_id: blockId,
      note: value,
    };
    setOverrides((prev) => ({ ...prev, [blockId]: updated }));
    saveOverride(blockId, updated);
  }

  const isProposed = jobStatus === "proposed";

  if (!isReviewable) {
    return (
      <p className="text-sm text-muted-foreground">
        Migration plan available once migration completes.
      </p>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading plan…
      </div>
    );
  }

  if (!data) {
    return (
      <p className="text-sm text-muted-foreground">
        No migration plan available for this job.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <ReconSummaryCard report={report} />

      {isProposed && (
        <Button
          onClick={() => acceptMutation.mutate()}
          disabled={acceptMutation.isPending}
          className="w-full"
        >
          {acceptMutation.isPending ? "Accepting…" : "Accept migration"}
        </Button>
      )}
      {jobStatus === "accepted" && (
        <p className="text-sm text-emerald-600 font-medium">
          ✓ Migration accepted
        </p>
      )}

      {/* Summary card */}
      <div className="rounded-lg border border-border bg-card p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-semibold px-2 py-0.5 rounded-full ${RISK_BADGE[data.overall_risk]}`}
          >
            {data.overall_risk.toUpperCase()} RISK
          </span>
        </div>
        <p className="text-sm text-foreground">{data.summary}</p>
      </div>

      {/* Blocks requiring manual review */}
      {data.recommended_review_blocks.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">
            Blocks requiring manual review
          </h3>
          <div className="flex flex-wrap gap-2">
            {data.recommended_review_blocks.map((bid) => (
              <span
                key={bid}
                className="font-mono text-xs px-2 py-1 rounded bg-amber-50 border border-amber-200 text-amber-800"
              >
                {bid}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Cross-file dependencies */}
      {data.cross_file_dependencies.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Cross-file dependencies</h3>
          <ul className="text-sm space-y-1 list-disc list-inside text-muted-foreground">
            {data.cross_file_dependencies.map((dep, i) => (
              <li key={i}>{dep}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Block plan table */}
      {data.block_plans.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">Block plan</h3>
          <BlockPlanTable
            blockPlans={data.block_plans}
            isProposed={isProposed}
            overrides={overrides}
            savingBlockId={savingBlockId}
            onStrategyChange={handleStrategyChange}
            onRiskChange={handleRiskChange}
            onNoteChange={handleNoteChange}
          />
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
        <h3 className="text-sm font-semibold mb-2 shrink-0">
          Reconciliation report
        </h3>
        <div className="flex-1 overflow-y-auto">
          <TiptapEditor content={reportHtml} readOnly={false} />
        </div>
      </div>
      <div className="flex flex-col flex-1 min-w-0">
        <h3 className="text-sm font-semibold mb-2 shrink-0">
          Migration summary
        </h3>
        <div className="flex-1 overflow-y-auto">
          {docData?.doc ? (
            <TiptapEditor
              content={String(marked.parse(extractMarkdown(docData.doc)))}
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
// History tab
// ---------------------------------------------------------------------------

function HistoryTab({ jobId }: { jobId: string }): React.ReactElement {
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["job", jobId, "history"],
    queryFn: () => getJobHistory(jobId),
    enabled: !!jobId,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading history…
      </div>
    );
  }

  if (!data || data.entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No history available.</p>
    );
  }

  return (
    <div className="relative space-y-0 pl-8">
      {/* Vertical line */}
      <div className="absolute left-3 top-3 bottom-3 w-px bg-border" />

      {data.entries.map((entry: JobHistoryEntry, idx: number) => {
        const isAgent = entry.trigger === "agent";
        const label =
          entry.trigger === "agent"
            ? "Agent migration"
            : entry.trigger === "human-refine"
              ? "Refined by reviewer"
              : "Re-reconciled by reviewer";

        const statusColor =
          entry.status === "accepted"
            ? "text-emerald-600"
            : entry.status === "failed"
              ? "text-red-500"
              : entry.status === "proposed" || entry.status === "done"
                ? "text-amber-600"
                : "text-muted-foreground";

        return (
          <div key={entry.job_id} className="relative pb-6 last:pb-0">
            {/* Node */}
            <div className="absolute -left-5 top-1 flex h-6 w-6 items-center justify-center rounded-full border-2 border-border bg-background">
              {isAgent ? (
                <Bot size={12} className="text-blue-500" />
              ) : (
                <User size={12} className="text-violet-500" />
              )}
            </div>

            <div
              className={cn(
                "ml-2 rounded-lg border p-3 space-y-1 transition-colors",
                entry.is_current
                  ? "border-primary bg-primary/5"
                  : "border-border bg-card cursor-pointer hover:bg-muted/50",
              )}
              onClick={() => {
                if (!entry.is_current) navigate(`/jobs/${entry.job_id}`);
              }}
              role={entry.is_current ? undefined : "button"}
              tabIndex={entry.is_current ? undefined : 0}
              onKeyDown={(e) => {
                if (!entry.is_current && (e.key === "Enter" || e.key === " ")) {
                  e.preventDefault();
                  navigate(`/jobs/${entry.job_id}`);
                }
              }}
              aria-label={
                entry.is_current ? undefined : `Go to version ${idx + 1}`
              }
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-foreground">
                  {label}
                </span>
                {entry.is_current && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary font-semibold">
                    current
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className={`font-medium ${statusColor}`}>
                  {STATUS_LABEL[entry.status] ?? entry.status}
                </span>
                <span>·</span>
                <span>{new Date(entry.created_at).toLocaleString()}</span>
              </div>
              <p className="text-[11px] font-mono text-muted-foreground/70 truncate">
                {entry.job_id}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
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
      q.state.data?.status !== undefined &&
      POLLING_STATUSES.includes(q.state.data.status)
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
      <Tabs defaultValue="plan">
        <TabsList>
          <TabsTrigger value="plan">Plan</TabsTrigger>
          <TabsTrigger value="editor">Editor</TabsTrigger>
          <TabsTrigger value="report">Report</TabsTrigger>
          <TabsTrigger value="lineage">Lineage</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="plan" className="mt-4">
          <PlanTab
            jobId={id}
            isReviewable={
              job?.status === "proposed" || job?.status === "accepted"
            }
            jobStatus={job?.status ?? "queued"}
            report={job?.report ?? null}
          />
        </TabsContent>

        <TabsContent value="editor" className="mt-4">
          <EditorTab
            jobId={id}
            initialCode={job?.python_code ?? ""}
            generatedFiles={job?.generated_files ?? null}
          />
        </TabsContent>

        <TabsContent value="report" className="mt-4">
          <ReportTab
            jobId={id}
            report={job?.report ?? null}
            isDone={job?.status === "proposed" || job?.status === "accepted"}
          />
        </TabsContent>

        <TabsContent value="lineage" className="mt-4">
          <LineageTab jobId={id} />
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <HistoryTab jobId={id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
