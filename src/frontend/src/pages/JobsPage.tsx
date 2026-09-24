import { downloadJob, getJob, listJobs } from "@/api/jobs";
import { submitMigration } from "@/api/migrate";
import LiveTraceDialog from "@/components/LiveTraceDialog";
import type { JobStatusValue, JobSummary } from "@/api/types";
import { Button } from "@/components/ui/button";
import { JOB_STATUS_TONE, TONE_TEXT_CLASS } from "@/components/JobDetail/status-colors";
import StatusChip from "@/components/JobDetail/StatusChip";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useUploadState } from "@/context/UploadStateContext";
import { cn } from "@/lib/utils";
import { STATUS_LABEL } from "@/pages/JobDetailPage";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Archive,
  Check,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  ClipboardCopy,
  Database,
  ExternalLink,
  File,
  FileCode2,
  FileSpreadsheet,
  Folder,
  FolderOpen,
  ScrollText,
  Search,
  Target,
  XCircle,
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
  const colorClass: Record<string, string> = {
    queued:       "bg-muted text-muted-foreground",
    running:      "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400",
    proposed:     "bg-[var(--tone-warning-bg)] text-[var(--tone-warning)]",
    under_review: "bg-[var(--tone-warning-bg)] text-[var(--tone-warning)]",
    accepted:     "bg-[var(--tone-success-bg)] text-[var(--tone-success)]",
    done:         "bg-[var(--tone-success-bg)] text-[var(--tone-success)]",
    failed:       "bg-destructive/10 text-destructive",
  };
  const label: Record<string, string> = {
    queued:       "Queued",
    running:      "Processing",
    proposed:     "Needs Review",
    under_review: "Needs Review",
    accepted:     "Accepted",
    done:         "Done",
    failed:       "Failed",
  };
  const pulse = ["queued", "running"].includes(status);
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${colorClass[status] ?? "bg-muted text-muted-foreground"}`}>
      {pulse && <span className="h-2 w-2 rounded-full bg-current animate-pulse" aria-hidden />}
      {label[status] ?? status}
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
  refTargetPath,
  onSetRefTarget,
}: {
  node: TreeNode;
  depth: number;
  excluded: Set<string>;
  openDirs: Set<string>;
  toggleDir: (key: string) => void;
  onRemoveFile: (fullPath: string) => void;
  onRemoveDir: (node: TreeNode) => void;
  refTargetPath: string | null;
  onSetRefTarget: (path: string | null) => void;
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
              refTargetPath={refTargetPath}
              onSetRefTarget={onSetRefTarget}
            />
          ))}
      </>
    );
  }

  if (excluded.has(node.fullPath)) return null;
  const ext = fileExt(node.name);
  const isEligible = ext === ".csv" || ext === ".sas7bdat";
  const isTarget = refTargetPath === node.fullPath;

  return (
    <li className="flex items-center justify-between pr-3 py-1 text-sm border-b border-border/50 last:border-b-0">
      <span
        style={indent}
        className="flex items-center gap-2 min-w-0 text-muted-foreground"
      >
        <span className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <FileIcon ext={ext} className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">{node.name}</span>
        {isTarget && (
          <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-[var(--tone-success-bg)] text-[var(--tone-success)]">
            Target
          </span>
        )}
        {ext === "" && (
          <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-destructive/10 text-destructive">
            Unsupported
          </span>
        )}
      </span>
      <span className="flex items-center gap-1 shrink-0">
        {isEligible && (
          <button
            type="button"
            onClick={() => onSetRefTarget(isTarget ? null : node.fullPath)}
            aria-label={isTarget ? "Unmark as reconciliation target" : "Mark as reconciliation target"}
            title={isTarget ? "Remove reconciliation target" : "Set as reconciliation target"}
            className={cn(
              "ml-1 shrink-0 cursor-pointer rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors",
              isTarget ? "text-primary" : "text-muted-foreground hover:text-primary",
            )}
          >
            <Target className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          type="button"
          onClick={() => onRemoveFile(node.fullPath)}
          aria-label={`Remove ${node.name}`}
          className="ml-1 shrink-0 cursor-pointer text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          ✕
        </button>
      </span>
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
  refTargetPath,
  onSetRefTarget,
}: {
  fileName: string;
  ext: string;
  zipData: ZipEntryData | undefined;
  openDirs: Set<string>;
  toggleDir: (displayPath: string) => void;
  onToggleExpanded: () => void;
  onRemoveZip: () => void;
  onExcludeEntry: (fullPath: string) => void;
  refTargetPath: string | null;
  onSetRefTarget: (path: string | null) => void;
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
              refTargetPath={refTargetPath}
              onSetRefTarget={onSetRefTarget}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// StatusCell (jobs table) — StatusChip + status icon, per the Manifest mockup
// ---------------------------------------------------------------------------

const POLLING_STATUSES: JobStatusValue[] = ["queued", "running", "proposed"];

/**
 * queued/running have no verdict yet, so their icon is a pulsing dot (mirrors the mockup's
 * `.pulse` running-row treatment) rather than a static glyph — preserves the in-progress visual
 * cue that the old shimmer-text `TableStatus` gave, now that the chip itself is static.
 */
function StatusCellIcon({ status }: { status: JobStatusValue }): React.ReactElement | null {
  if (status === "queued" || status === "running") {
    return (
      <span
        className="h-1.5 w-1.5 rounded-full bg-current animate-pulse"
        aria-hidden="true"
      />
    );
  }
  if (status === "proposed" || status === "under_review") {
    return <AlertTriangle aria-hidden="true" />;
  }
  if (status === "accepted" || status === "done") {
    return <Check aria-hidden="true" />;
  }
  if (status === "failed") {
    return <XCircle aria-hidden="true" />;
  }
  return null;
}

function StatusCell({ status }: { status: JobStatusValue }): React.ReactElement {
  return (
    <StatusChip tone={JOB_STATUS_TONE[status]}>
      <StatusCellIcon status={status} />
      {STATUS_LABEL[status]}
    </StatusChip>
  );
}

// ---------------------------------------------------------------------------
// Status filter options (S-E)
// ---------------------------------------------------------------------------
// `proposed` and `under_review` share the "Needs Review" label (STATUS_LABEL) and the same
// `warning` tone — collapsed into one filter option here too, rather than two dropdown entries
// with identical text that would filter differently underneath. Same reasoning for
// `accepted`/`done` staying separate: they render distinct labels ("Accepted" vs "Done"), so a
// user filtering by one shouldn't silently also match the other.

interface StatusFilterOption {
  value: string;
  label: string;
  statuses: JobStatusValue[];
}

const STATUS_FILTER_OPTIONS: StatusFilterOption[] = [
  { value: "all", label: "All statuses", statuses: [] },
  { value: "queued", label: STATUS_LABEL.queued, statuses: ["queued"] },
  { value: "running", label: STATUS_LABEL.running, statuses: ["running"] },
  { value: "needs_review", label: "Needs Review", statuses: ["proposed", "under_review"] },
  { value: "accepted", label: STATUS_LABEL.accepted, statuses: ["accepted"] },
  { value: "done", label: STATUS_LABEL.done, statuses: ["done"] },
  { value: "failed", label: STATUS_LABEL.failed, statuses: ["failed"] },
];

// ---------------------------------------------------------------------------
// SortableHeader (jobs table) — chevron sort-direction indicator per mockup
// ---------------------------------------------------------------------------

type SortColumn = "name" | "status" | "files" | "created";

function SortableHeader({
  column,
  label,
  activeColumn,
  direction,
  onToggle,
}: {
  column: SortColumn;
  label: string;
  activeColumn: SortColumn;
  direction: "asc" | "desc";
  onToggle: (column: SortColumn) => void;
}): React.ReactElement {
  const isActive = activeColumn === column;
  return (
    <button
      type="button"
      onClick={() => onToggle(column)}
      aria-label={`Sort by ${label}`}
      className={cn(
        "inline-flex items-center gap-1 cursor-pointer select-none transition-colors",
        isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
      {isActive && direction === "desc" ? (
        <ChevronUp className="h-3 w-3" aria-hidden="true" />
      ) : (
        <ChevronDown
          className={cn("h-3 w-3", isActive ? "opacity-100" : "opacity-40")}
          aria-hidden="true"
        />
      )}
    </button>
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

  // ── Header stat line (S-C) ─────────────────────────────────────────────────

  const stats = useMemo(() => {
    const list = jobs ?? [];
    return {
      total: list.length,
      needsReview: list.filter(
        (j) => j.status === "proposed" || j.status === "under_review",
      ).length,
      running: list.filter((j) => j.status === "running" || j.status === "queued")
        .length,
      accepted: list.filter((j) => j.status === "accepted").length,
    };
  }, [jobs]);

  // ── Search + status filter, sort (S-D, S-E, S-F) ────────────────────────────
  // One shared filter-state object (search + status) so the two filters compose via AND
  // instead of being derived independently.

  const [tableFilter, setTableFilter] = useState<{ search: string; status: string }>({
    search: "",
    status: "all",
  });

  const [tableSort, setTableSort] = useState<{
    column: SortColumn;
    direction: "asc" | "desc";
  }>({ column: "name", direction: "asc" });

  function toggleSort(column: SortColumn) {
    setTableSort((prev) =>
      prev.column === column
        ? { column, direction: prev.direction === "asc" ? "desc" : "asc" }
        : { column, direction: "asc" },
    );
  }

  const visibleJobs = useMemo(() => {
    const list = jobs ?? [];
    const query = tableFilter.search.trim().toLowerCase();
    const statusOption =
      STATUS_FILTER_OPTIONS.find((o) => o.value === tableFilter.status) ??
      STATUS_FILTER_OPTIONS[0];
    const filtered = list.filter((job) => {
      if (statusOption.statuses.length > 0 && !statusOption.statuses.includes(job.status)) {
        return false;
      }
      if (query === "") return true;
      return (job.name ?? job.job_id).toLowerCase().includes(query);
    });

    const { column, direction } = tableSort;
    const sign = direction === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      switch (column) {
        case "name":
          return sign * (a.name ?? a.job_id).localeCompare(b.name ?? b.job_id);
        case "status":
          return sign * STATUS_LABEL[a.status].localeCompare(STATUS_LABEL[b.status]);
        case "files":
          return sign * ((a.file_count ?? 0) - (b.file_count ?? 0));
        case "created":
          return (
            sign * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
          );
        default:
          return 0;
      }
    });
  }, [jobs, tableFilter, tableSort]);

  // ── Dialog state ──────────────────────────────────────────────────────────

  const [uploadOpen, setUploadOpen] = useState<boolean>(false);
  const [traceJobId, setTraceJobId] = useState<string | null>(null);
  // Callback ref (via state, not useRef) — react-hooks/refs forbids reading `.current`
  // during render, and DialogContent's `container` prop is read during this component's
  // render. Setting state from the ref callback triggers a re-render once the node
  // commits, which happens on JobsPage's own first render (the `.brand-manifest` div
  // below is unconditionally rendered), well before the dialog can be opened.
  const [brandManifestEl, setBrandManifestEl] = useState<HTMLDivElement | null>(null);

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

  const [refTargetPath, setRefTargetPath] = useState<string | null>(null);

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
  const hasEligibleTopLevelFile = files.some((f) => {
    const e = fileExt(f.name);
    return e === ".csv" || e === ".sas7bdat";
  });
  // A zip upload only ever sends `zip_file` to the backend (see submitMigration) —
  // a reference target set on a file sitting alongside the zip, rather than inside
  // it, is silently never uploaded. Detect that state so the UI can warn instead of
  // showing a false "Target set" confirmation.
  const refTargetIsOutsideZip =
    zipFile !== undefined &&
    refTargetPath !== null &&
    files.some((f) => f.name === refTargetPath);

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
      submitMigration(sasFiles, refDataset, zipFile, migrationName, refTargetPath),
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
      setRefTargetPath(null);
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
                refTargetPath={refTargetPath}
                onSetRefTarget={setRefTargetPath}
              />
            );
          }

          const isEligible = ext === ".csv" || ext === ".sas7bdat";
          const isTarget = refTargetPath === f.name;

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
                {isTarget && (
                  <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-[var(--tone-success-bg)] text-[var(--tone-success)]">
                    Target
                  </span>
                )}
              </span>
              <span className="flex items-center gap-1 shrink-0">
                {isEligible && (
                  <button
                    type="button"
                    onClick={() => setRefTargetPath(isTarget ? null : f.name)}
                    aria-label={isTarget ? "Unmark as reconciliation target" : "Mark as reconciliation target"}
                    title={isTarget ? "Remove reconciliation target" : "Set as reconciliation target"}
                    className={cn(
                      "ml-1 shrink-0 cursor-pointer rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors",
                      isTarget ? "text-primary" : "text-muted-foreground hover:text-primary",
                    )}
                  >
                    <Target className="h-3.5 w-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => removeFile(f.name)}
                  aria-label={`Remove ${f.name}`}
                  className="ml-1 shrink-0 cursor-pointer rounded-sm text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  ✕
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    );
  }

  const hasJobs = !isLoading && jobs !== undefined && jobs.length > 0;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div ref={setBrandManifestEl} className="brand-manifest px-6 py-2 overflow-y-auto flex-1 h-full">
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-foreground">Migrations</h1>
            {hasJobs && (
              <p className="mt-1 text-sm text-muted-foreground">
                {stats.total} {stats.total === 1 ? "migration" : "migrations"}, {stats.needsReview}{" "}
                need review, {stats.running} running, {stats.accepted} accepted
              </p>
            )}
          </div>

          <div className="flex items-center gap-2">
            {hasJobs && (
              <>
                <div className="relative">
                  <Search
                    className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <input
                    type="text"
                    value={tableFilter.search}
                    onChange={(e) =>
                      setTableFilter((prev) => ({ ...prev, search: e.target.value }))
                    }
                    placeholder="Search migrations…"
                    aria-label="Search migrations"
                    className="h-9 w-64 rounded-md border border-border bg-background pl-8 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>

                <Select
                  value={tableFilter.status}
                  onValueChange={(value) =>
                    setTableFilter((prev) => ({ ...prev, status: value }))
                  }
                >
                  <SelectTrigger aria-label="Filter by status" className="h-9">
                    <SelectValue placeholder="All statuses" />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUS_FILTER_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </>
            )}
            <Button variant="outline" onClick={() => setUploadOpen(true)}>
              New migration
            </Button>
          </div>
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

        {hasJobs && visibleJobs.length === 0 && (
          <p className="text-sm text-muted-foreground py-4">
            {tableFilter.search.trim() !== ""
              ? `No migrations match “${tableFilter.search.trim()}”.`
              : "No migrations match the selected status."}{" "}
            Try a different search term or status filter.
          </p>
        )}

        {hasJobs && visibleJobs.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm" aria-label="Migration jobs">
              <thead>
                <tr className="border-b border-border bg-muted text-muted-foreground text-left">
                  <th scope="col" className="px-4 py-2.5 font-medium w-[40%]">
                    <SortableHeader
                      column="name"
                      label="Name"
                      activeColumn={tableSort.column}
                      direction={tableSort.direction}
                      onToggle={toggleSort}
                    />
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium">
                    <SortableHeader
                      column="status"
                      label="Status"
                      activeColumn={tableSort.column}
                      direction={tableSort.direction}
                      onToggle={toggleSort}
                    />
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium">
                    <SortableHeader
                      column="files"
                      label="Files"
                      activeColumn={tableSort.column}
                      direction={tableSort.direction}
                      onToggle={toggleSort}
                    />
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium">
                    <SortableHeader
                      column="created"
                      label="Created"
                      activeColumn={tableSort.column}
                      direction={tableSort.direction}
                      onToggle={toggleSort}
                    />
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium sr-only">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleJobs.map((job) => {
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
                        <StatusCell status={job.status} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {job.file_count != null ? job.file_count : "—"}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {new Date(job.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="inline-flex items-center gap-1 justify-end">
                          {(job.status === "queued" || job.status === "running" || job.status === "done" || job.status === "under_review" || job.status === "proposed") && (
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-7 w-7"
                              title="Live trace"
                              aria-label={`Live trace for job ${job.job_id.slice(0, 8)}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                setTraceJobId(job.job_id);
                              }}
                            >
                              <Activity className={`h-4 w-4 ${["running", "queued"].includes(job.status) ? "text-primary animate-pulse" : "text-muted-foreground"}`} />
                            </Button>
                          )}
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
                        </span>
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
        <DialogContent
          container={brandManifestEl}
          className="max-w-3xl w-[90vw] h-[85vh] overflow-y-auto flex flex-col"
        >
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
                <form
                  id="migration-form"
                  onSubmit={handleSubmit}
                  noValidate
                  className="space-y-6"
                >
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

                  {files.length > 0 && (
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium text-muted-foreground">
                        <Target className="inline-block w-3 h-3 mr-1" />Reconciliation target (optional)
                      </p>
                      {refTargetPath && (
                        refTargetIsOutsideZip ? (
                          <span className={`text-xs font-medium ${TONE_TEXT_CLASS.danger}`}>
                            ⚠ Won't upload — outside the zip
                          </span>
                        ) : (
                          <span className={`text-xs font-medium ${TONE_TEXT_CLASS.success}`}>
                            ✓ Target set
                          </span>
                        )
                      )}
                    </div>
                  )}

                  {renderFileList()}

                  {refTargetIsOutsideZip && (
                    <p role="alert" className={`text-xs flex items-start gap-1 ${TONE_TEXT_CLASS.danger}`}>
                      <Target className="inline h-3 w-3 mt-0.5 shrink-0" />
                      <span>
                        This target sits alongside the zip, not inside it, so it won't be
                        uploaded — only files bundled inside the zip can be sent as the
                        reconciliation reference. Unmark it and pick a file from inside the
                        zip's tree instead, or add the reference file to the zip itself.
                      </span>
                    </p>
                  )}

                  {!refTargetIsOutsideZip && !refTargetPath && zipFile && (
                    <p className="text-xs text-muted-foreground flex items-start gap-1">
                      <Target className="inline h-3 w-3 mt-0.5 shrink-0" />
                      <span>
                        Optional — migration runs fine without one. To compare output
                        against a reference, expand the zip above and click the target
                        icon on a CSV or dataset file inside it. A reference file must be
                        bundled inside the zip; one added separately here won't be uploaded.
                      </span>
                    </p>
                  )}

                  {!refTargetIsOutsideZip && !refTargetPath && !zipFile && hasEligibleTopLevelFile && (
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      Optional — migration runs fine without one. Click{" "}
                      <Target className="inline h-3 w-3" /> next to a CSV or dataset file
                      to set it as the reconciliation target.
                    </p>
                  )}

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
            {phase === "staging" && (
              <Button
                type="submit"
                form="migration-form"
                disabled={submitDisabled}
                aria-busy={isPending}
                className="cursor-pointer"
              >
                {isPending ? "Submitting…" : "Migrate"}
              </Button>
            )}

            {phase === "submitted" && manifest !== null && (
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

      <LiveTraceDialog
        open={!!traceJobId}
        jobId={traceJobId ?? ""}
        jobName={jobs?.find((j) => j.job_id === traceJobId)?.name ?? null}
        onOpenChange={(open) => {
          if (!open) setTraceJobId(null);
        }}
        onJobDone={() => queryClient.invalidateQueries({ queryKey: ["jobs"] })}
      />
    </div>
  );
}
