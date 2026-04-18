export type JobStatusValue = "queued" | "running" | "done" | "failed";

export interface JobStatus {
  job_id: string;
  status: JobStatusValue;
  python_code: string | null;
  report: Record<string, unknown> | null;
  error: string | null;
}

export interface JobSummary {
  job_id: string;
  status: JobStatusValue;
  created_at: string;
  updated_at: string;
  error: string | null;
}
