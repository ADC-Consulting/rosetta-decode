import { downloadJob, listJobs } from "@/api/jobs";
import type { JobStatusValue, JobSummary } from "@/api/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { STATUS_LABEL, StatusBadge } from "@/pages/JobDetailPage";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

const POLLING_STATUSES: JobStatusValue[] = ["queued", "running"];

export default function JobsPage(): React.ReactElement {
  const navigate = useNavigate();

  const { data: jobs, isLoading } = useQuery<JobSummary[], Error>({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: (query) => {
      const list = query.state.data;
      if (!list) return false;
      return list.some((j) => POLLING_STATUSES.includes(j.status))
        ? 3000
        : false;
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Migrations</h1>
        <Button variant="outline" onClick={() => navigate("/upload")}>
          New migration
        </Button>
      </div>

      {isLoading && (
        <div className="flex items-center gap-3 text-muted-foreground py-4">
          <div
            aria-label="Loading jobs"
            className="size-5 rounded-full border-2 border-border border-t-foreground animate-spin"
          />
          <span className="text-sm">Loading…</span>
        </div>
      )}

      {!isLoading && jobs !== undefined && jobs.length === 0 && (
        <p className="text-sm text-muted-foreground py-4">
          No migrations yet. Start one from the Upload page.
        </p>
      )}

      {!isLoading && jobs !== undefined && jobs.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm" aria-label="Migration jobs">
            <thead>
              <tr className="border-b border-border bg-muted text-muted-foreground text-left">
                <th scope="col" className="px-4 py-2.5 font-medium w-[40%]">
                  Name
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Status
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Files
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Created
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium sr-only">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const isClickable = job.status === "done";
                return (
                  <tr
                    key={job.job_id}
                    onClick={() => {
                      if (isClickable) navigate(`/jobs/${job.job_id}`);
                    }}
                    role={isClickable ? "button" : undefined}
                    tabIndex={isClickable ? 0 : undefined}
                    aria-label={`${job.name ?? job.job_id.slice(0, 8)}, status ${STATUS_LABEL[job.status]}`}
                    aria-disabled={!isClickable}
                    onKeyDown={(e) => {
                      if (!isClickable) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        navigate(`/jobs/${job.job_id}`);
                      }
                    }}
                    className={cn(
                      "border-b border-border last:border-0 transition-colors",
                      isClickable
                        ? "cursor-pointer hover:bg-muted/50"
                        : "cursor-default opacity-70",
                    )}
                  >
                    <td className="px-4 py-3 text-foreground font-medium">
                      {job.name ?? (
                        <span className="font-mono text-muted-foreground">
                          {job.job_id.slice(0, 8)}…
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {job.file_count != null ? job.file_count : "—"}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {new Date(job.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {job.status === "done" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={(e) => {
                            e.stopPropagation();
                            void downloadJob(job.job_id);
                          }}
                          aria-label={`Download results for job ${job.job_id.slice(0, 8)}`}
                        >
                          Download
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
