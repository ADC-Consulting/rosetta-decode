import { extractApiError } from "./errors";
import type {
    BlockRefineRequest,
    BlockRefineResponse,
    BlockRevisionHistory,
    ExecuteResponse,
    JobAttachmentsResponse,
    JobChangelogResponse,
    JobDocResponse,
    JobHistoryResponse,
    JobLineageResponse,
    JobPlanResponse,
    JobSourcesResponse,
    JobStatus,
    JobSummary,
    JobVersionDetail,
    JobVersionSummary,
    PatchPlanRequest,
    SaveVersionRequest,
    SaveVersionResponse,
    TrustReportResponse,
} from "./types";

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

export async function getJobPlan(jobId: string): Promise<JobPlanResponse | null> {
  const res = await fetch(`${BASE}/jobs/${jobId}/plan`);
  if (res.status === 202) return null;
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobPlanResponse>;
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

export async function getJobHistory(jobId: string): Promise<JobHistoryResponse> {
  const res = await fetch(`${BASE}/jobs/${jobId}/history`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobHistoryResponse>;
}

export async function acceptJob(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE}/jobs/${jobId}/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobStatus>;
}

export async function patchJobPlan(jobId: string, req: PatchPlanRequest): Promise<JobStatus> {
  const res = await fetch(`${BASE}/jobs/${jobId}/plan`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobStatus>;
}

export async function getJobVersions(jobId: string, tab: string): Promise<JobVersionSummary[]> {
  const res = await fetch(`${BASE}/jobs/${jobId}/versions?tab=${encodeURIComponent(tab)}`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobVersionSummary[]>;
}

export async function getJobVersion(jobId: string, versionId: string): Promise<JobVersionDetail> {
  const res = await fetch(`${BASE}/jobs/${jobId}/versions/${versionId}`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobVersionDetail>;
}

export async function saveVersion(
  jobId: string,
  tab: string,
  body: SaveVersionRequest,
): Promise<SaveVersionResponse> {
  const res = await fetch(
    `${BASE}/jobs/${jobId}/versions?tab=${encodeURIComponent(tab)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<SaveVersionResponse>;
}

// ── F4: Block-level refine ────────────────────────────────────────────────────

export async function refineBlock(
  jobId: string,
  blockId: string,
  request: BlockRefineRequest,
): Promise<BlockRefineResponse> {
  const encodedBlockId = blockId.replace(/:/g, '%3A');
  const res = await fetch(`${BASE}/jobs/${jobId}/blocks/${encodedBlockId}/refine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<BlockRefineResponse>;
}

// ── F4: Block revision history ────────────────────────────────────────────────

export async function getBlockRevisions(
  jobId: string,
  blockId: string,
): Promise<BlockRevisionHistory> {
  const encodedBlockId = blockId.replace(/:/g, '%3A');
  const res = await fetch(`${BASE}/jobs/${jobId}/blocks/${encodedBlockId}/revisions`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<BlockRevisionHistory>;
}

// ── F4: Restore a prior block revision ───────────────────────────────────────

export async function restoreBlockRevision(
  jobId: string,
  blockId: string,
  revisionId: string,
): Promise<BlockRefineResponse> {
  const encodedBlockId = blockId.replace(/:/g, '%3A');
  const res = await fetch(
    `${BASE}/jobs/${jobId}/blocks/${encodedBlockId}/revisions/${revisionId}/restore`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<BlockRefineResponse>;
}

// ── Human python edit ────────────────────────────────────────────────────────

export async function saveBlockPython(
  jobId: string,
  blockId: string,
  pythonCode: string,
  notes?: string,
): Promise<{ revision_number: number; block_id: string }> {
  const encodedBlockId = blockId.replace(/:/g, '%3A');
  const res = await fetch(
    `${BASE}/jobs/${jobId}/blocks/${encodedBlockId}/python`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ python_code: pythonCode, notes }),
    },
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ revision_number: number; block_id: string }>;
}

// ── F4: Job changelog ─────────────────────────────────────────────────────────

export async function getJobChangelog(jobId: string): Promise<JobChangelogResponse> {
  const res = await fetch(`${BASE}/jobs/${jobId}/changelog`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobChangelogResponse>;
}

// ── F4: Trust report ──────────────────────────────────────────────────────────

export async function getJobTrustReport(jobId: string): Promise<TrustReportResponse> {
  const res = await fetch(`${BASE}/jobs/${jobId}/trust-report`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<TrustReportResponse>;
}

// ── Attachments ───────────────────────────────────────────────────────────────

export async function getJobAttachments(jobId: string): Promise<JobAttachmentsResponse> {
  const res = await fetch(`${BASE}/jobs/${jobId}/attachments`);
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<JobAttachmentsResponse>;
}

export function getAttachmentUrl(jobId: string, pathKey: string): string {
  return `${BASE}/jobs/${jobId}/attachments/${encodeURIComponent(pathKey)}`;
}

// ── Execute ───────────────────────────────────────────────────────────────────

export async function executeJob(
  jobId: string,
  blockId?: string,
): Promise<ExecuteResponse> {
  const res = await fetch(`${BASE}/jobs/${jobId}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ block_id: blockId ?? null }),
  });
  if (!res.ok) throw new Error(await extractApiError(res));
  return res.json() as Promise<ExecuteResponse>;
}
