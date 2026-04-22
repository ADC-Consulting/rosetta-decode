import { getJobChangelog, getJobSources } from "@/api/jobs";
import type { ChangelogEntry } from "@/api/types";
import FileTree from "@/components/FileTree";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { Editor } from "@monaco-editor/react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Lock, Moon, Pencil, Sun } from "lucide-react";
import type { editor } from "monaco-editor";
import { Suspense, useRef, useState } from "react";
import { registerSasLanguage } from "./registerSasLanguage";

export default function EditorTab({
  jobId,
  generatedFiles,
  onGeneratedFilesChange,
  code,
  setCode,
}: {
  jobId: string;
  generatedFiles: Record<string, string> | null;
  onGeneratedFilesChange?: (gf: Record<string, string>) => void;
  code: string;
  setCode: (code: string) => void;
}): React.ReactElement {
  const [editorDark, setEditorDark] = useState(false);
  const [pythonEditable, setPythonEditable] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const pythonEditorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoTheme = editorDark
    ? { sas: "sas-dark", python: "vs-dark" }
    : { sas: "sas-light", python: "vs" };
  const [selectedSasKey, setSelectedSasKey] = useState<string>("");

  const { data: sources, isLoading } = useQuery({
    queryKey: ["job", jobId, "sources"],
    queryFn: () => getJobSources(jobId),
    enabled: !!jobId,
  });

  const { data: changelog } = useQuery({
    queryKey: ["job", jobId, "changelog"],
    queryFn: () => getJobChangelog(jobId),
    enabled: !!jobId && showHistory,
  });

  const allPaths = sources ? Object.keys(sources.sources) : [];
  const sasKeys = allPaths.filter((k) => k.endsWith(".sas"));
  const effectiveSasKey = selectedSasKey || sasKeys[0] || "";
  const sasSource =
    effectiveSasKey && sources ? (sources.sources[effectiveSasKey] ?? "") : "";

  const pyKeyForSelected: string | null = effectiveSasKey
    ? (effectiveSasKey.split("/").pop() ?? effectiveSasKey).replace(
        /\.sas$/i,
        ".py",
      )
    : null;
  const perFileCode: string | null =
    generatedFiles && pyKeyForSelected
      ? (generatedFiles[pyKeyForSelected] ?? null)
      : null;
  const rightCode = perFileCode ?? code;
  const rightReadOnly = !pythonEditable;
  // eslint-disable-next-line react-hooks/purity
  const renderNow = Date.now();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading sources…
      </div>
    );
  }

  const breadcrumbParts = effectiveSasKey ? effectiveSasKey.split("/") : [];

  return (
    <div className="h-full min-h-0 flex flex-col space-y-4 pb-6">
      <div className="flex justify-end gap-2 shrink-0">
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger
              aria-label={
                pythonEditable
                  ? "Lock Python editor (read-only)"
                  : "Unlock Python editor (editable)"
              }
              onClick={() => setPythonEditable((v) => !v)}
              className={cn(
                "flex items-center text-xs transition-colors cursor-pointer border rounded p-1.5",
                pythonEditable
                  ? "border-primary text-primary hover:bg-primary/10"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {pythonEditable ? <Pencil size={14} /> : <Lock size={14} />}
            </TooltipTrigger>
            <TooltipContent side="top">
              {pythonEditable ? "Lock Python editor" : "Edit Python"}
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger
              aria-label={
                editorDark
                  ? "Switch editor to light theme"
                  : "Switch editor to dark theme"
              }
              onClick={() => setEditorDark((d) => !d)}
              className="flex items-center text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer border border-border rounded p-1.5"
            >
              {editorDark ? <Sun size={14} /> : <Moon size={14} />}
            </TooltipTrigger>
            <TooltipContent side="top">
              {editorDark ? "Light theme" : "Dark theme"}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <ResizablePanelGroup
        id="editor-panel-group"
        orientation="horizontal"
        className="rounded-md overflow-hidden flex-1 min-h-0"
        style={{ border: editorDark ? "1px solid #3e3e3e" : "1px solid var(--border)" }}
      >
        <ResizablePanel defaultSize="15%" minSize="10%" maxSize="30%">
          <div
            className="flex flex-col h-full"
            style={{ background: editorDark ? "#1e1e1e" : "#fafafa" }}
          >
            <div
              className="h-8 flex items-center px-3 text-[10px] font-semibold tracking-widest uppercase shrink-0"
              style={{
                background: editorDark ? "#1e1e1e" : "#fafafa",
                color: editorDark ? "#858585" : undefined,
                borderBottom: editorDark ? "1px solid #3e3e3e" : "1px solid var(--border)",
              }}
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

        <ResizablePanel defaultSize="78%">
          <ResizablePanelGroup orientation="horizontal">
            <ResizablePanel defaultSize="50%">
              <div className="flex flex-col h-full">
                <div
                  className="h-8 px-3 text-xs font-medium shrink-0 flex items-center"
                  style={{
                    background: editorDark ? "#1e1e1e" : "#fafafa",
                    color: editorDark ? "#858585" : undefined,
                    borderBottom: editorDark ? "1px solid #3e3e3e" : "1px solid var(--border)",
                  }}
                >
                  SAS Source
                  {effectiveSasKey && (
                    <span className="ml-2 text-[11px]" style={{ opacity: 0.5 }}>
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
                      key={`sas-${effectiveSasKey}`}
                      height="100%"
                      defaultValue={sasSource}
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

            <ResizablePanel defaultSize="50%">
              <div className="flex flex-col h-full">
                <div
                  className="h-8 px-3 text-xs font-medium shrink-0 flex items-center gap-2"
                  style={{
                    background: editorDark ? "#1e1e1e" : "#fafafa",
                    color: editorDark ? "#858585" : undefined,
                    borderBottom: editorDark ? "1px solid #3e3e3e" : "1px solid var(--border)",
                  }}
                >
                  <span>Generated Python</span>
                  {breadcrumbParts.length > 0 && (
                    <span className="text-[11px]" style={{ opacity: 0.5 }}>
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
                    key={`py-${effectiveSasKey || "default"}`}
                    height="100%"
                    defaultValue={rightCode}
                    language="python"
                    theme={monacoTheme.python}
                    loading={
                      <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                        Loading…
                      </div>
                    }
                    onMount={(ed) => {
                      pythonEditorRef.current = ed;
                    }}
                    onChange={(value) => {
                      if (rightReadOnly) return;
                      const next = value ?? "";
                      if (perFileCode !== null && pyKeyForSelected) {
                        onGeneratedFilesChange?.({
                          ...(generatedFiles ?? {}),
                          [pyKeyForSelected]: next,
                        });
                      } else {
                        setCode(next);
                      }
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

      {/* History panel */}
      <div className="shrink-0 border-t border-border">
        <button
          onClick={() => setShowHistory((v) => !v)}
          className="flex items-center gap-1.5 w-full px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer"
          aria-expanded={showHistory}
        >
          {showHistory ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {showHistory ? "Hide history" : "Show history"}
        </button>
        {showHistory && (
          <div className="max-h-56 overflow-y-auto divide-y divide-border">
            {!changelog && (
              <p className="px-3 py-3 text-xs text-muted-foreground">
                Loading…
              </p>
            )}
            {changelog && changelog.entries.length === 0 && (
              <p className="px-3 py-3 text-xs text-muted-foreground">
                No history yet.
              </p>
            )}
            {changelog &&
              [...changelog.entries]
                .sort(
                  (a: ChangelogEntry, b: ChangelogEntry) =>
                    new Date(b.created_at).getTime() -
                    new Date(a.created_at).getTime(),
                )
                .map((entry: ChangelogEntry) => {
                  const isHuman =
                    entry.trigger === "human-refine" ||
                    entry.trigger === "restore";
                  const icon = isHuman ? "👤" : "🤖";
                  const shortBlock = entry.block_id.replace(/:\d+$/, "");
                  const diffMs =
                    renderNow - new Date(entry.created_at).getTime();
                  const diffMin = Math.floor(diffMs / 60_000);
                  const relTime =
                    diffMin < 1
                      ? "just now"
                      : diffMin < 60
                        ? `${diffMin}m ago`
                        : diffMin < 1440
                          ? `${Math.floor(diffMin / 60)}h ago`
                          : `${Math.floor(diffMin / 1440)}d ago`;
                  return (
                    <div
                      key={entry.id}
                      className="flex items-center gap-2 px-3 py-2 text-xs hover:bg-muted/30"
                    >
                      <span aria-hidden>{icon}</span>
                      <span className="font-mono text-muted-foreground truncate max-w-40">
                        {shortBlock}
                      </span>
                      {isHuman && (
                        <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold bg-amber-100 text-amber-800">
                          User modified
                        </span>
                      )}
                      {entry.notes && (
                        <span className="text-muted-foreground/70 truncate max-w-30">
                          {entry.notes}
                        </span>
                      )}
                      <span className="ml-auto text-muted-foreground/60 tabular-nums shrink-0">
                        {relTime}
                      </span>
                    </div>
                  );
                })}
          </div>
        )}
      </div>
    </div>
  );
}
