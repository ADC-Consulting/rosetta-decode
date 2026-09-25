import type { JobSummary } from "@/api/types";
import { buttonVariants, Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { Activity, ArchiveRestore, Download, MoreVertical, Trash2 } from "lucide-react";

interface MigrationRowActionsProps {
  job: JobSummary;
  onTraceClick: () => void;
  onDeleteClick: () => void;
  onDownloadClick: () => void;
  onUnarchiveClick: () => void;
}

/**
 * Per-row action cluster: a primary action (pulsing "Watch live" for
 * running/queued jobs, static "Trace" for reviewable/completed/failed jobs,
 * "Download" for accepted jobs) plus a kebab menu offering "Delete
 * migration" and, for archived jobs, "Unarchive" (reversing the soft-hide —
 * see journal/DECISIONS.md 2026-09-24: "Archive = soft-hide ... Reversible").
 * The kebab is withheld for running/queued jobs, matching the Manifest
 * mockup (docs/design/MigrationsPage.dc.html row 2).
 */
export default function MigrationRowActions({
  job,
  onTraceClick,
  onDeleteClick,
  onDownloadClick,
  onUnarchiveClick,
}: MigrationRowActionsProps): React.ReactElement {
  const isLive = job.status === "queued" || job.status === "running";
  const isAccepted = job.status === "accepted";
  const shortId = job.job_id.slice(0, 8);

  return (
    <div className="flex items-center justify-end gap-0.5">
      {isLive && (
        <Button
          size="sm"
          variant="ghost"
          className="text-primary hover:text-primary"
          onClick={(e) => {
            e.stopPropagation();
            onTraceClick();
          }}
          aria-label={`Watch live trace for job ${shortId}`}
        >
          <Activity className="h-3.5 w-3.5 animate-pulse" aria-hidden="true" />
          Watch live
        </Button>
      )}

      {!isLive && isAccepted && (
        <Button
          size="sm"
          variant="outline"
          onClick={(e) => {
            e.stopPropagation();
            onDownloadClick();
          }}
          aria-label={`Download results for job ${shortId}`}
        >
          <Download className="h-3.5 w-3.5" aria-hidden="true" />
          Download
        </Button>
      )}

      {!isLive && !isAccepted && (
        <Button
          size="sm"
          variant="ghost"
          className="text-primary hover:text-primary"
          onClick={(e) => {
            e.stopPropagation();
            onTraceClick();
          }}
          aria-label={`Trace for job ${shortId}`}
        >
          <Activity className="h-3.5 w-3.5" aria-hidden="true" />
          Trace
        </Button>
      )}

      {!isLive && (
        <DropdownMenu>
          <DropdownMenuTrigger
            className={cn(buttonVariants({ variant: "ghost", size: "icon-sm" }))}
            aria-label={`Actions for job ${shortId}`}
            onClick={(e) => e.stopPropagation()}
          >
            <MoreVertical className="h-4 w-4" aria-hidden="true" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {job.is_archived && (
              <>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
                    onUnarchiveClick();
                  }}
                >
                  <ArchiveRestore className="h-3.5 w-3.5" aria-hidden="true" />
                  Unarchive
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            )}
            <DropdownMenuItem
              variant="destructive"
              onClick={(e) => {
                e.stopPropagation();
                onDeleteClick();
              }}
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              Delete migration
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}
