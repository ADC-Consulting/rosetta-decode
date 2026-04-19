import { downloadJob, getJob } from "@/api/jobs";
import type { JobStatus, JobStatusValue } from "@/api/types";
import { Button } from "@/components/ui/button";
import { useQuery } from "@tanstack/react-query";

interface JobResultProps {
  jobId: string;
}

const POLLING_STATUSES: JobStatusValue[] = ["queued", "running", "proposed"];

const STATUS_LABEL: Record<JobStatusValue, string> = {
  queued: "Queued",
  running: "Running",
  proposed: "Under Review",
  accepted: "Accepted",
  failed: "Failed",
};

export default function JobResult({ jobId }: JobResultProps) {
  const { data, error, isLoading } = useQuery<JobStatus, Error>({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status !== undefined && POLLING_STATUSES.includes(status)
        ? 2000
        : false;
    },
  });

  if (isLoading || !data) {
    return (
      <div className="flex items-center gap-3 py-6 text-muted-foreground">
        <div
          aria-label="Loading"
          className={
            "size-5 rounded-full border-2 border-border border-t-foreground animate-spin"
          }
        />
        <span className="text-sm">Loading…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive bg-destructive/10 px-4 py-3 text-sm text-destructive"
      >
        <p className="font-medium mb-1">Could not load job status</p>
        <p className="text-xs opacity-80">
          Please refresh the page. If the problem persists, the job may have
          been removed.
        </p>
      </div>
    );
  }

  const { status } = data;

  if (POLLING_STATUSES.includes(status)) {
    return (
      <div className="py-6" aria-label="Job in progress">
        <style>{`@keyframes shimmer { from { background-position: 200% center; } to { background-position: -200% center; } }`}</style>
        <span className="inline-flex items-center rounded-full bg-black px-2.5 py-0.5 text-xs font-medium">
          <span
            style={{
              background:
                "linear-gradient(90deg, #fff 25%, #888 50%, #fff 75%)",
              backgroundSize: "200% 100%",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
              animation: "shimmer 3.5s linear infinite",
            }}
          >
            {STATUS_LABEL[status]}
          </span>
        </span>
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive bg-destructive/10 px-4 py-3 text-sm text-destructive"
      >
        <p className="font-medium mb-1">Migration failed</p>
        <p>
          We were unable to complete the migration. Try submitting again, or
          check that your SAS files are valid.
        </p>
      </div>
    );
  }

  // status === "done"
  return (
    <div className="space-y-6">
      <Button
        variant="outline"
        onClick={() => void downloadJob(jobId)}
        aria-label={`Download results for job ${jobId}`}
      >
        Download results
      </Button>
    </div>
  );
}
