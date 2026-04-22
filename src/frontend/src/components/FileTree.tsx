import { cn } from "@/lib/utils";
import {
  ChevronDown,
  ChevronRight,
  File,
  FileCode,
  FileText,
  Folder,
  FolderOpen,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type TreeNode = {
  name: string;
  path: string;
  type: "file" | "dir";
  children?: TreeNode[];
};

export interface FileTreeProps {
  paths: string[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
  storageKey: string;
  theme?: "dark" | "light";
}

// ---------------------------------------------------------------------------
// Build tree from flat paths
// ---------------------------------------------------------------------------

// eslint-disable-next-line react-refresh/only-export-components
export function buildTree(paths: string[]): TreeNode[] {
  const root: TreeNode[] = [];
  const dirMap = new Map<string, TreeNode>();

  const getOrCreateDir = (segments: string[], depth: number): TreeNode[] => {
    if (depth === 0) return root;
    const pathKey = segments.slice(0, depth).join("/");
    if (dirMap.has(pathKey)) {
      return dirMap.get(pathKey)!.children!;
    }
    const parent = getOrCreateDir(segments, depth - 1);
    const node: TreeNode = {
      name: segments[depth - 1],
      path: pathKey,
      type: "dir",
      children: [],
    };
    parent.push(node);
    dirMap.set(pathKey, node);
    return node.children!;
  };

  for (const p of paths) {
    const segments = p.split("/").filter(Boolean);
    const parentChildren = getOrCreateDir(segments, segments.length - 1);
    parentChildren.push({
      name: segments[segments.length - 1],
      path: p,
      type: "file",
    });
  }

  const sortNodes = (nodes: TreeNode[]): TreeNode[] => {
    const dirs = nodes
      .filter((n) => n.type === "dir")
      .sort((a, b) =>
        a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
      );
    const files = nodes
      .filter((n) => n.type === "file")
      .sort((a, b) =>
        a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
      );
    return [
      ...dirs.map((d) => ({ ...d, children: sortNodes(d.children ?? []) })),
      ...files,
    ];
  };

  return sortNodes(root);
}

// ---------------------------------------------------------------------------
// File icon by extension
// ---------------------------------------------------------------------------

function FileIcon({ name }: { name: string }): React.ReactElement {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "sas" || ext === "py")
    return (
      <FileCode size={13} className="shrink-0 text-[#75beff] opacity-80" />
    );
  if (ext === "csv")
    return (
      <FileText size={13} className="shrink-0 text-emerald-400 opacity-80" />
    );
  return (
    <File size={13} className="shrink-0 text-muted-foreground opacity-70" />
  );
}

// ---------------------------------------------------------------------------
// Flatten visible nodes for keyboard nav
// ---------------------------------------------------------------------------

type FlatRow = { node: TreeNode; depth: number };

function flattenVisible(
  nodes: TreeNode[],
  expanded: Set<string>,
  depth = 0,
): FlatRow[] {
  const rows: FlatRow[] = [];
  for (const node of nodes) {
    rows.push({ node, depth });
    if (node.type === "dir" && expanded.has(node.path) && node.children) {
      rows.push(...flattenVisible(node.children, expanded, depth + 1));
    }
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Filter tree for search
// ---------------------------------------------------------------------------

function filterTree(nodes: TreeNode[], query: string): TreeNode[] {
  if (!query) return nodes;
  const q = query.toLowerCase();
  const filtered: TreeNode[] = [];
  for (const node of nodes) {
    if (node.type === "file") {
      if (node.name.toLowerCase().includes(q)) filtered.push(node);
    } else {
      const filteredChildren = filterTree(node.children ?? [], query);
      if (filteredChildren.length > 0 || node.name.toLowerCase().includes(q)) {
        filtered.push({ ...node, children: filteredChildren });
      }
    }
  }
  return filtered;
}

// ---------------------------------------------------------------------------
// FileTree component
// ---------------------------------------------------------------------------

export default function FileTree({
  paths,
  selectedPath,
  onSelect,
  storageKey,
  theme = "dark",
}: FileTreeProps): React.ReactElement {
  const bg = theme === "light" ? "#fff" : "#1e1e1e";
  const inputBg = theme === "light" ? "#f3f4f6" : "#2d2d2d";
  const inputColor = theme === "light" ? "#111" : "#d4d4d4";
  const inputBorder = theme === "light" ? "#d1d5db" : "#444";
  const rowHoverBg =
    theme === "light" ? "rgba(0,0,0,0.06)" : "rgba(255,255,255,0.06)";
  const rowSelectedBg = theme === "light" ? "#e8e8e8" : "#37373d";
  const rowColor = theme === "light" ? "#111" : "#d4d4d4";
  const lsKey = `filetree-expanded-${storageKey}`;

  const [expanded, setExpanded] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(lsKey);
      if (raw) return new Set(JSON.parse(raw) as string[]);
    } catch {
      // ignore
    }
    // Default: all directories expanded
    const allDirs = new Set<string>();
    const collectDirs = (nodes: TreeNode[]) => {
      for (const n of nodes) {
        if (n.type === "dir") {
          allDirs.add(n.path);
          if (n.children) collectDirs(n.children);
        }
      }
    };
    collectDirs(buildTree(paths));
    return allDirs;
  });

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [focusedPath, setFocusedPath] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Persist expanded state
  useEffect(() => {
    try {
      localStorage.setItem(lsKey, JSON.stringify([...expanded]));
    } catch {
      // ignore
    }
  }, [expanded, lsKey]);

  // Debounce search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 150);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [search]);

  // When search active, expand all matched dirs
  const tree = useMemo(() => buildTree(paths), [paths]);

  const displayTree = useMemo(
    () => filterTree(tree, debouncedSearch),
    [tree, debouncedSearch],
  );

  // When search active, treat all dirs as expanded
  const effectiveExpanded = useMemo<Set<string>>(() => {
    if (!debouncedSearch) return expanded;
    const all = new Set<string>();
    const collectDirs = (nodes: TreeNode[]) => {
      for (const n of nodes) {
        if (n.type === "dir") {
          all.add(n.path);
          collectDirs(n.children ?? []);
        }
      }
    };
    collectDirs(displayTree);
    return all;
  }, [debouncedSearch, displayTree, expanded]);

  const visibleRows = useMemo(
    () => flattenVisible(displayTree, effectiveExpanded),
    [displayTree, effectiveExpanded],
  );

  const toggleDir = useCallback((path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const idx = visibleRows.findIndex((r) => r.node.path === focusedPath);
      if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = visibleRows[idx + 1];
        if (next) setFocusedPath(next.node.path);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const prev = visibleRows[idx - 1];
        if (prev) setFocusedPath(prev.node.path);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        const row = visibleRows[idx];
        if (row?.node.type === "dir" && !effectiveExpanded.has(row.node.path)) {
          toggleDir(row.node.path);
        }
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        const row = visibleRows[idx];
        if (!row) return;
        if (row.node.type === "dir" && effectiveExpanded.has(row.node.path)) {
          toggleDir(row.node.path);
        } else {
          // Go to parent
          const parentPath = row.node.path.split("/").slice(0, -1).join("/");
          if (parentPath) setFocusedPath(parentPath);
        }
      } else if (e.key === "Enter") {
        const row = visibleRows[idx];
        if (row?.node.type === "file") onSelect(row.node.path);
      }
    },
    [visibleRows, focusedPath, effectiveExpanded, toggleDir, onSelect],
  );

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{ background: bg }}
    >
      {/* Search */}
      <div className="px-2 py-1.5 border-b border-border shrink-0">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search files…"
          className="w-full rounded px-2 py-0.5 text-[12px] focus:outline-none focus:ring-1 focus:ring-ring"
          style={{
            background: inputBg,
            color: inputColor,
            border: `1px solid ${inputBorder}`,
          }}
        />
      </div>

      {/* Tree */}
      <div
        ref={containerRef}
        role="tree"
        tabIndex={0}
        onKeyDown={handleKeyDown}
        className="flex-1 overflow-y-auto overflow-x-hidden py-1 focus:outline-none"
      >
        {visibleRows.map(({ node, depth }) => {
          const isExpanded = effectiveExpanded.has(node.path);
          const isSelected = node.path === selectedPath;
          const isFocused = node.path === focusedPath;
          const indentPx = depth * 12;

          return (
            <div
              key={node.path}
              role="treeitem"
              aria-selected={node.type === "file" ? isSelected : undefined}
              aria-expanded={node.type === "dir" ? isExpanded : undefined}
              style={{
                paddingLeft: indentPx,
                color: rowColor,
                background: isSelected ? rowSelectedBg : undefined,
              }}
              className={cn(
                "relative flex items-center gap-1 h-6 pr-2 text-[13px] cursor-pointer select-none",
                !isSelected && "hover:bg-[var(--row-hover)]",
                isFocused && !isSelected && "ring-1 ring-inset ring-ring",
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
                setFocusedPath(node.path);
                if (node.type === "dir") toggleDir(node.path);
                else onSelect(node.path);
              }}
            >
              {/* Vertical guide line */}
              {depth > 0 && (
                <span
                  className="absolute top-0 bottom-0 border-l border-border pointer-events-none"
                  style={{ left: indentPx - 6 }}
                />
              )}

              {/* Chevron / spacer */}
              <span className="shrink-0 w-3 flex items-center justify-center">
                {node.type === "dir" ? (
                  isExpanded ? (
                    <ChevronDown size={12} className="text-muted-foreground" />
                  ) : (
                    <ChevronRight size={12} className="text-muted-foreground" />
                  )
                ) : null}
              </span>

              {/* Icon */}
              {node.type === "dir" ? (
                isExpanded ? (
                  <FolderOpen
                    size={13}
                    className="shrink-0 text-yellow-400 opacity-80"
                  />
                ) : (
                  <Folder
                    size={13}
                    className="shrink-0 text-yellow-400 opacity-70"
                  />
                )
              ) : (
                <FileIcon name={node.name} />
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
