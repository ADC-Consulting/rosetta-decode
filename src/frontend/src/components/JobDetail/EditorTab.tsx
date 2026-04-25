import {
  executeJob,
  getBlockRevisions,
  getJobAttachments,
  getJobChangelog,
  getJobSources,
} from "@/api/jobs";
import type {
  AttachmentInfo,
  BlockPlan,
  ChangelogEntry,
  ExecuteCheckResult,
  ExecuteResponse,
} from "@/api/types";
import FileTree, { buildTree } from "@/components/FileTree";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { Editor } from "@monaco-editor/react";
import { useQuery } from "@tanstack/react-query";
import {
  BracesIcon,
  ChevronDown,
  ChevronRight,
  Copy,
  DatabaseIcon,
  FunctionSquareIcon,
  Loader2,
  Lock,
  Maximize2,
  Minimize2,
  Moon,
  Pencil,
  Play,
  Save,
  Sun,
} from "lucide-react";
import type { editor } from "monaco-editor";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import LogView from "./LogView";
import OutputView from "./OutputView";
import { registerSasLanguage } from "./registerSasLanguage";

// ---------------------------------------------------------------------------
// Block type icon helper
// ---------------------------------------------------------------------------

function BlockTypeIcon({
  blockType,
  color,
}: {
  blockType: string;
  color: string;
}): React.ReactElement {
  const upper = blockType.toUpperCase();
  if (upper === "DATA" || upper.startsWith("DATA ")) {
    return <DatabaseIcon size={11} style={{ color }} className="shrink-0" />;
  }
  if (upper === "MACRO" || upper.startsWith("%MACRO")) {
    return <BracesIcon size={11} style={{ color }} className="shrink-0" />;
  }
  // PROC * and everything else
  return (
    <FunctionSquareIcon size={11} style={{ color }} className="shrink-0" />
  );
}

// ---------------------------------------------------------------------------
// SasAwareFileTree — FileTree augmented with expandable block children
// ---------------------------------------------------------------------------

interface SasAwareFileTreeProps {
  paths: string[];
  selectedPath: string | null;
  blockPlans: BlockPlan[];
  onSelect: (path: string) => void;
  onSelectBlock: (block: BlockPlan) => void;
  storageKey: string;
  theme?: "dark" | "light";
}

function SasAwareFileTree({
  paths,
  selectedPath,
  blockPlans,
  onSelect,
  onSelectBlock,
  storageKey,
  theme = "dark",
}: SasAwareFileTreeProps): React.ReactElement {
  // Index blocks by normalised sas_file basename
  const blocksByFile = useMemo(() => {
    const map = new Map<string, BlockPlan[]>();
    for (const b of blockPlans) {
      const key = b.source_file.split("/").pop() ?? b.source_file;
      const arr = map.get(key) ?? [];
      arr.push(b);
      map.set(key, arr);
    }
    return map;
  }, [blockPlans]);

  // Which .sas files have their block list expanded
  const lsKey = `sas-blocks-expanded-${storageKey}`;
  const [expandedSas, setExpandedSas] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(lsKey);
      if (raw) return new Set(JSON.parse(raw) as string[]);
    } catch {
      // ignore
    }
    return new Set<string>();
  });

  const toggleSas = useCallback(
    (sasPath: string) => {
      setExpandedSas((prev) => {
        const next = new Set(prev);
        if (next.has(sasPath)) next.delete(sasPath);
        else next.add(sasPath);
        try {
          localStorage.setItem(lsKey, JSON.stringify([...next]));
        } catch {
          // ignore
        }
        return next;
      });
    },
    [lsKey],
  );

  // Theme tokens (mirror FileTree)
  const rowHoverBg =
    theme === "light" ? "rgba(0,0,0,0.06)" : "rgba(255,255,255,0.06)";
  const rowSelectedBg = theme === "light" ? "#e8e8e8" : "#37373d";
  const rowColor = theme === "light" ? "#111" : "#d4d4d4";
  const badgeBg = theme === "light" ? "#e5e7eb" : "#3a3a3a";
  const badgeColor = theme === "light" ? "#374151" : "#9ca3af";
  const iconAccent = theme === "light" ? "#6366f1" : "#818cf8";

  // Check whether a given full path has blocks attached
  const hasBlocks = useCallback(
    (path: string): boolean => {
      const name = path.split("/").pop() ?? path;
      return path.endsWith(".sas") && (blocksByFile.get(name)?.length ?? 0) > 0;
    },
    [blocksByFile],
  );

  // We need to intercept clicks on .sas files with blocks so we can toggle
  // their expand state without breaking the file-selection behaviour.
  // The FileTree `onSelect` callback still fires — we handle the toggle here.
  const handleFileSelect = useCallback(
    (path: string) => {
      onSelect(path);
      if (hasBlocks(path)) {
        // Auto-expand when selecting a sas file that has blocks
        setExpandedSas((prev) => {
          if (prev.has(path)) return prev;
          const next = new Set(prev);
          next.add(path);
          try {
            localStorage.setItem(lsKey, JSON.stringify([...next]));
          } catch {
            // ignore
          }
          return next;
        });
      }
    },
    [onSelect, hasBlocks, lsKey],
  );

  // Build tree from flat paths
  const tree = useMemo(() => buildTree(paths), [paths]);

  // Row union type
  type Row =
    | { kind: "tree"; path: string; depth: number }
    | { kind: "block"; block: BlockPlan; parentPath: string; depth: number };

  // Directory expand/collapse — reuse same localStorage key as FileTree
  const dirLsKey = `filetree-expanded-${storageKey}`;
  const [dirExpanded, setDirExpanded] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(dirLsKey);
      if (raw) return new Set(JSON.parse(raw) as string[]);
    } catch {
      // ignore
    }
    const all = new Set<string>();
    const collectDirs = (nodes: typeof tree) => {
      for (const n of nodes) {
        if (n.type === "dir") {
          all.add(n.path);
          collectDirs(n.children ?? []);
        }
      }
    };
    collectDirs(tree);
    return all;
  });

  const toggleDir = useCallback(
    (path: string) => {
      setDirExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(path)) next.delete(path);
        else next.add(path);
        try {
          localStorage.setItem(dirLsKey, JSON.stringify([...next]));
        } catch {
          // ignore
        }
        return next;
      });
    },
    [dirLsKey],
  );

  // Re-derive rows using dirExpanded (not the all-expanded set above)
  const visibleRows = useMemo((): Row[] => {
    const result: Row[] = [];
    const walk = (nodes: typeof tree, depth: number) => {
      for (const node of nodes) {
        result.push({ kind: "tree", path: node.path, depth });
        if (node.type === "dir" && dirExpanded.has(node.path)) {
          walk(node.children ?? [], depth + 1);
        } else if (node.type === "file" && node.path.endsWith(".sas")) {
          if (expandedSas.has(node.path)) {
            const name = node.path.split("/").pop() ?? node.path;
            const blocks = blocksByFile.get(name) ?? [];
            for (const block of blocks) {
              result.push({
                kind: "block",
                block,
                parentPath: node.path,
                depth: depth + 1,
              });
            }
          }
        }
      }
    };
    walk(tree, 0);
    return result;
  }, [tree, dirExpanded, expandedSas, blocksByFile]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Tree */}
      <div
        role="tree"
        className="flex-1 overflow-y-auto overflow-x-hidden py-1 focus:outline-none"
        style={{ background: theme === "light" ? "#fff" : "#1e1e1e" }}
      >
        {visibleRows.map((row, idx) => {
          if (row.kind === "block") {
            const isParentSelected = row.parentPath === selectedPath;
            const indentPx = row.depth * 12;
            const shortLabel = row.block.block_type;
            return (
              <div
                key={`block-${row.block.block_id}-${idx}`}
                role="treeitem"
                aria-label={`Block: ${shortLabel}`}
                style={{
                  paddingLeft: indentPx,
                  color: rowColor,
                }}
                className="relative flex items-center gap-1 h-6 pr-2 text-[12px] cursor-pointer select-none"
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLDivElement).style.background =
                    rowHoverBg;
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.background = "";
                }}
                onClick={() => {
                  if (!isParentSelected) onSelect(row.parentPath);
                  onSelectBlock(row.block);
                }}
              >
                {/* Vertical guide line */}
                <span
                  className="absolute top-0 bottom-0 border-l border-border pointer-events-none"
                  style={{ left: indentPx - 6 }}
                />
                {/* Spacer matching chevron width */}
                <span className="shrink-0 w-3" />
                {/* Block type icon */}
                <BlockTypeIcon
                  blockType={row.block.block_type}
                  color={iconAccent}
                />
                {/* Short label */}
                <span
                  className="truncate text-[11px] leading-none"
                  style={{ color: rowColor, opacity: 0.85 }}
                >
                  {shortLabel}
                </span>
                {/* Line number badge */}
                {row.block.start_line > 0 && (
                  <span
                    className="ml-auto shrink-0 text-[10px] px-1 rounded font-mono"
                    style={{ background: badgeBg, color: badgeColor }}
                  >
                    :{row.block.start_line}
                  </span>
                )}
              </div>
            );
          }

          // --- tree row ---
          const findNode = (
            nodes: ReturnType<typeof buildTree>,
            target: string,
          ): ReturnType<typeof buildTree>[number] | undefined => {
            for (const n of nodes) {
              if (n.path === target) return n;
              if (n.type === "dir") {
                const found = findNode(n.children ?? [], target);
                if (found) return found;
              }
            }
            return undefined;
          };
          const node = findNode(tree, row.path);

          if (!node) return null;

          const indentPx = row.depth * 12;
          const isSelected = node.path === selectedPath;
          const isDir = node.type === "dir";
          const isDirExpanded = dirExpanded.has(node.path);
          const isSasWithBlocks =
            node.type === "file" &&
            node.path.endsWith(".sas") &&
            hasBlocks(node.path);
          const isSasExpanded = expandedSas.has(node.path);

          return (
            <div
              key={node.path}
              role="treeitem"
              aria-selected={!isDir ? isSelected : undefined}
              aria-expanded={
                isDir
                  ? isDirExpanded
                  : isSasWithBlocks
                    ? isSasExpanded
                    : undefined
              }
              style={{
                paddingLeft: indentPx,
                color: rowColor,
                background: isSelected ? rowSelectedBg : undefined,
              }}
              className={cn(
                "relative flex items-center gap-1 h-6 pr-2 text-[13px] cursor-pointer select-none",
              )}
              onMouseEnter={
                !isSelected
                  ? (e) => {
                      (e.currentTarget as HTMLDivElement).style.background =
                        rowHoverBg;
                    }
                  : undefined
              }
              onMouseLeave={
                !isSelected
                  ? (e) => {
                      (e.currentTarget as HTMLDivElement).style.background = "";
                    }
                  : undefined
              }
              onClick={() => {
                if (isDir) {
                  toggleDir(node.path);
                } else {
                  handleFileSelect(node.path);
                  if (isSasWithBlocks) toggleSas(node.path);
                }
              }}
            >
              {/* Vertical guide line */}
              {row.depth > 0 && (
                <span
                  className="absolute top-0 bottom-0 border-l border-border pointer-events-none"
                  style={{ left: indentPx - 6 }}
                />
              )}

              {/* Chevron */}
              <span className="shrink-0 w-3 flex items-center justify-center">
                {isDir ? (
                  isDirExpanded ? (
                    <ChevronDown size={12} className="text-muted-foreground" />
                  ) : (
                    <ChevronRight size={12} className="text-muted-foreground" />
                  )
                ) : isSasWithBlocks ? (
                  isSasExpanded ? (
                    <ChevronDown size={12} className="text-muted-foreground" />
                  ) : (
                    <ChevronRight size={12} className="text-muted-foreground" />
                  )
                ) : null}
              </span>

              {/* Icon — reuse lucide icons matching FileTree */}
              {isDir ? (
                isDirExpanded ? (
                  <span className="shrink-0 text-yellow-400 opacity-80 text-[13px]">
                    📂
                  </span>
                ) : (
                  <span className="shrink-0 text-yellow-400 opacity-70 text-[13px]">
                    📁
                  </span>
                )
              ) : node.path.endsWith(".sas") || node.path.endsWith(".py") ? (
                <span
                  className="shrink-0 opacity-80 text-[11px]"
                  style={{ color: "#75beff" }}
                >
                  {"</>"}
                </span>
              ) : (
                <span className="shrink-0 text-muted-foreground opacity-70 text-[11px]">
                  📄
                </span>
              )}

              {/* Name */}
              <span className="truncate text-[13px] leading-none">
                {node.name}
              </span>
            </div>
          );
        })}

        {visibleRows.length === 0 && (
          <p className="px-3 py-2 text-[12px] text-muted-foreground">
            No files found.
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ExecutionOutputPanel — embedded in bottom panel (no close button)
// ---------------------------------------------------------------------------

type ExecOutputTab = "output" | "result" | "recon";

interface ExecutionOutputPanelProps {
  result: ExecuteResponse | null;
  fetchError: string | null;
  onClose?: () => void;
  activeTab: ExecOutputTab;
  onTabChange: (tab: ExecOutputTab) => void;
}

function ExecutionOutputPanel({
  result,
  fetchError,
  activeTab,
  onTabChange,
}: ExecutionOutputPanelProps): React.ReactElement {
  const hasResult = result !== null && result.result_json !== null;
  const hasRecon =
    result !== null && result.checks !== null && result.checks.length > 0;
  const reconPassed =
    result?.checks?.every((c) => c.status === "pass") ?? false;

  const tabs: { key: ExecOutputTab; label: string }[] = [
    { key: "output", label: "Output" },
    ...(hasResult
      ? [
          {
            key: "result" as ExecOutputTab,
            label: `Result (${result!.result_json!.length} rows)`,
          },
        ]
      : []),
    ...(hasRecon
      ? [
          {
            key: "recon" as ExecOutputTab,
            label: reconPassed ? "Recon ✓" : "Recon ✗",
          },
        ]
      : []),
  ];

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      aria-label="Execution output"
    >
      {/* Sub-tab strip */}
      <div className="flex items-center gap-0.5 px-2 py-1 border-b border-border shrink-0">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => onTabChange(t.key)}
            className={cn(
              "px-2.5 py-0.5 text-[11px] font-medium rounded transition-colors cursor-pointer",
              activeTab === t.key
                ? "bg-background text-foreground border border-border"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t.key === "output" && fetchError
              ? "Run failed"
              : t.key === "output" && result?.error
                ? "Run error"
                : t.label}
          </button>
        ))}
        {result && !fetchError && (
          <span className="ml-2 text-[10px] text-muted-foreground/60">
            {result.elapsed_ms}ms
          </span>
        )}
      </div>

      {/* Panel body */}
      <div className="flex-1 overflow-auto bg-background">
        {/* Output tab */}
        {activeTab === "output" && (
          <div className="p-3">
            {fetchError && (
              <div className="relative rounded border border-red-300 bg-red-50 dark:bg-red-950/30 dark:border-red-800 px-3 py-2 text-xs text-red-700 dark:text-red-400 font-mono mb-2">
                <button
                  type="button"
                  className="absolute top-2 right-2 p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    void navigator.clipboard.writeText(fetchError);
                    toast.success("Copied to clipboard");
                  }}
                  aria-label="Copy error"
                >
                  <Copy size={12} />
                </button>
                <pre className="select-all whitespace-pre-wrap break-all">
                  {fetchError}
                </pre>
              </div>
            )}
            {result?.error && (
              <div className="relative rounded border border-red-300 bg-red-50 dark:bg-red-950/30 dark:border-red-800 px-3 py-2 text-xs text-red-700 dark:text-red-400 font-mono mb-2">
                <button
                  type="button"
                  className="absolute top-2 right-2 p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    const errorText =
                      result.error +
                      (result.stderr ? "\n" + result.stderr : "");
                    void navigator.clipboard.writeText(errorText);
                    toast.success("Copied to clipboard");
                  }}
                  aria-label="Copy error"
                >
                  <Copy size={12} />
                </button>
                {result.error}
                {result.stderr && (
                  <pre className="select-all mt-2 whitespace-pre-wrap break-all opacity-80">
                    {result.stderr}
                  </pre>
                )}
              </div>
            )}
            {result && result.stdout.trim().length > 0 && (
              <pre className="text-xs font-mono whitespace-pre-wrap break-all overflow-y-auto max-h-48 text-foreground mt-2">
                {result.stdout}
              </pre>
            )}
            {result && !result.error && result.stdout.trim().length === 0 && (
              <p className="text-xs text-muted-foreground italic">No output</p>
            )}
          </div>
        )}

        {/* Result tab */}
        {activeTab === "result" && hasResult && (
          <div className="overflow-auto max-h-full">
            <Table>
              <TableHeader>
                <TableRow>
                  {(
                    result!.result_columns ??
                    Object.keys(result!.result_json![0] ?? {})
                  ).map((col) => (
                    <TableHead
                      key={col}
                      className="whitespace-nowrap text-xs font-semibold"
                    >
                      {col}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {result!.result_json!.slice(0, 500).map((row, ri) => {
                  const cols = result!.result_columns ?? Object.keys(row);
                  return (
                    <TableRow key={ri}>
                      {cols.map((col) => (
                        <TableCell
                          key={col}
                          className="text-xs font-mono whitespace-nowrap"
                        >
                          {String(row[col] ?? "")}
                        </TableCell>
                      ))}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}

        {/* Recon tab */}
        {activeTab === "recon" && hasRecon && (
          <div className="divide-y divide-border">
            {result!.checks!.map((check: ExecuteCheckResult) => (
              <div
                key={check.name}
                className="flex items-start gap-3 px-3 py-2"
              >
                <span
                  className={cn(
                    "shrink-0 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold",
                    check.status === "pass"
                      ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-400"
                      : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-400",
                  )}
                >
                  {check.status === "pass" ? "Pass" : "Fail"}
                </span>
                <span className="text-xs font-mono text-muted-foreground shrink-0 w-36 truncate">
                  {check.name}
                </span>
                <span className="text-xs text-foreground">{check.detail}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// BottomPanel — persistent bottom section with tab bar
// ---------------------------------------------------------------------------

type BottomTab = "code" | "log" | "output" | "history";

interface BottomPanelProps {
  bottomTab: BottomTab;
  setBottomTab: (t: BottomTab) => void;
  executeResult: ExecuteResponse | null;
  executeError: string | null;
  execOutputTab: ExecOutputTab;
  setExecOutputTab: (t: ExecOutputTab) => void;
  logAttachments: AttachmentInfo[];
  outputAttachments: AttachmentInfo[];
  jobId: string;
  changelog: { entries: ChangelogEntry[] } | undefined;
  onLoadRevisionCode?: (code: string) => void;
  theme?: "dark" | "light";
}

function BottomPanel({
  bottomTab,
  setBottomTab,
  executeResult,
  executeError,
  execOutputTab,
  setExecOutputTab,
  logAttachments,
  outputAttachments,
  jobId,
  changelog,
  onLoadRevisionCode,
  theme = "light",
}: BottomPanelProps): React.ReactElement {
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(
    null,
  );
  const tabs: { key: BottomTab; label: string; count?: number }[] = [
    { key: "code", label: "Code" },
    { key: "log", label: "Log", count: logAttachments.length },
    { key: "output", label: "Output", count: outputAttachments.length },
    { key: "history", label: "History" },
  ];

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Tab bar — flush left, SAS Studio style */}
      <div
        className="flex items-center gap-0 shrink-0 border-b border-border bg-muted/30"
        style={
          theme === "dark"
            ? { background: "#252526", borderBottom: "1px solid #3e3e3e" }
            : undefined
        }
      >
        {tabs.map(({ key, label, count }) => (
          <button
            key={key}
            onClick={() => setBottomTab(key)}
            className={cn(
              "flex items-center gap-1 px-3 py-1.5 text-[11px] font-medium border-b-2 transition-colors cursor-pointer",
              bottomTab === key
                ? theme === "dark"
                  ? "border-blue-400 text-white"
                  : "border-primary text-foreground bg-background"
                : theme === "dark"
                  ? "border-transparent text-[#858585] hover:text-[#cccccc] hover:bg-white/5"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50",
            )}
            style={
              bottomTab === key && theme === "dark"
                ? { background: "#1e1e1e" }
                : undefined
            }
          >
            {label}
            {count !== undefined && count > 0 && (
              <span className="inline-flex items-center justify-center rounded-full bg-muted text-muted-foreground px-1.5 py-0.5 text-[10px] font-semibold">
                {count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content area */}
      <div
        className="flex-1 min-h-0 overflow-hidden"
        style={theme === "dark" ? { background: "#1e1e1e" } : undefined}
      >
        {/* Code tab */}
        {bottomTab === "code" && (
          <>
            {executeResult === null && executeError === null ? (
              <p className="text-xs text-muted-foreground italic p-3">
                Run Python ▶ to see output here.
              </p>
            ) : (
              <ExecutionOutputPanel
                result={executeResult}
                fetchError={executeError}
                activeTab={execOutputTab}
                onTabChange={setExecOutputTab}
              />
            )}
          </>
        )}

        {/* Log tab */}
        {bottomTab === "log" && (
          <LogView jobId={jobId} attachments={logAttachments} />
        )}

        {/* Output tab */}
        {bottomTab === "output" && (
          <OutputView jobId={jobId} attachments={outputAttachments} />
        )}

        {/* History tab */}
        {bottomTab === "history" && (
          <div className="h-full overflow-y-auto divide-y divide-border">
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
                    new Date(a.created_at).getTime() -
                    new Date(b.created_at).getTime(),
                )
                .map((entry: ChangelogEntry, idx: number, arr) => {
                  const isHuman =
                    entry.trigger === "human" || entry.trigger === "restore";
                  const diffMs =
                    new Date().getTime() - new Date(entry.created_at).getTime();
                  const diffMin = Math.floor(diffMs / 60_000);
                  const relTime =
                    diffMin < 1
                      ? "just now"
                      : diffMin < 60
                        ? `${diffMin}m ago`
                        : diffMin < 1440
                          ? `${Math.floor(diffMin / 60)}h ago`
                          : `${Math.floor(diffMin / 1440)}d ago`;
                  const handleClick = () => {
                    setSelectedHistoryId(entry.id);
                    void getBlockRevisions(jobId, entry.block_id).then(
                      (history) => {
                        const rev =
                          history.revisions.find(
                            (r) => r.revision_number === entry.revision_number,
                          ) ?? history.revisions[0];
                        if (rev?.python_code)
                          onLoadRevisionCode?.(rev.python_code);
                      },
                    );
                  };
                  return (
                    <div
                      key={entry.id}
                      className={cn(
                        "flex items-center gap-2 px-3 py-2 text-xs cursor-pointer border-l-2 transition-colors",
                        entry.id === selectedHistoryId
                          ? theme === "dark"
                            ? "border-blue-400 bg-blue-400/10 text-white"
                            : "border-primary bg-primary/10 text-foreground"
                          : theme === "dark"
                            ? "border-transparent text-[#cccccc] hover:bg-white/5"
                            : "border-transparent hover:bg-muted/30",
                      )}
                      onClick={handleClick}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleClick();
                      }}
                    >
                      <span aria-hidden>{isHuman ? "👤" : "🤖"}</span>
                      <span
                        className={cn(
                          "font-mono font-semibold text-[11px] tabular-nums shrink-0",
                          theme === "dark"
                            ? "text-[#cccccc]"
                            : "text-foreground",
                        )}
                      >
                        v{entry.revision_number}
                      </span>
                      {idx === arr.length - 1 && (
                        <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold bg-emerald-100 text-emerald-800">
                          Latest
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

// ---------------------------------------------------------------------------
// EditorTab — main export
// ---------------------------------------------------------------------------

export default function EditorTab({
  jobId,
  generatedFiles,
  onGeneratedFilesChange,
  code,
  setCode,
  blockPlans = [],
  onSave,
  isSaving,
  onExpand,
  isFullPage = false,
}: {
  jobId: string;
  generatedFiles: Record<string, string> | null;
  onGeneratedFilesChange?: (gf: Record<string, string>) => void;
  code: string;
  setCode: (code: string) => void;
  blockPlans?: BlockPlan[];
  onSave?: () => void;
  isSaving?: boolean;
  onExpand?: () => void;
  isFullPage?: boolean;
}): React.ReactElement {
  const [bottomTab, setBottomTab] = useState<BottomTab>("code");
  const [editorDark, setEditorDark] = useState(false);
  const [pythonEditable, setPythonEditable] = useState(false);
  const [selectedBlock, setSelectedBlock] = useState<BlockPlan | null>(null);
  const [executing, setExecuting] = useState(false);
  const [executeResult, setExecuteResult] = useState<ExecuteResponse | null>(
    null,
  );
  const [executeError, setExecuteError] = useState<string | null>(null);
  const [execOutputTab, setExecOutputTab] = useState<ExecOutputTab>("output");
  const pythonEditorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const sasEditorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoTheme = editorDark
    ? { sas: "sas-dark", python: "vs-dark" }
    : { sas: "sas-light", python: "vs" };
  const [selectedSasKey, setSelectedSasKey] = useState<string>("");
  const [overrideRevisionCode, setOverrideRevisionCode] = useState<
    string | null
  >(null);

  const { data: sources, isLoading } = useQuery({
    queryKey: ["job", jobId, "sources"],
    queryFn: () => getJobSources(jobId),
    enabled: !!jobId,
  });

  const { data: changelog } = useQuery({
    queryKey: ["job", jobId, "changelog"],
    queryFn: () => getJobChangelog(jobId),
    enabled: !!jobId && bottomTab === "history",
  });

  const { data: attachmentsData } = useQuery({
    queryKey: ["job", jobId, "attachments"],
    queryFn: () => getJobAttachments(jobId),
    enabled: !!jobId,
  });

  const logAttachments: AttachmentInfo[] =
    attachmentsData?.attachments.filter((a) => a.category === "log") ?? [];
  const outputAttachments: AttachmentInfo[] =
    attachmentsData?.attachments.filter((a) => a.category === "output") ?? [];

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
  const rightCode = overrideRevisionCode ?? perFileCode ?? code;
  const rightReadOnly = !pythonEditable;

  useEffect(() => {
    if (overrideRevisionCode !== null && pythonEditorRef.current) {
      const model = pythonEditorRef.current.getModel();
      if (model) model.setValue(overrideRevisionCode);
    }
  }, [overrideRevisionCode]);


  const hasPythonCode = !!(rightCode && rightCode.trim().length > 0);

  const handleRun = async () => {
    if (executing || !hasPythonCode) return;
    setExecuting(true);
    setExecuteResult(null);
    setExecuteError(null);
    setBottomTab("code");
    try {
      const result = await executeJob(jobId, selectedBlock?.block_id);
      setExecuteResult(result);
      setExecOutputTab("output");
    } catch (e: unknown) {
      setExecuteError(e instanceof Error ? e.message : String(e));
    } finally {
      setExecuting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        Loading sources…
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 flex flex-col">
      {/* Toolbar — Run first/left, then separator, then edit/theme controls */}
      <div className="flex items-center gap-2 shrink-0 px-1 py-1.5 border-b border-border">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger
              aria-label="Run Python code"
              onClick={() => {
                void handleRun();
              }}
              disabled={executing || !hasPythonCode}
              className={cn(
                "flex items-center gap-1 text-xs transition-colors cursor-pointer border rounded px-2 py-1.5",
                hasPythonCode && !executing
                  ? "border-green-600 text-green-600 hover:bg-green-600/10"
                  : "border-border text-muted-foreground opacity-50 cursor-not-allowed",
              )}
            >
              {executing ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Play size={14} />
              )}
              <span>Run</span>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              {executing
                ? "Running…"
                : hasPythonCode
                  ? "Run Python code"
                  : "No Python code loaded"}
            </TooltipContent>
          </Tooltip>

          {/* Separator */}
          <span className="h-4 w-px bg-border shrink-0" aria-hidden />

          {pythonEditable && (
            <button
              onClick={() => onSave?.()}
              disabled={isSaving}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium border border-border bg-background hover:bg-muted transition-colors cursor-pointer disabled:opacity-50"
            >
              <Save size={12} />
              {isSaving ? "Saving…" : "Save"}
            </button>
          )}
          <button
            onClick={() => setPythonEditable((v) => !v)}
            aria-label={pythonEditable ? "Lock Python editor" : "Edit Python"}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium border border-border bg-background hover:bg-muted transition-colors cursor-pointer"
          >
            {pythonEditable ? (
              <>
                <Lock size={12} /> Read-only
              </>
            ) : (
              <>
                <Pencil size={12} /> Edit
              </>
            )}
          </button>

          <span className="flex-1" />

          <button
            type="button"
            aria-label={
              editorDark
                ? "Switch editor to light theme"
                : "Switch editor to dark theme"
            }
            onClick={() => setEditorDark((d) => !d)}
            className="inline-flex items-center text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer border border-border rounded p-1.5"
          >
            {editorDark ? <Sun size={14} /> : <Moon size={14} />}
          </button>

          <button
            type="button"
            aria-label={isFullPage ? "Minimize editor" : "Open in full page"}
            onClick={() => onExpand?.()}
            className="inline-flex items-center text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer border border-border rounded p-1.5"
          >
            {isFullPage ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </TooltipProvider>
      </div>

      {/* Main vertical split: top editors + bottom panel */}
      <ResizablePanelGroup
        id="editor-outer-panel-group"
        orientation="vertical"
        className="flex-1 min-h-0"
      >
        {/* TOP panel — horizontal 3-panel editor group */}
        <ResizablePanel defaultSize={75} minSize={30}>
          <ResizablePanelGroup
            id="editor-panel-group"
            orientation="horizontal"
            className="rounded-md overflow-hidden h-full"
            style={{
              border: editorDark
                ? "1px solid #3e3e3e"
                : "1px solid var(--border)",
            }}
          >
            <ResizablePanel defaultSize={50} minSize={50} maxSize={300}>
              <div
                className="flex flex-col h-full"
                style={{ background: editorDark ? "#1e1e1e" : "#fafafa" }}
              >
                <div
                  className="h-8 flex items-center px-3 text-[10px] font-semibold tracking-widest uppercase shrink-0"
                  style={{
                    background: editorDark ? "#1e1e1e" : "#fafafa",
                    color: editorDark ? "#858585" : "#374151",
                    borderBottom: editorDark
                      ? "1px solid #3e3e3e"
                      : "1px solid var(--border)",
                  }}
                >
                  Explorer
                </div>
                <div className="flex-1 min-h-0 overflow-hidden">
                  {blockPlans.length > 0 ? (
                    <SasAwareFileTree
                      paths={allPaths}
                      selectedPath={effectiveSasKey || null}
                      blockPlans={blockPlans}
                      onSelect={(path) => {
                        if (path.endsWith(".sas")) setSelectedSasKey(path);
                        else setSelectedSasKey("");
                        setSelectedBlock(null);
                      }}
                      onSelectBlock={(block) => {
                        setSelectedBlock(block);
                        const filePath = allPaths.find(
                          (p) =>
                            p === block.source_file ||
                            p.endsWith(`/${block.source_file}`) ||
                            (p.split("/").pop() ?? p) === block.source_file,
                        );
                        if (filePath && filePath !== effectiveSasKey) {
                          setSelectedSasKey(filePath);
                        }
                        if (block.start_line > 0 && sasEditorRef.current) {
                          sasEditorRef.current.revealLineInCenter(
                            block.start_line,
                          );
                          sasEditorRef.current.setPosition({
                            lineNumber: block.start_line,
                            column: 1,
                          });
                        }
                      }}
                      storageKey={`job-${jobId}`}
                      theme={editorDark ? "dark" : "light"}
                    />
                  ) : (
                    <FileTree
                      paths={allPaths}
                      selectedPath={effectiveSasKey || null}
                      onSelect={(path) => {
                        if (path.endsWith(".sas")) setSelectedSasKey(path);
                        else setSelectedSasKey("");
                        setSelectedBlock(null);
                      }}
                      storageKey={`job-${jobId}`}
                      theme={editorDark ? "dark" : "light"}
                    />
                  )}
                </div>
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            <ResizablePanel defaultSize={85}>
              <ResizablePanelGroup orientation="horizontal">
                <ResizablePanel defaultSize={50}>
                  <div className="flex flex-col h-full">
                    <div
                      className="h-8 px-3 text-xs font-medium shrink-0 flex items-center"
                      style={{
                        background: editorDark ? "#1e1e1e" : "#fafafa",
                        color: editorDark ? "#858585" : "#374151",
                        borderBottom: editorDark
                          ? "1px solid #3e3e3e"
                          : "1px solid var(--border)",
                      }}
                    >
                      <img
                        src="/sas.svg"
                        className="h-4 w-4 shrink-0 mr-1.5"
                        alt="SAS"
                      />
                      SAS Source
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
                          onMount={(ed) => {
                            sasEditorRef.current = ed;
                          }}
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

                <ResizablePanel defaultSize={50}>
                  <div className="flex flex-col h-full">
                    <div
                      className="h-8 px-3 text-xs font-medium shrink-0 flex items-center gap-2"
                      style={{
                        background: editorDark ? "#1e1e1e" : "#fafafa",
                        color: editorDark ? "#858585" : "#374151",
                        borderBottom: editorDark
                          ? "1px solid #3e3e3e"
                          : "1px solid var(--border)",
                      }}
                    >
                      <img
                        src="/python.svg"
                        className="h-4 w-4 shrink-0"
                        alt="Python"
                      />
                      <span>Generated Python</span>
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
                          setOverrideRevisionCode(null);
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
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* BOTTOM panel — tabbed output area */}
        <ResizablePanel defaultSize={25} minSize={10}>
          <div
            className="h-full overflow-hidden"
            style={{
              borderTop: "none",
              borderRadius: "0 0 6px 6px",
              border: editorDark
                ? "1px solid #3e3e3e"
                : "1px solid var(--border)",
              background: editorDark ? "#1e1e1e" : undefined,
            }}
          >
            <BottomPanel
              bottomTab={bottomTab}
              setBottomTab={setBottomTab}
              executeResult={executeResult}
              executeError={executeError}
              execOutputTab={execOutputTab}
              setExecOutputTab={setExecOutputTab}
              logAttachments={logAttachments}
              outputAttachments={outputAttachments}
              jobId={jobId}
              changelog={changelog}
              theme={editorDark ? "dark" : "light"}
              onLoadRevisionCode={(code) => setOverrideRevisionCode(code)}
            />
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
