import { getJobSchema, patchJobSchema } from "@/api/jobs";
import type { TableSchema } from "@/api/types";
import MonacoEditor from "@/components/MonacoEditor";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Pencil, Settings } from "lucide-react";
import { useTheme } from "next-themes";
import React, { useEffect, useMemo, useState } from "react";
import DataModelERD from "./DataModelERD";
import DataFlowDiagram from "./DataFlowDiagram";

interface DataStorageTabProps {
  jobId: string;
  isReviewable: boolean;
}

const SEMANTIC_TO_PG: Record<string, string> = {
  String: "TEXT",
  Integer: "BIGINT",
  Float: "DOUBLE PRECISION",
  Number: "DOUBLE PRECISION",
  Decimal: "DECIMAL",
  Date: "DATE",
  DateTime: "TIMESTAMP",
  Boolean: "BOOLEAN",
};

function statusDotClass(status: string): string {
  if (status === "migrated") return "bg-green-500";
  if (status === "changed") return "bg-amber-400";
  return "bg-muted-foreground/30";
}

type DiffStatus = "unchanged" | "added" | "dropped";

interface DiffRow {
  name: string;
  status: DiffStatus;
  sas_type: string | null;
  sas_format: string | null;
  semantic_type: string | null;
  sql_type: string | null;
  is_pk: boolean;
  is_fk: boolean;
}

function buildColumnDiff(table: TableSchema): DiffRow[] {
  const sourceMap = new Map(table.columns.map((c) => [c.name.toLowerCase(), c]));
  const targetMap = new Map(table.target_columns.map((c) => [c.name.toLowerCase(), c]));

  const rows: DiffRow[] = [];

  for (const col of table.columns) {
    const key = col.name.toLowerCase();
    const target = targetMap.get(key);
    rows.push({
      name: col.name,
      status: target ? "unchanged" : "dropped",
      sas_type: col.sas_type || null,
      sas_format: col.sas_format,
      semantic_type: col.override_type ?? col.semantic_type,
      sql_type: target?.sql_type ?? null,
      is_pk: target?.is_pk ?? false,
      is_fk: target?.is_fk ?? false,
    });
  }

  for (const col of table.target_columns) {
    const key = col.name.toLowerCase();
    if (!sourceMap.has(key)) {
      rows.push({
        name: col.name,
        status: "added",
        sas_type: null,
        sas_format: null,
        semantic_type: null,
        sql_type: col.sql_type,
        is_pk: col.is_pk,
        is_fk: col.is_fk,
      });
    }
  }

  return rows;
}

// ── Group helpers ─────────────────────────────────────────────────────────────

type GroupedTables = Map<string | null, TableSchema[]>;

function groupTablesByLibname(tables: TableSchema[]): GroupedTables {
  const groups = new Map<string | null, TableSchema[]>();
  for (const table of tables) {
    const key = table.libname ?? null;
    const existing = groups.get(key);
    if (existing) {
      existing.push(table);
    } else {
      groups.set(key, [table]);
    }
  }
  return groups;
}

function sortedGroupKeys(groups: GroupedTables): (string | null)[] {
  const named = [...groups.keys()]
    .filter((k): k is string => k !== null)
    .sort((a, b) => a.localeCompare(b));
  const hasOther = groups.has(null);
  return hasOther ? [...named, null] : named;
}

// ── Schema status badge map ───────────────────────────────────────────────────

const SCHEMA_STATUS_BADGE: Record<string, { label: string; className: string }> = {
  migrated: { label: "Migrated", className: "bg-green-100 text-green-700 border-green-200" },
  changed:  { label: "Changed",  className: "bg-amber-100 text-amber-700 border-amber-200" },
  not_run:  { label: "Not run",  className: "bg-muted text-muted-foreground" },
};

// ── Main component ────────────────────────────────────────────────────────────

type ProjectView = "data-model" | "data-flow";

export default function DataStorageTab({ jobId, isReviewable }: DataStorageTabProps) {
  const [manualSelectedPath, setSelectedPath] = useState<string | null>(null);
  const [projectView, setProjectView] = useState<ProjectView | null>(null);
  const [ddlOpen, setDdlOpen] = useState(false);
  const [editingLibname, setEditingLibname] = useState<string | null>(null);
  const [sidebarView, setSidebarView] = useState<"source" | "target">("source");
  const [sourceSelectedPath, setSourceSelectedPath] = useState<string | null>(null);
  const [targetSelectedPath, setTargetSelectedPath] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { resolvedTheme } = useTheme();
  const monacoTheme = resolvedTheme === "dark" ? "sas-dark" : "sas-light";

  const { data: schemaData } = useQuery({
    queryKey: ["job", jobId, "schema"],
    queryFn: () => getJobSchema(jobId),
    enabled: isReviewable,
  });

  const selectedPath = useMemo(() => {
    if (manualSelectedPath) return manualSelectedPath;
    return schemaData?.tables[0]?.path ?? null;
  }, [manualSelectedPath, schemaData]);

  useEffect(() => {
    const table = schemaData?.tables.find((t) => t.path === selectedPath);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDdlOpen(table?.ddl_source === "target");
  }, [selectedPath, schemaData]);

  const handleLibnameRename = async (libname: string, newName: string) => {
    if (!newName || newName === libname) return;
    await patchJobSchema(jobId, { libname_overrides: { [libname]: newName } });
    queryClient.invalidateQueries({ queryKey: ["job", jobId, "schema"] });
  };

  const handleSidebarViewChange = (v: "source" | "target") => {
    setSidebarView(v);
    if (v === "source" && sourceSelectedPath) setSelectedPath(sourceSelectedPath);
    if (v === "target" && targetSelectedPath) setSelectedPath(targetSelectedPath);
  };

  // ── Guard states ─────────────────────────────────────────────────────────────

  if (!isReviewable) {
    return (
      <p className="text-sm text-muted-foreground p-4">
        Schema available once migration completes.
      </p>
    );
  }

  if (!schemaData) {
    return <Skeleton className="h-full w-full rounded" />;
  }

  if (schemaData.tables.length === 0) {
    return (
      <p className="text-sm text-muted-foreground p-4">
        No schema data available. Run a migration to extract table metadata.
      </p>
    );
  }

  // ── Build grouped data ────────────────────────────────────────────────────────

  const groups = groupTablesByLibname(schemaData.tables);
  const groupKeys = sortedGroupKeys(groups);
  const selectedTable = schemaData.tables.find((t) => t.path === selectedPath) ?? null;

  const namedKeys = groupKeys.filter((k): k is string => k !== null);
  const outputTables = groups.get(null) ?? [];

  return (
    <div className="h-full min-h-0 flex overflow-hidden">
      {/* Left: LIBNAME tree */}
      <div
        className="w-72 shrink-0 border-r border-border overflow-y-auto flex flex-col"
        aria-label="Table list"
      >
        {/* Toggle strip */}
        <div className="px-3 pt-3 pb-2 shrink-0 border-b border-border">
          <div className="flex items-center gap-1">
            {(["source", "target"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => handleSidebarViewChange(v)}
                className={[
                  "px-2 py-0.5 rounded text-[11px] font-medium border transition-colors",
                  sidebarView === v
                    ? "bg-foreground text-background border-foreground"
                    : "bg-transparent text-muted-foreground border-border hover:border-foreground/40",
                ].join(" ")}
              >
                {v.charAt(0).toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground/60 mt-1.5">
            {sidebarView === "source"
              ? "SAS input datasets · grouped by libname"
              : "Proposed output tables from migration"}
          </p>
        </div>

        {/* Source view */}
        {sidebarView === "source" && namedKeys.length > 0 && (
          <div>
            <div className="px-3 py-1.5 bg-muted/50 border-b border-border">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                Source data
              </span>
            </div>
            {namedKeys.map((libname) => {
              const tables = groups.get(libname) ?? [];
              const nameCount = new Map<string, number>();
              tables.forEach((t) => nameCount.set(t.dataset_name, (nameCount.get(t.dataset_name) ?? 0) + 1));
              return (
                <div key={libname} className="border-b border-border last:border-0">
                  {/* Sub-group header */}
                  <div className="flex items-center justify-between pl-5 pr-3 py-1.5 bg-muted/20">
                    <span className="flex items-center">
                      <span className="text-xs font-semibold text-foreground tracking-wide">
                        {libname}
                      </span>
                      <span className="text-xs text-muted-foreground/50 font-normal ml-1">
                        · {tables.length} {tables.length === 1 ? "table" : "tables"}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => setEditingLibname(editingLibname === libname ? null : libname)}
                      className="text-muted-foreground/50 hover:text-muted-foreground transition-colors"
                      title="Rename target schema"
                    >
                      <Settings className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  {editingLibname === libname && (
                    <div className="flex items-center gap-2 pl-5 pr-3 py-1.5 bg-muted/10 border-b border-border text-xs">
                      <span className="text-muted-foreground shrink-0">Target schema:</span>
                      <input
                        className="flex-1 bg-transparent border-b border-dashed border-muted-foreground/40 focus:outline-none focus:border-primary text-xs"
                        defaultValue={tables[0]?.target_schema ?? libname}
                        onBlur={(e) => {
                          handleLibnameRename(libname, e.target.value.trim());
                          setEditingLibname(null);
                        }}
                        autoFocus
                      />
                    </div>
                  )}
                  {/* Table rows — indented */}
                  {tables.map((table) => (
                    <button
                      key={table.path}
                      type="button"
                      onClick={() => { setSelectedPath(table.path); setSourceSelectedPath(table.path); }}
                      aria-pressed={selectedPath === table.path}
                      className={`w-full flex items-center gap-2 pl-7 pr-3 py-2 text-left transition-colors hover:bg-muted/50 ${
                        selectedPath === table.path
                          ? "bg-primary/10 border-l-2 border-primary"
                          : "border-l-2 border-transparent"
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full shrink-0 ${statusDotClass(table.schema_status)}`} aria-label={table.schema_status} />
                      <span className="font-mono text-xs truncate text-foreground flex-1 text-left">
                        {table.dataset_name}
                        {(nameCount.get(table.dataset_name) ?? 0) > 1 && (
                          <span className="block text-xs text-muted-foreground/60 font-sans font-normal truncate">
                            {table.path.split("/").at(-1) ?? table.path}
                          </span>
                        )}
                        {table.description && (
                          <span className="block text-xs text-muted-foreground/70 font-sans font-normal truncate">
                            {table.description}
                          </span>
                        )}
                      </span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {table.columns.length > 0 ? `${table.columns.length} cols` : "—"}
                      </span>
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
        )}

        {/* Migration view */}
        {sidebarView === "target" && (
          <div>
            <div className="px-3 py-1.5 bg-muted/50 border-b border-border">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                Output
              </span>
            </div>
            {outputTables.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
                <svg
                  width={28}
                  height={28}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-muted-foreground/30"
                >
                  <rect x={3} y={3} width={18} height={18} rx={2} />
                  <line x1={3} y1={9} x2={21} y2={9} />
                  <line x1={3} y1={15} x2={21} y2={15} />
                  <line x1={9} y1={3} x2={9} y2={21} />
                  <line x1={15} y1={3} x2={15} y2={21} />
                </svg>
                <p className="text-xs text-muted-foreground">No output tables yet.</p>
                <p className="text-xs text-muted-foreground/60">Run a migration to generate output.</p>
              </div>
            ) : (
              (() => {
                const nameCount = new Map<string, number>();
                outputTables.forEach((t) => nameCount.set(t.dataset_name, (nameCount.get(t.dataset_name) ?? 0) + 1));
                return outputTables.map((table) => (
                  <button
                    key={table.path}
                    type="button"
                    onClick={() => { setSelectedPath(table.path); setTargetSelectedPath(table.path); }}
                    aria-pressed={selectedPath === table.path}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-muted/50 ${
                      selectedPath === table.path
                        ? "bg-primary/10 border-l-2 border-primary"
                        : "border-l-2 border-transparent"
                    }`}
                  >
                    <span className={`w-2 h-2 rounded-full shrink-0 ${statusDotClass(table.schema_status)}`} aria-label={table.schema_status} />
                    <span className="font-mono text-xs truncate text-foreground flex-1 text-left">
                      {table.dataset_name}
                      {(nameCount.get(table.dataset_name) ?? 0) > 1 && (
                        <span className="block text-xs text-muted-foreground/60 font-sans font-normal truncate">
                          {table.path.split("/").at(-1) ?? table.path}
                        </span>
                      )}
                      {table.description && (
                        <span className="block text-xs text-muted-foreground/70 font-sans font-normal truncate">
                          {table.description}
                        </span>
                      )}
                    </span>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {(() => {
                        const count = table.target_columns.length > 0
                          ? table.target_columns.length
                          : table.columns.length;
                        return count > 0 ? `${count} cols` : "—";
                      })()}
                    </span>
                  </button>
                ));
              })()
            )}
          </div>
        )}

        {/* Legend — only when 2+ distinct statuses exist */}
        {(() => {
          const statuses = new Set(schemaData.tables.map((t) => t.schema_status));
          if (statuses.size < 2) return null;
          return (
            <div className="mt-auto border-t border-border px-3 py-2 flex flex-col gap-1">
              {[
                { cls: "bg-green-500", label: "Migrated" },
                { cls: "bg-amber-400", label: "Changed" },
                { cls: "bg-muted-foreground/30", label: "Not run" },
              ].map(({ cls, label }) => (
                <div key={label} className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${cls}`} />
                  <span className="text-xs text-muted-foreground">{label}</span>
                </div>
              ))}
            </div>
          );
        })()}
      </div>

      {/* Right: column details / project view */}
      <div className="flex-1 min-w-0 flex flex-col min-h-0">
        {projectView !== null ? (
          /* Project view mode */
          <div className="flex-1 min-h-0 flex flex-col">
            {/* Project view header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-border shrink-0">
              <span className="text-sm font-semibold text-foreground">
                {projectView === "data-model" ? "Data model" : "Data flow"}
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() =>
                    setProjectView(projectView === "data-model" ? "data-flow" : "data-model")
                  }
                  className="px-2 py-1 text-xs rounded border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                >
                  {projectView === "data-model" ? "Data flow" : "Data model"}
                </button>
                <button
                  type="button"
                  onClick={() => setProjectView(null)}
                  className="px-2 py-1 text-xs rounded border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  title="Return to table schema"
                >
                  ✕
                </button>
              </div>
            </div>
            {/* Diagram */}
            <div className="flex-1 min-h-0">
              {projectView === "data-model" ? (
                <DataModelERD
                  schema={schemaData}
                  selectedTable={selectedTable?.dataset_name ?? null}
                  onTableSelect={(name) => {
                    const match = schemaData.tables.find((t) => t.dataset_name === name);
                    if (!match) return;
                    if (match.libname === null) {
                      setSidebarView("target");
                      setTargetSelectedPath(match.path);
                    } else {
                      setSidebarView("source");
                      setSourceSelectedPath(match.path);
                    }
                    setSelectedPath(match.path);
                  }}
                />
              ) : (
                <DataFlowDiagram
                  jobId={jobId}
                  selectedTable={selectedTable?.dataset_name ?? null}
                  onTableSelect={(name) => {
                    const match = schemaData.tables.find((t) => t.dataset_name === name);
                    if (!match) return; // intermediate node — no sidebar entry, silently ignore
                    setSidebarView("target");
                    setTargetSelectedPath(match.path);
                    setSelectedPath(match.path);
                  }}
                  outputTableNames={outputTables.map((t) => t.dataset_name)}
                />
              )}
            </div>
          </div>
        ) : (
          /* Column details mode */
          <div className="flex-1 min-h-0 overflow-y-auto">
            {!selectedTable ? (
              <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                Select a table from the list to view its schema.
              </div>
            ) : (
              <>
                {/* Header */}
                <div className="px-4 py-3 border-b border-border flex items-start justify-between gap-2">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="font-mono text-sm font-semibold">
                      {selectedTable.dataset_name}
                    </span>
                    {selectedTable.description && (
                      <p className="text-xs text-muted-foreground mt-0.5 max-w-sm">
                        {selectedTable.description}
                      </p>
                    )}
                    {selectedTable.libname && selectedTable.libname !== selectedTable.target_schema && (
                      <span className="text-xs text-muted-foreground">
                        {selectedTable.libname} &rarr; {selectedTable.target_schema}
                      </span>
                    )}
                    {selectedTable.row_count != null && !selectedTable.description && (
                      <span className="text-xs text-muted-foreground">
                        {selectedTable.row_count.toLocaleString()} rows
                      </span>
                    )}
                    {selectedTable.libname === null ? (
                      (() => {
                        const b = SCHEMA_STATUS_BADGE[selectedTable.schema_status]
                          ?? SCHEMA_STATUS_BADGE.not_run;
                        return (
                          <Badge variant="outline" className={b.className}>{b.label}</Badge>
                        );
                      })()
                    ) : (
                      <span className="text-xs text-muted-foreground">Source SAS data · read only</span>
                    )}
                  </div>
                  {selectedTable.libname === null && (
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => setProjectView("data-model")}
                        className="px-2 py-1 text-xs rounded border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        title="View all tables as entity diagram"
                      >
                        Data model
                      </button>
                      <button
                        type="button"
                        onClick={() => setProjectView("data-flow")}
                        className="px-2 py-1 text-xs rounded border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        title="View full pipeline data flow"
                      >
                        Data flow
                      </button>
                    </div>
                  )}
                </div>

                {/* Column table or no-columns notice */}
                {selectedTable.libname !== null ? (
                  /* Source table — simple column list, no diff */
                  selectedTable.columns.length > 0 ? (
                    <table className="w-full text-sm border-collapse">
                      <thead className="sticky top-0 bg-background z-10">
                        <tr className="border-b border-border">
                          <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Column</th>
                          <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">SAS type</th>
                          <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Format</th>
                          <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Label</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedTable.columns.map((col) => (
                          <tr key={col.name} className="border-b border-border last:border-0">
                            <td className="px-3 py-2 font-mono text-xs text-foreground whitespace-nowrap">{col.name}</td>
                            <td className="px-3 py-2 whitespace-nowrap">
                              {col.sas_type ? (
                                <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
                                  {col.sas_type}
                                </span>
                              ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                              )}
                            </td>
                            <td className="px-3 py-2 font-mono text-xs text-muted-foreground whitespace-nowrap">
                              {col.sas_format ?? "—"}
                            </td>
                            <td className="px-3 py-2 text-xs text-muted-foreground max-w-xs truncate">
                              {col.label ?? "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="px-4 py-6">
                      <p className="text-sm text-muted-foreground">
                        Column schema not available — no .sas7bdat file or source declarations found.
                      </p>
                    </div>
                  )
                ) : (
                  /* Output table — existing diff/status view */
                  selectedTable.schema_status === "not_run" && selectedTable.columns.length === 0 ? (
                    <div className="px-4 py-6">
                      <p className="text-sm text-muted-foreground">
                        Column schema not available — no .sas7bdat file or source declarations found.
                      </p>
                    </div>
                  ) : selectedTable.target_columns.length > 0 ? (
                    <>
                      <div className="px-3 py-2 flex items-center justify-between border-b border-border bg-muted/10 text-xs text-muted-foreground">
                        <span>SAS source schema vs migration output</span>
                        <span className="flex items-center gap-3">
                          <span className="flex items-center gap-1">
                            <span className="font-bold text-green-600">+</span> Added
                          </span>
                          <span className="flex items-center gap-1">
                            <span className="font-bold text-red-500">✗</span> Dropped
                          </span>
                          <span className="flex items-center gap-1">
                            <span className="text-muted-foreground/40">✓</span> Unchanged
                          </span>
                        </span>
                      </div>
                      <table className="w-full text-sm border-collapse">
                        <thead className="sticky top-0 bg-background z-10">
                          <tr className="border-b border-border">
                            <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide w-6" />
                            <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Column</th>
                            <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">SAS type</th>
                            <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">SQL type</th>
                            <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Flags</th>
                          </tr>
                        </thead>
                        <tbody>
                          {buildColumnDiff(selectedTable).map((row) => (
                            <tr
                              key={row.name}
                              className={`border-b border-border last:border-0 ${
                                row.status === "added" ? "bg-green-50 dark:bg-green-950/20" :
                                row.status === "dropped" ? "bg-red-50 dark:bg-red-950/20" : ""
                              }`}
                            >
                              <td className="px-3 py-2 whitespace-nowrap">
                                {row.status === "added" ? (
                                  <span className="text-xs font-bold text-green-600" title="Added in output">+</span>
                                ) : row.status === "dropped" ? (
                                  <span className="text-xs font-bold text-red-500" title="Dropped in output">✗</span>
                                ) : (
                                  <span className="text-xs text-muted-foreground/50" title="Unchanged">✓</span>
                                )}
                              </td>
                              <td className="px-3 py-2 font-mono text-xs text-foreground whitespace-nowrap">{row.name}</td>
                              <td className="px-3 py-2 whitespace-nowrap">
                                {row.sas_type ? (
                                  <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
                                    {row.sas_type}
                                  </span>
                                ) : (
                                  <span className="text-xs text-muted-foreground">—</span>
                                )}
                              </td>
                              <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">
                                {row.sql_type ? (
                                  <span className="font-mono text-xs text-muted-foreground bg-muted/60 rounded px-1.5 py-0.5">{row.sql_type}</span>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </td>
                              <td className="px-3 py-2 text-xs whitespace-nowrap">
                                {row.is_pk && (
                                  <span className="inline-flex items-center rounded px-1 py-0.5 text-xs font-semibold bg-yellow-100 text-yellow-800 mr-1">PK</span>
                                )}
                                {row.is_fk && (
                                  <span className="inline-flex items-center rounded px-1 py-0.5 text-xs font-semibold bg-blue-100 text-blue-800">FK</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </>
                  ) : selectedTable.columns.length > 0 ? (
                    <>
                      <div className="px-3 py-2 border-b border-border bg-muted/10 text-xs flex items-center gap-2">
                        <span className="font-medium">Proposed output schema</span>
                        <span className="text-muted-foreground">· inferred from source columns</span>
                        <span className="inline-flex items-center rounded px-1.5 py-0.5 font-medium bg-blue-100 text-blue-700">
                          PostgreSQL
                        </span>
                      </div>
                      <table className="w-full text-sm border-collapse">
                        <thead className="sticky top-0 bg-background z-10">
                          <tr className="border-b border-border">
                            <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Column</th>
                            <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">PostgreSQL type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedTable.columns.map((col) => {
                            const semanticType = col.override_type ?? col.semantic_type;
                            const pgType = SEMANTIC_TO_PG[semanticType];
                            const isOverridden = col.override_type !== null;
                            return (
                              <tr key={col.name} className="border-b border-border last:border-0">
                                <td className="px-3 py-2 font-mono text-xs text-foreground whitespace-nowrap">
                                  {col.name}
                                </td>
                                <td className="px-3 py-2 whitespace-nowrap">
                                  {pgType ? (
                                    <span className="font-mono text-xs text-muted-foreground bg-muted/60 rounded px-1.5 py-0.5 inline-flex items-center gap-1">
                                      {pgType}
                                      {isOverridden && (
                                        <Pencil className="w-3 h-3" aria-label="Overridden type" />
                                      )}
                                    </span>
                                  ) : (
                                    <span className="text-xs text-muted-foreground">—</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </>
                  ) : (
                    <div className="px-4 py-6">
                      <p className="text-sm text-muted-foreground">
                        Column schema not available — no .sas7bdat file or source declarations found.
                      </p>
                    </div>
                  )
                )}

                {/* DDL collapsible — output tables only */}
                {selectedTable.libname === null && <div className="border-t border-border">
                  <Collapsible open={ddlOpen} onOpenChange={setDdlOpen}>
                    <div className="flex items-center justify-between pr-4">
                      <CollapsibleTrigger
                        className="flex flex-1 items-center gap-2 px-4 py-2.5 text-xs font-semibold
                          text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-colors
                          select-none"
                        aria-label="Toggle DDL panel"
                      >
                        {ddlOpen ? (
                          <ChevronDown className="w-3.5 h-3.5 shrink-0" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5 shrink-0" />
                        )}
                        <span className="flex items-center gap-2">
                          Table definition
                          {selectedTable.ddl_source === "source_estimated" && (
                            <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-amber-100 text-amber-800">
                              estimated from SAS
                            </span>
                          )}
                        </span>
                      </CollapsibleTrigger>
                    </div>
                    <CollapsibleContent>
                      {selectedTable.ddl ? (
                        <div className="px-4 pb-4">
                          <MonacoEditor
                            value={selectedTable.ddl}
                            language="sql"
                            readOnly
                            height="240px"
                            theme={monacoTheme}
                          />
                        </div>
                      ) : (
                        <p className="px-4 pb-4 text-xs text-muted-foreground">
                          DDL not available
                        </p>
                      )}
                    </CollapsibleContent>
                  </Collapsible>
                </div>}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
