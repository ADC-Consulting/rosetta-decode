import { submitMigration } from "@/api/migrate";
import { Button } from "@/components/ui/button";
import { useUploadState } from "@/context/UploadStateContext";
import { cn } from "@/lib/utils";
import { useMutation } from "@tanstack/react-query";
import {
  Archive,
  ChevronDown,
  ChevronRight,
  Database,
  File,
  FileCode2,
  FileSpreadsheet,
  Folder,
  FolderOpen,
  ScrollText,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

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
    files,
    zipEntries,
    dragOver,
    setDragOver,
    migrationName,
    setMigrationName,
    applyFiles,
    removeFile,
    toggleZipExpanded,
    excludeZipEntry,
    inputRef,
  } = useUploadState();

  const [refCsvFile, setRefCsvFile] = useState<File | null>(null);

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

  const mutation = useMutation({
    mutationFn: () =>
      submitMigration(sasFiles, refDataset, zipFile, migrationName, refCsvFile),
    onSuccess: () => {
      navigate("/jobs");
    },
    onError: (err) => {
      toast.error(
        err instanceof Error
          ? err.message
          : "Something went wrong while submitting the migration. Please try again.",
      );
    },
  });

  const isPending = mutation.status === "pending";
  const submitDisabled =
    files.length === 0 ||
    unknownFiles.length > 0 ||
    isPending ||
    migrationName.trim() === "";

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    applyFiles(Array.from(e.target.files ?? []));
    e.target.value = "";
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files);
    const csvFiles = dropped.filter((f) => f.name.toLowerCase().endsWith(".csv"));
    const otherFiles = dropped.filter((f) => !f.name.toLowerCase().endsWith(".csv"));
    // If CSVs are dropped alongside SAS files (not inside a zip), treat the
    // last CSV as the ref output file rather than adding it to the main list.
    const hasSasOrOther = otherFiles.length > 0;
    if (csvFiles.length > 0 && hasSasOrOther) {
      setRefCsvFile(csvFiles[csvFiles.length - 1]);
      applyFiles(otherFiles);
    } else {
      applyFiles(dropped);
    }
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (submitDisabled) return;
    mutation.mutate();
  }


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
    <div className="max-w-200 mx-auto w-full px-6 py-2 overflow-y-auto flex-1 h-full">
      <div className="max-w-lg mx-auto space-y-6">
        <h1 className="text-xl font-semibold text-foreground">New Migration</h1>

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
              <label
                htmlFor="migration-name"
                className="text-sm font-medium text-foreground"
              >
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

            {/* ---------------------------------------------------------------- */}
            {/* Ref CSV zone                                                       */}
            {/* ---------------------------------------------------------------- */}
            <div className="space-y-1.5">
              <div>
                <p className="text-sm font-medium text-foreground">
                  Reference output{" "}
                  <span className="text-muted-foreground font-normal">(CSV)</span>
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  The expected final output of your SAS pipeline — used for reconciliation
                </p>
              </div>

              {refCsvFile ? (
                <div className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-1.5 text-sm w-fit max-w-full">
                  <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="truncate text-foreground text-xs">{refCsvFile.name}</span>
                  <button
                    type="button"
                    onClick={() => setRefCsvFile(null)}
                    aria-label="Remove reference CSV"
                    className="shrink-0 cursor-pointer rounded-sm text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <label
                  htmlFor="ref-csv-input"
                  className={cn(
                    "flex items-center gap-2 rounded-md border border-dashed border-border px-3 py-2",
                    "cursor-pointer text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground",
                    "transition-colors select-none w-fit",
                  )}
                >
                  <FileSpreadsheet className="h-3.5 w-3.5 shrink-0" aria-hidden />
                  <span>
                    Drop a CSV here or{" "}
                    <span className="text-primary underline underline-offset-2">browse</span>
                  </span>
                  <input
                    id="ref-csv-input"
                    type="file"
                    accept=".csv"
                    className="sr-only"
                    aria-hidden="true"
                    tabIndex={-1}
                    onChange={(e) => {
                      const f = e.target.files?.[0] ?? null;
                      setRefCsvFile(f);
                      e.target.value = "";
                    }}
                  />
                </label>
              )}
            </div>

            {renderFileList()}

            <Button
              type="submit"
              disabled={submitDisabled}
              aria-busy={isPending}
              className="cursor-pointer"
            >
              {isPending ? "Submitting…" : "Migrate"}
            </Button>

            {validationError && (
              <p role="alert" className="text-sm text-destructive">
                {validationError}. Accepted: .csv, .log, .sas, .sas7bdat, .xls,
                .xlsx, .zip
              </p>
            )}
          </form>
        )}
      </div>
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
