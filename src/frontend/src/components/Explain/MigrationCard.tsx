import type { JobSummary } from "@/api/types";
import { StatusBadge } from "@/components/JobDetail/StatusBadge";
import { cn } from "@/lib/utils";

interface MigrationCardProps {
  job: JobSummary;
  isSelected: boolean;
  onSelect: () => void;
}

export default function MigrationCard({ job, isSelected, onSelect }: MigrationCardProps): React.ReactElement {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect()}
      className={cn(
        "rounded-md border p-3 cursor-pointer text-left transition-colors",
        isSelected
          ? "border-primary bg-primary/5"
          : "border-border bg-background hover:bg-muted/50",
      )}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="text-sm font-medium truncate">
          {job.name ?? `Job ${job.job_id.slice(0, 8)}`}
        </span>
        <StatusBadge status={job.status} />
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>{new Date(job.created_at).toLocaleDateString()}</span>
        <span>·</span>
        <span>
          {job.file_count} file{job.file_count !== 1 ? "s" : ""}
        </span>
      </div>
    </div>
  );
}
