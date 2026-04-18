import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { JobStatusValue, JobSummary } from "@/api/types";
import { listJobs, downloadJob } from "@/api/jobs";
import { Button } from "@/components/ui/button";
import JobResult from "@/components/JobResult";
import { cn } from "@/lib/utils";

const POLLING_STATUSES: JobStatusValue[] = ["queued", "running"];

const STATUS_BADGE: Record<JobStatusValue, string> = {
  queued:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  running:
    "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  done: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
};

export default function JobsPage() {
  const navigate = useNavigate();
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  const { data: jobs, isLoading } = useQuery<JobSummary[], Error>({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: (query) => {
      const list = query.state.data;
      if (!list) return false;
      return list.some((j) => POLLING_STATUSES.includes(j.status)) ? 3000 : false;
    },
  });

  function handleRowClick(jobId: string) {
    setSelectedJobId((prev) => (prev === jobId ? null : jobId));
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Migrations</h1>
        <Button variant="outline" onClick={() => navigate("/")}>
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
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Job ID
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Status
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
              {jobs.map((job) => (
                <tr
                  key={job.job_id}
                  onClick={() => handleRowClick(job.job_id)}
                  role="button"
                  tabIndex={0}
                  aria-pressed={selectedJobId === job.job_id}
                  aria-label={`Job ${job.job_id.slice(0, 8)}, status ${job.status}`}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleRowClick(job.job_id);
                    }
                  }}
                  className={cn(
                    "border-b border-border last:border-0 cursor-pointer",
                    "hover:bg-muted/50 transition-colors",
                    selectedJobId === job.job_id && "bg-muted/70",
                  )}
                >
                  <td className="px-4 py-3 font-mono text-foreground">
                    {job.job_id.slice(0, 8)}…
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                        STATUS_BADGE[job.status],
                      )}
                    >
                      {job.status}
                    </span>
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
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedJobId !== null && (
        <section aria-label="Job details">
          <h2 className="text-base font-medium text-foreground mb-3">
            Job details —{" "}
            <span className="font-mono text-muted-foreground">
              {selectedJobId.slice(0, 8)}…
            </span>
          </h2>
          <JobResult jobId={selectedJobId} />
        </section>
      )}
    </div>
  );
}
