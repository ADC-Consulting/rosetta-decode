import { downloadJob, getJob, listJobs } from "@/api/jobs";
import { submitMigration } from "@/api/migrate";
import type { JobStatusValue, JobSummary } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useUploadState } from "@/context/UploadStateContext";
import { cn } from "@/lib/utils";
import { STATUS_LABEL } from "@/pages/JobDetailPage";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { toast } from "sonner";

// ---------------------------------------------------------------------------
// Upload helpers (mirrors UploadPage internals)
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

function fileExt(name: string): AcceptedExt {
  const lower = name.toLowerCase();
  for (const ext of ACCEPTED_EXTS) {
    if (lower.endsWith(ext)) return ext;
  }
  return "";
}

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

function UploadStatusBadge({ status }: { status: string }) {
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
  if (status === "proposed" || status === "done")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">
        Under Review
      </span>
    );
  if (status === "accepted")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
        Accepted
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
  fullPath: string;
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

function collectLeafPaths(node: TreeNode): string[] {
  if (!node.isDir) return node.fullPath ? [node.fullPath] : [];
  return node.children.flatMap(collectLeafPaths);
}

// ---------------------------------------------------------------------------
// TreeRow
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

  if (excluded.has(node.fullPath)) return null;
  const ext = fileExt(node.name);

  return (
    <li className="flex items-center justify-between pr-3 py-1 text-sm border-b border-border/50 last:border-b-0">
      <span
        style={indent}
        className="flex items-center gap-2 min-w-0 text-muted-foreground"
      >
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
// ZipCard
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

// ---------------------------------------------------------------------------
// TableStatus (jobs table)
// ---------------------------------------------------------------------------

const POLLING_STATUSES: JobStatusValue[] = ["queued", "running", "proposed"];

function TableStatus({
  status,
}: {
  status: JobStatusValue;
}): React.ReactElement {
  if (status === "accepted") {
    return (
      <span className="text-sm font-medium text-emerald-500">
        {STATUS_LABEL.accepted}
      </span>
    );
  }
  if (status === "proposed") {
    const gradient =
      "linear-gradient(90deg, #f59e0b 20%, #fef3c7 50%, #f59e0b 80%)";
    return (
      <>
        <style>{`@keyframes table-shimmer { from { background-position: 200% center; } to { background-position: -200% center; } }`}</style>
        <span
          className="text-sm font-medium"
          style={{
            display: "inline-block",
            backgroundImage: gradient,
            backgroundSize: "200% 100%",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
            animation: "table-shimmer 4s linear infinite",
          }}
        >
          Under Review
        </span>
      </>
    );
  }
  if (status === "failed") {
    return (
      <span className="text-sm font-medium text-red-500">
        {STATUS_LABEL.failed}
      </span>
    );
  }
  const gradient =
    status === "running"
      ? "linear-gradient(90deg, #93c5fd 20%, #eff6ff 50%, #93c5fd 80%)"
      : "linear-gradient(90deg, #94a3b8 20%, #e2e8f0 50%, #94a3b8 80%)";
  return (
    <>
      <style>{`@keyframes table-shimmer { from { background-position: 200% center; } to { background-position: -200% center; } }`}</style>
      <span
        className="text-sm font-medium"
        style={{
          display: "inline-block",
          backgroundImage: gradient,
          backgroundSize: "200% 100%",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
          backgroundClip: "text",
          animation: "table-shimmer 4s linear infinite",
        }}
      >
        {STATUS_LABEL[status]}
      </span>
    </>
  );
}

// ---------------------------------------------------------------------------
// JobsPage
// ---------------------------------------------------------------------------

export default function JobsPage(): React.ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // ── Jobs list query ───────────────────────────────────────────────────────

  const { data: jobs, isLoading } = useQuery<JobSummary[], Error>({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: (query) => {
      const list = query.state.data;
      if (!list) return false;
      return list.some((j) => POLLING_STATUSES.includes(j.status))
        ? 3000
        : false;
    },
  });

  // ── Dialog state ──────────────────────────────────────────────────────────

  const [uploadOpen, setUploadOpen] = useState<boolean>(false);

  // ── Upload state (from shared context) ───────────────────────────────────

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

  // Per-zip open-folder state
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

  // Job polling (upload result)
  const jobId = manifest?.job_id ?? null;
  const { data: jobStatus } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "accepted" || s === "failed" || s === "done" ? false : 3000;
    },
  });

  const mutation = useMutation({
    mutationFn: () =>
      submitMigration(sasFiles, refDataset, zipFile, migrationName),
    onSuccess: (data) => {
      setManifest(data);
      setPhase("submitted");
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
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

  const isAccepted = jobStatus?.status === "accepted";
  const isProposed =
    jobStatus?.status === "proposed" || jobStatus?.status === "done";
  const isFailed = jobStatus?.status === "failed";

  useEffect(() => {
    if (isFailed && jobStatus?.error) {
      toast.error(
        "The migration could not be completed. Please check your files and try again.",
      );
    }
  }, [isFailed, jobStatus?.error]);

  function handleDialogOpenChange(open: boolean) {
    if (!open) {
      reset();
      setOpenDirs(new Set());
    }
    setUploadOpen(open);
  }

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

  // ── File list render (upload dialog) ─────────────────────────────────────

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

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="px-6 py-8 overflow-y-auto flex-1 h-full">
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-foreground">Migrations</h1>
          <Button variant="outline" onClick={() => setUploadOpen(true)}>
            New migration
          </Button>
        </div>

        {isLoading && (
          <div className="flex items-center gap-3 text-muted-foreground py-4">
            <div
              aria-label="Loading jobs"
              className="size-5 rounded-full border-2 border-border border-t-foreground animate-spin"
            />
            <span className="text-sm">Loading…</span>
          </div>
        )}

        {!isLoading && jobs !== undefined && jobs.length === 0 && (
          <p className="text-sm text-muted-foreground py-4">
            No migrations yet. Click &ldquo;New migration&rdquo; to get started.
          </p>
        )}

        {!isLoading && jobs !== undefined && jobs.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm" aria-label="Migration jobs">
              <thead>
                <tr className="border-b border-border bg-muted text-muted-foreground text-left">
                  <th scope="col" className="px-4 py-2.5 font-medium w-[40%]">
                    Name
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium">
                    Files
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium">
                    Created
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium sr-only">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const isClickable =
                    job.status === "proposed" ||
                    job.status === "accepted" ||
                    job.status === "done";
                  return (
                    <tr
                      key={job.job_id}
                      onClick={() => {
                        if (isClickable) navigate(`/jobs/${job.job_id}`);
                      }}
                      role={isClickable ? "button" : undefined}
                      tabIndex={isClickable ? 0 : undefined}
                      aria-label={`${job.name ?? job.job_id.slice(0, 8)}, status ${STATUS_LABEL[job.status]}`}
                      aria-disabled={!isClickable}
                      onKeyDown={(e) => {
                        if (!isClickable) return;
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          navigate(`/jobs/${job.job_id}`);
                        }
                      }}
                      className={cn(
                        "border-b border-border last:border-0 transition-colors",
                        isClickable
                          ? "cursor-pointer hover:bg-muted/50"
                          : "cursor-default opacity-70",
                      )}
                    >
                      <td className="px-4 py-3 text-foreground font-medium">
                        {job.name ?? (
                          <span className="font-mono text-muted-foreground">
                            {job.job_id.slice(0, 8)}…
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <TableStatus status={job.status} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {job.file_count != null ? job.file_count : "—"}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {new Date(job.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {job.status === "accepted" && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => {
                              e.stopPropagation();
                              void downloadJob(job.job_id);
                            }}
                            aria-label={`Download results for job ${job.job_id.slice(0, 8)}`}
                          >
                            Download
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Upload Dialog ───────────────────────────────────────────────── */}
      <Dialog open={uploadOpen} onOpenChange={handleDialogOpenChange}>
        <DialogContent className="max-w-3xl w-[90vw] h-[85vh] overflow-y-auto flex flex-col">
          <DialogHeader>
            <DialogTitle>New Migration</DialogTitle>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto">
            <div className="max-w-lg mx-auto space-y-6 py-2">
              {/* Phase 2 — Job result card */}
              {manifest !== null && (
                <div className="rounded-lg border border-border bg-background shadow-sm space-y-4 p-5">
                  {(isAccepted || isProposed) && (
                    <Button
                      type="button"
                      onClick={() => navigate(`/jobs/${manifest.job_id}`)}
                      className="w-full cursor-pointer"
                      aria-label="Open full job details"
                    >
                      Open full details
                      <ExternalLink
                        className="ml-2 h-4 w-4"
                        aria-hidden="true"
                      />
                    </Button>
                  )}

                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      {(manifest.name ?? migrationName) ? (
                        <p className="text-base font-semibold text-foreground">
                          {manifest.name ?? migrationName}
                        </p>
                      ) : (
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
                      )}
                    </div>
                    <UploadStatusBadge status={jobStatus?.status ?? "queued"} />
                  </div>

                  <div className="flex items-center gap-3 pt-1 border-t border-border">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={newMigration}
                      className="cursor-pointer"
                      aria-label="Start another migration"
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

              {/* Phase 1 — Staging form */}
              {phase === "staging" && (
                <form onSubmit={handleSubmit} noValidate className="space-y-6">
                  <input
                    ref={inputRef}
                    id="file-input-dialog"
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
                      htmlFor="migration-name-dialog"
                      className="text-sm font-medium text-foreground"
                    >
                      Migration name
                    </label>
                    <input
                      id="migration-name-dialog"
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
                      Accepted formats: .csv, .log, .sas, .sas7bdat, .xls,
                      .xlsx, .zip
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
                      {validationError}. Accepted: .csv, .log, .sas, .sas7bdat,
                      .xls, .xlsx, .zip
                    </p>
                  )}
                </form>
              )}
            </div>
          </div>

          <DialogFooter showCloseButton={false}>
            <Button
              variant="outline"
              onClick={() => handleDialogOpenChange(false)}
            >
              {manifest !== null ? "Done" : "Cancel"}
            </Button>
            {manifest !== null && (
              <Button
                onClick={() => {
                  const id = manifest.job_id;
                  handleDialogOpenChange(false);
                  navigate(`/jobs/${id}`);
                }}
              >
                View Migration
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
