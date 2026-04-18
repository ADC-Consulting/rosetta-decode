import type { JobStatus, JobSummary } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function getJob(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE}/jobs/${jobId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<JobStatus>;
}

export async function listJobs(): Promise<JobSummary[]> {
  const res = await fetch(`${BASE}/jobs`);
  if (!res.ok) throw new Error(await res.text());
  const data = (await res.json()) as { jobs: JobSummary[] };
  return data.jobs;
}

export async function downloadJob(jobId: string): Promise<void> {
  const res = await fetch(`${BASE}/jobs/${jobId}/download`);
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `rosetta-${jobId}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}
