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
  file_nodes?: FileNode[];
  file_edges?: FileEdge[];
  pipeline_steps?: PipelineStep[];
  block_status?: BlockStatus[];
  log_links?: LogLink[];
}

export type TranslationStrategy =
  | "translate"
  | "translate_with_review"
  | "manual_ingestion"
  | "manual"
  | "skip";

export interface BlockPlan {
  block_id: string;
  source_file: string;
  start_line: number;
  block_type: string;
  strategy: TranslationStrategy;
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

export interface FileNode {
  filename: string;
  file_type: "PROGRAM" | "MACRO" | "AUTOEXEC" | "LOG" | "OTHER";
  blocks: string[];
  status: "OK" | "UNTRANSLATABLE" | "ERROR_PRONE" | null;
  status_reason: string | null;
}

export interface FileEdge {
  source_file: string;
  target_file: string;
  reason: "INCLUDE" | "MACRO_CALL" | "READS_DATASET" | "WRITES_DATASET";
  via_block_id: string;
}

export interface PipelineStep {
  step_id: string;
  name: string;
  description: string;
  files: string[];
  blocks: string[];
  inputs: string[];
  outputs: string[];
}

export interface BlockStatus {
  block_id: string;
  status: "OK" | "UNTRANSLATABLE" | "ERROR_PRONE";
  reason: string | null;
}

export interface LogLink {
  log_file: string;
  related_files: string[];
  related_blocks: string[];
  severity: "INFO" | "WARNING" | "ERROR";
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

export interface JobVersionSummary {
  id: string;
  job_id: string;
  tab: "plan" | "editor" | "report";
  trigger: string;
  created_at: string;
}

export interface JobVersionDetail extends JobVersionSummary {
  content: Record<string, unknown>;
}

export interface SaveVersionRequest {
  content: Record<string, unknown>;
  trigger?: string;
}

export interface SaveVersionResponse {
  id: string;
  job_id: string;
  tab: string;
  created_at: string;
}
