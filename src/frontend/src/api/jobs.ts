import type { JobDocResponse, JobLineageResponse, JobSourcesResponse, JobStatus, JobSummary } from "./types";
import { extractApiError } from "./errors";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function getJob(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE}/jobs/${jobId}`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobStatus>;
}

export async function listJobs(): Promise<JobSummary[]> {
  const res = await fetch(`${BASE}/jobs`);
  if (!res.ok) throw new Error(await extractApiError(res));
  const data = (await res.json()) as { jobs: JobSummary[] };
  return data.jobs;
}

export async function downloadJob(jobId: string): Promise<void> {
  const res = await fetch(`${BASE}/jobs/${jobId}/download`);
  if (!res.ok) throw new Error(await extractApiError(res));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `rosetta-${jobId}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function getJobSources(jobId: string): Promise<JobSourcesResponse> {
  const res = await fetch(`${BASE}/jobs/${jobId}/sources`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobSourcesResponse>;
}

export async function getJobLineage(jobId: string): Promise<JobLineageResponse> {
  const res = await fetch(`${BASE}/jobs/${jobId}/lineage`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobLineageResponse>;
}

export async function getJobDoc(jobId: string): Promise<JobDocResponse> {
  const res = await fetch(`${BASE}/jobs/${jobId}/doc`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobDocResponse>;
}

export async function updateJobPythonCode(jobId: string, pythonCode: string): Promise<void> {
  const res = await fetch(`${BASE}/jobs/${jobId}/python_code`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ python_code: pythonCode }),
  });
  if (!res.ok) throw new Error(await extractApiError(res));
}

export async function refineJob(jobId: string, hint?: string): Promise<{ job_id: string }> {
  const res = await fetch(`${BASE}/jobs/${jobId}/refine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hint: hint ?? null }),
  });
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<{ job_id: string }>;
}
