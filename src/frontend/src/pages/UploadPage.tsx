import { getJob } from "@/api/jobs";
import { submitMigration } from "@/api/migrate";
import { Button } from "@/components/ui/button";
import { useUploadState } from "@/context/UploadStateContext";
import { cn } from "@/lib/utils";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Archive,
  ChevronDown,
  ChevronRight,
  ClipboardCopy,
  Database,
  ExternalLink,
  File,
  FileCode2,
  FileSpreadsheet,
  Folder,
  FolderOpen,
  ScrollText,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ACCEPTED_EXTS = [
  ".csv",
  ".log",
  ".sas",
  ".sas7bdat",
  ".xls",
  ".xlsx",
  ".zip",
] as const;

type AcceptedExt = (typeof ACCEPTED_EXTS)[number] | "";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fileExt(name: string): AcceptedExt {
  const lower = name.toLowerCase();
  for (const ext of ACCEPTED_EXTS) {
    if (lower.endsWith(ext)) return ext;
  }
  return "";
}

/** Strip the top-level parent folder from a zip entry path. */
function stripTopFolder(path: string): string {
  const idx = path.indexOf("/");
  if (idx === -1) return path;
  return path.slice(idx + 1);
}

function FileIcon({ ext, className }: { ext: string; className?: string }) {
  const cls = cn("shrink-0", className ?? "h-4 w-4");
  if (ext === ".sas") return <FileCode2 className={cls} />;
  if (ext === ".sas7bdat") return <Database className={cls} />;
  if (ext === ".xls" || ext === ".xlsx" || ext === ".csv")
    return <FileSpreadsheet className={cls} />;
  if (ext === ".log") return <ScrollText className={cls} />;
  return <File className={cls} />;
}

function TypeBadge({ ext }: { ext: string }) {
  if (ext === ".sas")
    return (
      <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
        SAS source
      </span>
    );
  if (ext === ".sas7bdat")
    return (
      <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-400">
        Dataset
      </span>
    );
  if (ext === ".zip")
    return (
      <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-400">
        Zip archive
      </span>
    );
  if (ext === ".log" || ext === ".csv" || ext === ".xls" || ext === ".xlsx")
    return (
      <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">
        Supporting
      </span>
    );
  return (
    <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-destructive/10 text-destructive">
      Unsupported
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "queued")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
        Queued
      </span>
    );
  if (status === "running")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400">
        <span
          className="h-2 w-2 rounded-full bg-blue-500 animate-pulse"
          aria-hidden="true"
        />
        Running…
      </span>
    );
  if (status === "done")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
        Done
      </span>
    );
  if (status === "failed")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium bg-destructive/10 text-destructive">
        Failed
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Zip tree helpers
// ---------------------------------------------------------------------------

type TreeNode = {
  name: string;
  /** Full entry path as stored in zipData.entries (for files only). Empty for dirs. */
  fullPath: string;
  /** Display path relative to the stripped root (used for folder keys). */
  displayPath: string;
  isDir: boolean;
  children: TreeNode[];
};

function buildTree(entries: string[]): TreeNode {
  const root: TreeNode = {
    name: "",
    fullPath: "",
    displayPath: "",
    isDir: true,
    children: [],
  };

  for (const fullPath of entries) {
    const display = stripTopFolder(fullPath);
    const parts = display.split("/").filter(Boolean);
    if (parts.length === 0) continue;

    let node = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLeaf = i === parts.length - 1;
      let child = node.children.find((c) => c.name === part);
      if (!child) {
        child = {
          name: part,
          fullPath: isLeaf ? fullPath : "",
          displayPath: parts.slice(0, i + 1).join("/"),
          isDir: !isLeaf,
          children: [],
        };
        node.children.push(child);
      }
      node = child;
    }
  }

  // Sort: directories first, then alphabetical
  const sortRec = (n: TreeNode) => {
    n.children.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    n.children.forEach(sortRec);
  };
  sortRec(root);

  return root;
}

/** Collect all leaf fullPaths under a node. */
function collectLeafPaths(node: TreeNode): string[] {
  if (!node.isDir) return node.fullPath ? [node.fullPath] : [];
  return node.children.flatMap(collectLeafPaths);
}

// ---------------------------------------------------------------------------
// Tree row component
// ---------------------------------------------------------------------------

function TreeRow({
  node,
  depth,
  excluded,
  openDirs,
  toggleDir,
  onRemoveFile,
  onRemoveDir,
}: {
  node: TreeNode;
  depth: number;
  excluded: Set<string>;
  openDirs: Set<string>;
  toggleDir: (key: string) => void;
  onRemoveFile: (fullPath: string) => void;
  onRemoveDir: (node: TreeNode) => void;
}) {
  // 1rem per depth level, plus a base left padding
  const indent = { paddingLeft: `${0.75 + depth * 1}rem` };

  if (node.isDir) {
    const isOpen = openDirs.has(node.displayPath);
    const visibleLeafCount = collectLeafPaths(node).filter(
      (p) => !excluded.has(p),
    ).length;
    if (visibleLeafCount === 0) return null;

    return (
      <>
        <li className="flex items-center justify-between pr-3 py-1 text-sm border-b border-border/50 last:border-b-0">
          <button
            type="button"
            onClick={() => toggleDir(node.displayPath)}
            style={indent}
            className="flex items-center gap-2 min-w-0 flex-1 text-left cursor-pointer hover:text-primary transition-colors"
            aria-expanded={isOpen}
            aria-label={`${isOpen ? "Collapse" : "Expand"} ${node.name}`}
          >
            {isOpen ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            )}
            {isOpen ? (
              <FolderOpen className="h-4 w-4 shrink-0 text-muted-foreground" />
            ) : (
              <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
            )}
            <span className="truncate text-foreground">{node.name}</span>
            <span className="text-[10px] text-muted-foreground">
              {visibleLeafCount} {visibleLeafCount === 1 ? "file" : "files"}
            </span>
          </button>
          <button
            type="button"
            onClick={() => onRemoveDir(node)}
            aria-label={`Remove folder ${node.name}`}
            className="ml-2 shrink-0 cursor-pointer rounded-sm text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            ✕
          </button>
        </li>
        {isOpen &&
          node.children.map((child) => (
            <TreeRow
              key={child.displayPath || child.fullPath}
              node={child}
              depth={depth + 1}
              excluded={excluded}
              openDirs={openDirs}
              toggleDir={toggleDir}
              onRemoveFile={onRemoveFile}
              onRemoveDir={onRemoveDir}
            />
          ))}
      </>
    );
  }

  // File leaf
  if (excluded.has(node.fullPath)) return null;
  const ext = fileExt(node.name);

  return (
    <li className="flex items-center justify-between pr-3 py-1 text-sm border-b border-border/50 last:border-b-0">
      <span
        style={indent}
        className="flex items-center gap-2 min-w-0 text-muted-foreground"
      >
        {/* Spacer to align with the folder chevron column */}
        <span className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <FileIcon ext={ext} className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">{node.name}</span>
        {ext === "" && (
          <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-destructive/10 text-destructive">
            Unsupported
          </span>
        )}
      </span>
      <button
        type="button"
        onClick={() => onRemoveFile(node.fullPath)}
        aria-label={`Remove ${node.name}`}
        className="ml-2 shrink-0 cursor-pointer text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        ✕
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function UploadPage() {
  const navigate = useNavigate();
  const {
    phase,
    setPhase,
    files,
    zipEntries,
    manifest,
    dragOver,
    setDragOver,
    migrationName,
    setMigrationName,
    applyFiles,
    removeFile,
    toggleZipExpanded,
    excludeZipEntry,
    setManifest,
    reset,
    newMigration,
    inputRef,
  } = useUploadState();

  // Per-zip open-folder state: key = `${zipName}::${displayPath}`
  const [openDirs, setOpenDirs] = useState<Set<string>>(new Set());
  const toggleDir = (zipName: string, displayPath: string) => {
    setOpenDirs((prev) => {
      const next = new Set(prev);
      const key = `${zipName}::${displayPath}`;
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Derived — staging
  const sasFiles = files.filter((f) => f.name.toLowerCase().endsWith(".sas"));
  const refDataset =
    files.findLast((f) => f.name.toLowerCase().endsWith(".sas7bdat")) ??
    undefined;
  const zipFile =
    files.findLast((f) => f.name.toLowerCase().endsWith(".zip")) ?? undefined;
  const unknownFiles = files.filter((f) => fileExt(f.name) === "");
  const validationError: string | null =
    unknownFiles.length > 0
      ? `Unsupported file(s): ${unknownFiles.map((f) => f.name).join(", ")}`
      : null;

  // Job polling
  const jobId = manifest?.job_id ?? null;
  const { data: jobStatus } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "done" || s === "failed" ? false : 3000;
    },
  });

  const mutation = useMutation({
    mutationFn: () => submitMigration(sasFiles, refDataset, zipFile, migrationName),
    onSuccess: (data) => {
      setManifest(data);
      setPhase("submitted");
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Something went wrong while submitting the migration. Please try again.");
    },
  });

  const isPending = mutation.status === "pending";
  const submitDisabled =
    files.length === 0 || unknownFiles.length > 0 || isPending || migrationName.trim() === "";

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    applyFiles(Array.from(e.target.files ?? []));
    e.target.value = "";
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    applyFiles(Array.from(e.dataTransfer.files));
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (submitDisabled) return;
    mutation.mutate();
  }

  function copyText(text: string) {
    void navigator.clipboard.writeText(text);
  }

  const isDone = jobStatus?.status === "done";
  const isFailed = jobStatus?.status === "failed";

  useEffect(() => {
    if (isFailed && jobStatus?.error) {
      toast.error("The migration could not be completed. Please check your files and try again.");
    }
  }, [isFailed, jobStatus?.error]);

  // ---------------------------------------------------------------------------
  // File list render
  // ---------------------------------------------------------------------------

  function renderFileList() {
    if (files.length === 0) return null;

    return (
      <ul className="space-y-1.5" aria-label="Selected files">
        {files.map((f) => {
          const ext = fileExt(f.name);
          const isZip = ext === ".zip";
          const zipData = zipEntries.get(f.name);

          if (isZip) {
            return (
              <ZipCard
                key={f.name}
                fileName={f.name}
                ext={ext}
                zipData={zipData}
                openDirs={openDirs}
                toggleDir={(displayPath) => toggleDir(f.name, displayPath)}
                onToggleExpanded={() => toggleZipExpanded(f.name)}
                onRemoveZip={() => removeFile(f.name)}
                onExcludeEntry={(p) => excludeZipEntry(f.name, p)}
              />
            );
          }

          return (
            <li
              key={f.name}
              className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-1.5 text-sm"
            >
              <span className="flex items-center gap-2 min-w-0">
                {/* Leading spacer — matches the chevron slot on the zip card, keeping
                    icons/badges/names vertically aligned across all rows. */}
                <span className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <FileIcon
                  ext={ext}
                  className="h-4 w-4 shrink-0 text-muted-foreground"
                />
                <TypeBadge ext={ext} />
                <span className="truncate text-foreground">{f.name}</span>
              </span>
              <button
                type="button"
                onClick={() => removeFile(f.name)}
                aria-label={`Remove ${f.name}`}
                className="ml-2 shrink-0 cursor-pointer rounded-sm text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                ✕
              </button>
            </li>
          );
        })}
      </ul>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-xl font-semibold text-foreground">New Migration</h1>

      {/* ------------------------------------------------------------------ */}
      {/* Phase 2 — Job result card                                           */}
      {/* ------------------------------------------------------------------ */}
      {manifest !== null && (
        <div className="rounded-lg border border-border bg-background shadow-sm space-y-4 p-5">
          {isDone && (
            <Button
              type="button"
              onClick={() => navigate(`/jobs/${manifest.job_id}`)}
              className="w-full cursor-pointer"
              aria-label="Open full job details"
            >
              Open full details
              <ExternalLink className="ml-2 h-4 w-4" aria-hidden="true" />
            </Button>
          )}

          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <p className="text-sm font-semibold text-foreground">
                Migration submitted
              </p>
              {manifest.name && (
                <p className="text-base font-semibold text-foreground">{manifest.name}</p>
              )}
              <div className="flex items-center gap-2">
                <code className="font-mono text-xs text-muted-foreground truncate max-w-65">
                  {manifest.job_id}
                </code>
                <button
                  type="button"
                  onClick={() => copyText(manifest.job_id)}
                  aria-label="Copy job ID"
                  className="shrink-0 cursor-pointer text-muted-foreground hover:text-foreground transition-colors"
                >
                  <ClipboardCopy className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            <StatusBadge status={jobStatus?.status ?? "queued"} />
          </div>

          {isDone && (
            <>
              {jobStatus.python_code && (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      Generated Python (preview)
                    </p>
                    <button
                      type="button"
                      onClick={() => copyText(jobStatus.python_code ?? "")}
                      aria-label="Copy generated Python"
                      className="flex items-center gap-1 cursor-pointer text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <ClipboardCopy className="h-3 w-3" />
                      Copy
                    </button>
                  </div>
                  <pre className="rounded-md bg-zinc-950 dark:bg-zinc-900 text-zinc-100 text-xs font-mono p-3 overflow-x-auto max-h-48">
                    {jobStatus.python_code.split("\n").slice(0, 20).join("\n")}
                  </pre>
                </div>
              )}

              {jobStatus.report !== null && (
                <details className="group rounded-md border border-border">
                  <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors select-none">
                    <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" />
                    Reconciliation report
                  </summary>
                  <pre className="border-t border-border px-3 py-2 text-xs font-mono text-foreground overflow-x-auto max-h-64">
                    {JSON.stringify(jobStatus.report, null, 2)}
                  </pre>
                </details>
              )}
            </>
          )}


          <div className="flex items-center gap-3 pt-1 border-t border-border">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={newMigration}
              className="cursor-pointer"
              aria-label="Start another migration without clearing this result"
            >
              Start another
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={reset}
              aria-label="Accept result and clear this session"
              className="cursor-pointer text-muted-foreground hover:text-foreground"
            >
              Accept & clear
            </Button>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Phase 1 — Staging form                                              */}
      {/* ------------------------------------------------------------------ */}
      {phase === "staging" && (
        <form onSubmit={handleSubmit} noValidate className="space-y-6">
          <input
            ref={inputRef}
            id="file-input"
            type="file"
            accept=".sas,.sas7bdat,.zip,.log,.csv,.xls,.xlsx"
            multiple
            className="sr-only"
            aria-hidden="true"
            tabIndex={-1}
            onChange={handleInputChange}
          />

          <div className="space-y-1.5">
            <label htmlFor="migration-name" className="text-sm font-medium text-foreground">
              Migration name
            </label>
            <input
              id="migration-name"
              type="text"
              required
              value={migrationName}
              onChange={(e) => setMigrationName(e.target.value)}
              placeholder="e.g. Q4 claims pipeline"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>

          <div
            role="button"
            tabIndex={0}
            aria-label="Select files — .sas, .sas7bdat, or .zip"
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={cn(
              "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10",
              "cursor-pointer select-none transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              dragOver
                ? "border-primary bg-primary/5"
                : "border-border bg-muted/30 hover:border-primary/50 hover:bg-muted/50",
            )}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-8 w-8 text-muted-foreground"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
              />
            </svg>
            <p className="text-sm font-medium text-foreground">
              Drop files here or{" "}
              <span className="text-primary underline underline-offset-2">
                browse
              </span>
            </p>
            <p className="text-xs text-muted-foreground">
              Accepted formats: .csv, .log, .sas, .sas7bdat, .xls, .xlsx, .zip
            </p>
          </div>

          <Button
            type="submit"
            disabled={submitDisabled}
            aria-busy={isPending}
            className="cursor-pointer"
          >
            {isPending ? "Submitting…" : "Migrate"}
          </Button>

          {renderFileList()}

          {validationError && (
            <p role="alert" className="text-sm text-destructive">
              {validationError}. Accepted: .csv, .log, .sas, .sas7bdat, .xls,
              .xlsx, .zip
            </p>
          )}
        </form>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ZipCard — extracted to keep hooks tidy
// ---------------------------------------------------------------------------

type ZipEntryData = {
  expanded?: boolean;
  loading?: boolean;
  entries: string[];
  excluded: Set<string>;
};

function ZipCard({
  fileName,
  ext,
  zipData,
  openDirs,
  toggleDir,
  onToggleExpanded,
  onRemoveZip,
  onExcludeEntry,
}: {
  fileName: string;
  ext: string;
  zipData: ZipEntryData | undefined;
  openDirs: Set<string>;
  toggleDir: (displayPath: string) => void;
  onToggleExpanded: () => void;
  onRemoveZip: () => void;
  onExcludeEntry: (fullPath: string) => void;
}) {
  const isExpanded = zipData?.expanded === true;

  const tree = useMemo(
    () => (zipData ? buildTree(zipData.entries) : null),
    [zipData],
  );

  const excluded = zipData?.excluded ?? new Set<string>();
  const visibleCount = zipData
    ? zipData.entries.length - zipData.excluded.size
    : 0;

  // Build a Set of open folders that belong to THIS zip, stripped back to plain
  // displayPaths, so TreeRow can work with unscoped keys.
  const prefix = `${fileName}::`;
  const localOpenDirs = useMemo(() => {
    const s = new Set<string>();
    for (const key of openDirs) {
      if (key.startsWith(prefix)) s.add(key.slice(prefix.length));
    }
    return s;
  }, [openDirs, prefix]);

  const handleRemoveDir = (node: TreeNode) => {
    for (const p of collectLeafPaths(node)) onExcludeEntry(p);
  };

  return (
    <li className="rounded-md border border-border bg-background">
      <div className="flex items-center justify-between px-3 py-1.5 text-sm">
        <button
          type="button"
          onClick={onToggleExpanded}
          className="flex items-center gap-2 min-w-0 flex-1 text-left cursor-pointer hover:text-primary transition-colors"
          aria-expanded={isExpanded}
          aria-label={`${isExpanded ? "Collapse" : "Expand"} ${fileName}`}
        >
          {isExpanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )}
          <Archive
            className="h-4 w-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
          <TypeBadge ext={ext} />
          <span className="truncate text-foreground">{fileName}</span>
          {zipData?.loading && (
            <span className="text-[10px] text-muted-foreground animate-pulse">
              parsing…
            </span>
          )}
          {zipData && !zipData.loading && (
            <span className="text-[10px] text-muted-foreground">
              {visibleCount} {visibleCount === 1 ? "file" : "files"}
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={onRemoveZip}
          aria-label={`Remove ${fileName}`}
          className="ml-2 shrink-0 cursor-pointer rounded-sm text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          ✕
        </button>
      </div>

      {isExpanded && tree && tree.children.length > 0 && (
        <ul
          className="border-t border-border"
          aria-label={`Contents of ${fileName}`}
        >
          {tree.children.map((child) => (
            <TreeRow
              key={child.displayPath || child.fullPath}
              node={child}
              depth={0}
              excluded={excluded}
              openDirs={localOpenDirs}
              toggleDir={toggleDir}
              onRemoveFile={onExcludeEntry}
              onRemoveDir={handleRemoveDir}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
