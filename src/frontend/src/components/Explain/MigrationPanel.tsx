import type { JobSummary } from "@/api/types";
import MigrationCard from "./MigrationCard";

const ICON_LEFT = 19;

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
  const filteredJobs = jobs?.filter(
    (j) =>
      searchQuery === "" ||
      j.name?.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header — matches AppSidebar logo row */}
      <div
        className="flex items-center justify-between h-14 border-b border-border shrink-0 overflow-hidden"
        style={{ paddingLeft: ICON_LEFT, paddingRight: ICON_LEFT }}
      >
        <span className="text-sm font-semibold text-foreground">Migrations</span>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close migrations panel"
          >
            ✕
          </button>
        )}
      </div>

      {/* Search row — same h-10 as nav rows */}
      <div
        className="flex items-center h-10 border-b border-border shrink-0"
        style={{ paddingLeft: ICON_LEFT, paddingRight: ICON_LEFT }}
      >
        <input
          type="search"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search…"
          className="w-full bg-transparent text-sm outline-none text-foreground placeholder:text-muted-foreground"
          aria-label="Search migrations"
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
            <MigrationCard
              key={job.job_id}
              job={job}
              isSelected={job.job_id === selectedJobId}
              onSelect={() => onSelectJob(job)}
            />
          ))}
        {!isLoading && (filteredJobs?.length ?? 0) === 0 && (
          <p
            className="text-xs text-muted-foreground py-4"
            style={{ paddingLeft: ICON_LEFT }}
          >
            No migrations found.
          </p>
        )}
      </div>

      {/* Footer — nav row style */}
      <div className="shrink-0 border-t border-border">
        <button
          type="button"
          onClick={onSwitchToUpload}
          className="flex items-center w-full h-10 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
          style={{ paddingLeft: ICON_LEFT }}
        >
          Upload files instead
        </button>
      </div>
    </div>
  );
}
