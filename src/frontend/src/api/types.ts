export type JobStatusValue = "queued" | "running" | "proposed" | "accepted" | "failed" | "done";

export interface JobStatus {
  job_id: string;
  status: JobStatusValue;
  python_code: string | null;
  report: Record<string, unknown> | null;
  error: string | null;
  name: string | null;
  generated_files: Record<string, string> | null;
  user_overrides: Record<string, unknown> | null;
  accepted_at: string | null;
  parent_job_id: string | null;
  trigger: string;
  skip_llm: boolean;
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

export interface BlockOverride {
  block_id: string;
  strategy?: string;
  risk?: string;
  note?: string;
}

export interface PatchPlanRequest {
  block_overrides: BlockOverride[];
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
  column_flows?: ColumnFlow[];
  macro_usages?: MacroUsage[];
  cross_file_edges?: Record<string, string>[];
  dataset_summaries?: Record<string, string>;
}

export interface BlockPlan {
  block_id: string;
  source_file: string;
  start_line: number;
  block_type: string;
  strategy: "translate" | "stub" | "skip";
  risk: "low" | "medium" | "high";
  rationale: string;
  estimated_effort: "low" | "medium" | "high";
}

export interface JobPlanResponse {
  job_id: string;
  summary: string;
  overall_risk: "low" | "medium" | "high";
  block_plans: BlockPlan[];
  recommended_review_blocks: string[];
  cross_file_dependencies: string[];
}

export interface ColumnFlow {
  column: string;
  source_dataset: string;
  target_dataset: string;
  via_block_id: string;
  transformation: string | null;
}

export interface MacroUsage {
  macro_name: string;
  macro_value: string;
  used_in_block_id: string;
}

export interface JobDocResponse {
  job_id: string;
  doc: string | null;
}

export interface JobHistoryEntry {
  job_id: string;
  status: JobStatusValue;
  trigger: "agent" | "human-refine" | "human-rereconcile";
  name: string | null;
  created_at: string;
  updated_at: string;
  is_current: boolean;
}

export interface JobHistoryResponse {
  entries: JobHistoryEntry[];
}
