export type JobStatusValue = "queued" | "running" | "done" | "failed";

export interface JobStatus {
  job_id: string;
  status: JobStatusValue;
  python_code: string | null;
  report: Record<string, unknown> | null;
  error: string | null;
  name: string | null;
}

export interface JobSummary {
  job_id: string;
  status: JobStatusValue;
  created_at: string;
  updated_at: string;
  error: string | null;
  name: string | null;
  file_count: number;
}

export interface FileRejection {
  filename: string;
  reason: string;
}

export interface MigrateResponse {
  job_id: string;
  accepted: string[];
  rejected: FileRejection[];
  name?: string;
}

export interface JobSourcesResponse {
  job_id: string;
  sources: Record<string, string>;
}

export interface LineageNode {
  id: string;
  label: string;
  source_file: string;
  block_type: string;
  status: "migrated" | "manual_review" | "untranslatable";
}

export interface LineageEdge {
  source: string;
  target: string;
  dataset: string;
  inferred: boolean;
}

export interface JobLineageResponse {
  job_id: string;
  nodes: LineageNode[];
  edges: LineageEdge[];
}

export interface JobDocResponse {
  job_id: string;
  doc: string | null;
}
