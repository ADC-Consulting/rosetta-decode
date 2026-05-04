import type { JobSummary } from "@/api/types";
import { cn } from "@/lib/utils";

interface MigrationCardProps {
  job: JobSummary;
  isSelected: boolean;
  onSelect: () => void;
}

export default function MigrationCard({ job, isSelected, onSelect }: MigrationCardProps): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onSelect}
      style={{ paddingLeft: 19 }}
      className={cn(
        "flex items-center w-full h-10 text-sm text-muted-foreground overflow-hidden",
        "hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer text-left",
        isSelected && "bg-muted text-foreground font-medium",
      )}
    >
      <span className="truncate">
        {job.name ?? `Job ${job.job_id.slice(0, 8)}`}
      </span>
    </button>
  );
}
