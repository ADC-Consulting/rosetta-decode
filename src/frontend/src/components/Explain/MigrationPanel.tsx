import type { JobSummary } from "@/api/types";
import MigrationCard from "./MigrationCard";

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
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center justify-between shrink-0">
        <span className="text-sm font-semibold text-foreground">Migrations</span>
        {onClose && (
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close migrations panel"
          >
            ✕
          </button>
        )}
      </div>

      <input
        type="search"
        value={searchQuery}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search migrations…"
        className="rounded-md border border-border bg-background px-3 py-1.5 text-sm w-full outline-none focus:ring-1 focus:ring-ring shrink-0"
        aria-label="Search migrations"
      />

      <div className="flex-1 overflow-y-auto space-y-2">
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
          <p className="text-xs text-muted-foreground text-center py-4">
            No migrations found.
          </p>
        )}
      </div>

      <div className="shrink-0 pt-2 border-t border-border">
        <button
          onClick={onSwitchToUpload}
          className="text-xs text-primary hover:underline underline-offset-2"
        >
          Use uploaded files instead →
        </button>
      </div>
    </div>
  );
}
