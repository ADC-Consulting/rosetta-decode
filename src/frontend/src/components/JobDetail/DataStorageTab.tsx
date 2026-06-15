import { getJobSchema, patchJobSchema } from "@/api/jobs";
import type { TableSchema } from "@/api/types";
import { Skeleton } from "@/components/ui/skeleton";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useMemo, useState } from "react";

interface DataStorageTabProps {
  jobId: string;
  isReviewable: boolean;
}

// ── Semantic type badge colours ───────────────────────────────────────────────

const SEMANTIC_COLORS: Record<string, string> = {
  String: "bg-muted text-muted-foreground",
  Date: "bg-green-100 text-green-800",
  Timestamp: "bg-teal-100 text-teal-800",
  Decimal: "bg-amber-100 text-amber-800",
  Number: "bg-blue-100 text-blue-800",
  Integer: "bg-blue-100 text-blue-800",
};

function semanticBadgeClasses(type: string): string {
  return SEMANTIC_COLORS[type] ?? "bg-muted text-muted-foreground";
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

// ── Main component ────────────────────────────────────────────────────────────

export default function DataStorageTab({ jobId, isReviewable }: DataStorageTabProps) {
  const [manualSelectedPath, setSelectedPath] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: schemaData } = useQuery({
    queryKey: ["job", jobId, "schema"],
    queryFn: () => getJobSchema(jobId),
    enabled: isReviewable,
  });

  const selectedPath = useMemo(() => {
    if (manualSelectedPath) return manualSelectedPath;
    return schemaData?.tables[0]?.path ?? null;
  }, [manualSelectedPath, schemaData]);

  const handleLibnameRename = async (libname: string, newName: string) => {
    if (!newName || newName === libname) return;
    await patchJobSchema(jobId, { libname_overrides: { [libname]: newName } });
    queryClient.invalidateQueries({ queryKey: ["job", jobId, "schema"] });
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

  return (
    <div className="h-full min-h-0 flex overflow-hidden">
      {/* Left: LIBNAME tree */}
      <div
        className="w-72 shrink-0 border-r border-border overflow-y-auto flex flex-col"
        aria-label="Table list"
      >
        {groupKeys.map((libname) => {
          const tables = groups.get(libname) ?? [];
          return (
            <div
              key={libname ?? "__other__"}
              className="border-b border-border last:border-0"
            >
              {/* Group header */}
              <div className="flex items-center justify-between px-3 py-2 bg-muted/30">
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  {libname ?? "Other"}
                </span>
                {libname && (
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <span>&rarr;</span>
                    <input
                      className={
                        "bg-transparent border-0 border-b border-dashed border-muted-foreground/40 " +
                        "focus:outline-none focus:border-primary text-xs w-20 text-right"
                      }
                      defaultValue={tables[0]?.target_schema ?? libname}
                      onBlur={(e) => handleLibnameRename(libname, e.target.value.trim())}
                      title="Target schema name (click to edit)"
                      aria-label={`Target schema name for ${libname}`}
                    />
                  </div>
                )}
              </div>

              {/* Table rows */}
              {tables.map((table) => (
                <button
                  key={table.path}
                  type="button"
                  onClick={() => setSelectedPath(table.path)}
                  aria-pressed={selectedPath === table.path}
                  className={`w-full flex items-center justify-between px-3 py-2 text-left transition-colors hover:bg-muted/50 ${
                    selectedPath === table.path
                      ? "bg-primary/10 border-l-2 border-primary"
                      : "border-l-2 border-transparent"
                  }`}
                >
                  <span className="font-mono text-xs truncate text-foreground">
                    {table.dataset_name}
                  </span>
                  <span className="text-xs text-muted-foreground shrink-0 ml-1">
                    {table.columns.length > 0 ? `${table.columns.length}` : "—"}
                  </span>
                </button>
              ))}
            </div>
          );
        })}
      </div>

      {/* Right: schema detail */}
      <div className="flex-1 min-w-0 overflow-y-auto">
        {!selectedTable ? (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            Select a table from the list to view its schema.
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="px-4 py-3 border-b border-border">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="font-mono text-sm font-semibold">
                  {selectedTable.dataset_name}
                </span>
                {selectedTable.libname && (
                  <span className="text-xs text-muted-foreground">
                    {selectedTable.libname} &rarr; {selectedTable.target_schema}
                  </span>
                )}
                {selectedTable.row_count != null && (
                  <span className="text-xs text-muted-foreground">
                    {selectedTable.row_count.toLocaleString()} rows
                  </span>
                )}
              </div>
            </div>

            {/* Column table or no-columns notice */}
            {selectedTable.columns.length > 0 ? (
              <table className="w-full text-sm border-collapse">
                <thead className="sticky top-0 bg-background z-10">
                  <tr className="border-b border-border">
                    <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Column
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      SAS type
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Format
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Type
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Label
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {selectedTable.columns.map((col) => {
                    const displayType = col.override_type ?? col.semantic_type;
                    const isOverridden = col.override_type !== null;
                    return (
                      <tr key={col.name} className="border-b border-border last:border-0">
                        <td className="px-3 py-2 font-mono text-xs text-foreground whitespace-nowrap">
                          {col.name}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
                            {col.sas_type}
                          </span>
                        </td>
                        <td className="px-3 py-2 font-mono text-xs text-muted-foreground whitespace-nowrap">
                          {col.sas_format ?? "—"}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {displayType === "Unknown" ? (
                            <span className="text-xs text-muted-foreground">—</span>
                          ) : (
                            <span
                              className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium ${semanticBadgeClasses(displayType)}`}
                            >
                              {displayType}
                              {isOverridden && (
                                <Pencil className="w-3 h-3" aria-label="Overridden type" />
                              )}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-xs text-muted-foreground max-w-xs truncate">
                          {col.label ?? "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <div className="px-4 py-6 space-y-1">
                <p className="text-sm text-muted-foreground">
                  Column metadata not available for this dataset.
                </p>
                <p className="text-xs text-muted-foreground">
                  Schema is extracted from uploaded .sas7bdat and .csv files. Derived datasets
                  show no columns until schema extraction is extended.
                </p>
              </div>
            )}

            {/* DDL block */}
            {selectedTable.ddl && (
              <div className="px-4 py-3 border-t border-border">
                <p className="text-xs font-semibold text-muted-foreground mb-2">DDL</p>
                <pre className="text-xs font-mono bg-muted rounded p-3 overflow-x-auto whitespace-pre">
                  {selectedTable.ddl}
                </pre>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
