import type { JobSummary } from "@/api/types";
import { cn } from "@/lib/utils";
import { ChevronLeft, ChevronRight, Upload, X } from "lucide-react";
import { useState } from "react";
import MigrationCard from "./MigrationCard";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem("migration-panel-collapsed") === "true";
  } catch {
    return false;
  }
}

const ICON_COL = 56;
const ICON_LEFT = (ICON_COL - 18) / 2;
const LABEL_WIDTH = 140;

interface MigrationPanelProps {
  jobs: JobSummary[] | undefined;
  isLoading: boolean;
  selectedJobId: string | null;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onSelectJob: (job: JobSummary) => void;
  onSwitchToUpload: () => void;
  onClose?: () => void;
}

export default function MigrationPanel({
  jobs,
  isLoading,
  selectedJobId,
  searchQuery,
  onSearchChange,
  onSelectJob,
  onSwitchToUpload,
  onClose,
}: MigrationPanelProps): React.ReactElement {
  const [collapsed, setCollapsed] = useState<boolean>(readCollapsed);

  function toggle(): void {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem("migration-panel-collapsed", String(next));
    } catch {
      // ignore
    }
  }

  const filteredJobs = jobs?.filter(
    (j) =>
      searchQuery === "" ||
      j.name?.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <aside
      aria-label="Migrations panel"
      style={{ width: collapsed ? ICON_COL : 280 }}
      className="relative flex flex-col h-screen shrink-0 bg-background border-l border-border transition-[width] duration-200 ease-in-out"
    >
      {/* Header — matches AppSidebar logo row */}
      <div
        className="flex items-center h-14 border-b border-border shrink-0 overflow-hidden"
        style={{ paddingLeft: (ICON_COL - 20) / 2 }}
      >
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground shrink-0"
            aria-label="Close migrations panel"
          >
            <X size={20} />
          </button>
        )}
        <span
          className="text-sm font-semibold text-foreground whitespace-nowrap overflow-hidden transition-[width,opacity,margin] duration-200 ease-in-out"
          style={{
            width: collapsed ? 0 : LABEL_WIDTH,
            opacity: collapsed ? 0 : 1,
            marginLeft: collapsed ? 0 : 10,
          }}
        >
          Migrations
        </span>
      </div>

      {/* Search row — same h-10 as nav rows */}
      <div
        className={cn(
          "flex items-center h-10 border-b border-border shrink-0 overflow-hidden",
        )}
        style={{ paddingLeft: ICON_LEFT, paddingRight: ICON_LEFT }}
      >
        <input
          type="search"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search…"
          className={cn(
            "bg-transparent text-sm outline-none text-foreground placeholder:text-muted-foreground",
            "whitespace-nowrap overflow-hidden transition-[width,opacity] duration-200 ease-in-out",
          )}
          style={{
            width: collapsed ? 0 : "100%",
            opacity: collapsed ? 0 : 1,
          }}
          aria-label="Search migrations"
          tabIndex={collapsed ? -1 : 0}
        />
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto py-2">
        {isLoading && (
          <div className="flex justify-center py-4">
            <div className="size-5 rounded-full border-2 border-border border-t-foreground animate-spin" />
          </div>
        )}

        {!isLoading &&
          filteredJobs?.map((job) => (
            <div key={job.job_id} className="group/job relative">
              <div
                className={cn("overflow-hidden", collapsed && "cursor-pointer")}
                onClick={() => collapsed && onSelectJob(job)}
              >
                {collapsed ? (
                  /* Collapsed: show a small indicator, same h-10 as nav rows */
                  <div
                    className={cn(
                      "flex items-center justify-center h-10",
                      "text-sm text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer",
                      job.job_id === selectedJobId &&
                        "bg-muted text-foreground font-medium",
                    )}
                  >
                    <span className="size-2 rounded-full bg-current shrink-0" />
                  </div>
                ) : (
                  <MigrationCard
                    job={job}
                    isSelected={job.job_id === selectedJobId}
                    onSelect={() => onSelectJob(job)}
                  />
                )}
              </div>

              {/* Tooltip — appears to the LEFT (right-full → left-full mirror) */}
              <div
                aria-hidden="true"
                className={cn(
                  "pointer-events-none absolute right-full top-1/2 -translate-y-1/2 mr-3 z-50",
                  "rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background whitespace-nowrap",
                  "opacity-0 transition-opacity duration-100",
                  collapsed ? "group-hover/job:opacity-100" : "hidden",
                )}
              >
                {job.name ?? job.job_id}
              </div>
            </div>
          ))}

        {!isLoading && (filteredJobs?.length ?? 0) === 0 && (
          <p
            className={cn(
              "text-xs text-muted-foreground py-4 whitespace-nowrap overflow-hidden transition-[opacity] duration-200 ease-in-out",
              collapsed && "opacity-0",
            )}
            style={{ paddingLeft: ICON_LEFT }}
          >
            No migrations found.
          </p>
        )}
      </div>

      {/* Footer — matches AppSidebar bottom toggles */}
      <div className="shrink-0 border-t border-border">
        {/* Upload button */}
        <div className="group/upload relative">
          <button
            type="button"
            onClick={onSwitchToUpload}
            aria-label="Upload files instead"
            className="flex items-center h-10 w-full overflow-hidden text-sm text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
            style={{ paddingLeft: ICON_LEFT }}
          >
            <Upload size={18} className="shrink-0" />
            <span
              className="whitespace-nowrap overflow-hidden text-ellipsis transition-[width,opacity,margin] duration-200 ease-in-out"
              style={{
                width: collapsed ? 0 : LABEL_WIDTH,
                opacity: collapsed ? 0 : 1,
                marginLeft: collapsed ? 0 : 12,
              }}
            >
              Upload files instead
            </span>
          </button>

          <div
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute right-full top-1/2 -translate-y-1/2 mr-3 z-50",
              "rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background whitespace-nowrap",
              "opacity-0 transition-opacity duration-100",
              collapsed ? "group-hover/upload:opacity-100" : "hidden",
            )}
          >
            Upload files
          </div>
        </div>

        {/* Collapse/expand toggle */}
        <div className="group/toggle relative">
          <button
            type="button"
            onClick={toggle}
            aria-label={collapsed ? "Expand panel" : "Collapse panel"}
            className="flex items-center h-10 w-full overflow-hidden text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
            style={{ paddingLeft: ICON_LEFT }}
          >
            {/* Mirrored chevrons: collapse → right, expand → left */}
            {collapsed ? (
              <ChevronLeft size={18} className="shrink-0" />
            ) : (
              <ChevronRight size={18} className="shrink-0" />
            )}
            <span
              className="text-sm whitespace-nowrap overflow-hidden transition-[width,opacity,margin] duration-200 ease-in-out"
              style={{
                width: 0,
                opacity: 0,
                marginLeft: 0,
              }}
            >
              Collapse
            </span>
          </button>

          <div
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute right-full top-1/2 -translate-y-1/2 mr-3 z-50",
              "rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background whitespace-nowrap",
              "opacity-0 transition-opacity duration-100",
              collapsed ? "group-hover/toggle:opacity-100" : "hidden",
            )}
          >
            Expand
          </div>
        </div>
      </div>
    </aside>
  );
}
