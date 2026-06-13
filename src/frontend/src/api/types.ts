export type JobStatusValue = "queued" | "running" | "proposed" | "accepted" | "under_review" | "failed" | "done";

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
  status: "migrated" | "manual_review" | "unrecognized";
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

export type TranslationStrategy = "translated" | "translated_with_review" | "manual";

export interface BlockPlan {
  block_id: string;
  source_file: string;
  start_line: number;
  end_line: number;
  block_type: string;
  strategy: TranslationStrategy;
  risk: "low" | "medium" | "high";
  rationale: string;
  estimated_effort: "low" | "medium" | "high";
  confidence_score: number;
  confidence_band: string;
  input_datasets: string[];
  output_datasets: string[];
}

export interface JobPlanResponse {
  job_id: string;
  summary: string;
  overall_risk: "low" | "medium" | "high";
  block_plans: BlockPlan[];
  recommended_review_blocks: string[];
  cross_file_dependencies: string[];
  risk_explanation: string;
  missing_dependencies?: Array<{name: string; type: "macro" | "include"; reference_count: number}>;
  sensitive_data_findings?: Array<{
    column: string;
    matched_signal: string;
    source_type: "file" | "block";
    source: string;
  }>;
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
  status: "OK" | "UNRECOGNIZED" | "ERROR_PRONE" | null;
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
  status: "OK" | "UNRECOGNIZED" | "ERROR_PRONE";
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
  non_technical_doc?: string | null;
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

// ── F4: Block revisions ───────────────────────────────────────────────────────

export interface BlockRevision {
  id: string;
  job_id: string;
  block_id: string;
  revision_number: number;
  python_code: string;
  strategy: TranslationStrategy;
  confidence: string;
  uncertainty_notes: string[];
  reconciliation_status: "pass" | "fail" | null;
  trigger: string;
  notes: string | null;
  hint: string | null;
  diff_vs_previous: string | null;
  created_at: string;
}

export interface BlockRevisionHistory {
  block_id: string;
  revisions: BlockRevision[];
}

export interface BlockRefineRequest {
  notes?: string | null;
  hint?: string | null;
}

export interface BlockRefineResponse {
  block_id: string;
  revision_number: number;
  confidence: string;
  reconciliation_status: "pass" | "fail" | null;  python_code: string | null;}

// ── F4: Changelog ─────────────────────────────────────────────────────────────

export interface ChangelogEntry {
  id: string;
  block_id: string;
  revision_number: number;
  trigger: string;
  strategy: TranslationStrategy;
  confidence: string;
  reconciliation_status: "pass" | "fail" | null;
  notes: string | null;
  hint: string | null;
  diff_vs_previous: string | null;
  created_at: string;
}

export interface JobChangelogResponse {
  job_id: string;
  entries: ChangelogEntry[];
}

// ── F4: Trust report ─────────────────────────────────────────────────────────

export interface TrustReportBlock {
  block_id: string;
  source_file: string;
  start_line: number;
  block_type: string;
  strategy: TranslationStrategy;
  self_confidence: string;
  verified_confidence: string | null;
  reconciliation_status: "pass" | "fail" | null;
  needs_attention: boolean;
  blast_radius: number | null;
  effective_confidence_band?: string;
  criticality: "critical" | "high" | "medium" | "low";
  human_review_required: boolean;
}

export interface TrustReportFile {
  source_file: string;
  total_blocks: number;
  auto_verified: number;
  needs_review: number;
  manual_todo: number;
  failed_reconciliation: number;
}

export interface TrustReportResponse {
  job_id: string;
  lineage_available: boolean;
  overall_confidence: "high" | "medium" | "low" | "very_low" | "unknown";
  overall_confidence_score: number;  // 0.0-1.0 average of block confidence_scores
  total_blocks: number;
  auto_verified: number;
  needs_review: number;
  manual_todo: number;
  failed_reconciliation: number;
  files: TrustReportFile[];
  blocks: TrustReportBlock[];
  review_queue: TrustReportBlock[];
}

// ── F20 — Live Trace types ────────────────────────────────────────────────────

export interface TraceEventBase {
  event_type: string;
  ts: string; // ISO 8601
}

export interface BlockStartEvent extends TraceEventBase {
  event_type: "block_start";
  block_id: string;
  agent: string;
  attempt: number;
}

export interface BlockDoneEvent extends TraceEventBase {
  event_type: "block_done";
  block_id: string;
  attempt: number;
  status: "pass" | "fail" | "error";
  elapsed_ms: number;
}

export interface ReconCheck {
  name: string;
  status: string;
  detail: string;
}

export interface ReconResultEvent extends TraceEventBase {
  event_type: "recon_result";
  block_id: string;
  checks: ReconCheck[];
  all_passed: boolean;
}

export interface JobDoneEvent extends TraceEventBase {
  event_type: "job_done";
  job_id: string;
  final_status: string;
}

export interface TraceErrorEvent extends TraceEventBase {
  event_type: "error";
  message: string;
}

export type PhaseName =
  | "parse_analysis"
  | "migration_planning"
  | "translation"
  | "assembly_recon"
  | "enrichment";

export type PhaseStatus = "pending" | "running" | "done" | "error";

export interface PhaseStartEvent extends TraceEventBase {
  event_type: "phase_start";
  phase: PhaseName;
}

export interface PhaseDoneEvent extends TraceEventBase {
  event_type: "phase_done";
  phase: PhaseName;
  status: "done" | "error";
  elapsed_ms: number;
}

export interface ParseResultEvent extends TraceEventBase {
  event_type: "parse_result";
  block_count: number;
  file_count: number;
  macro_var_count: number;
  block_type_counts?: Record<string, number>;
}

export interface PlanResultEvent extends TraceEventBase {
  event_type: "plan_result";
  overall_risk: "low" | "medium" | "high";
  summary: string;
  block_count: number;
  review_block_count: number;
  cross_file_dependencies?: string[];
  block_plans?: Array<{
    block_id: string;
    block_type: string;
    strategy: string;
    risk: string;
    rationale: string;
  }>;
}

export interface EnrichmentItemDoneEvent extends TraceEventBase {
  event_type: "enrichment_item_done";
  item: "lineage" | "documentation" | "plain_english";
  status: "done" | "skipped" | "error";
}

export type TraceEvent =
  | BlockStartEvent
  | BlockDoneEvent
  | ReconResultEvent
  | JobDoneEvent
  | TraceErrorEvent
  | PhaseStartEvent
  | PhaseDoneEvent
  | ParseResultEvent
  | PlanResultEvent
  | EnrichmentItemDoneEvent;

// ── F34: Scoping summary ──────────────────────────────────────────────────────

export interface PhaseTokens {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  requests: number;
}

export interface TokenUsageStats {
  phases: Record<string, PhaseTokens>;
  total: PhaseTokens;
  translation_by_block: Record<string, PhaseTokens>;
}

export interface CostEstimate {
  total_usd: number;
  per_phase_usd: Record<string, number>;
  prices: { input_usd_per_mtok: number; output_usd_per_mtok: number };
  price_source: string;
}

export interface BomSummary {
  total_blocks: number;
  data_steps: number;
  procs: number;
  macros: number;
  untranslatable: number;
  proc_counts: Record<string, number>;
  risk_buckets: Record<string, number>;
  criticality_buckets: Record<string, number>;
  strategy_counts: Record<string, number>;
  human_review_required: number;
}

export interface ScopingSummaryResponse {
  job_id: string;
  job_name: string;
  llm_model: string;
  token_usage: TokenUsageStats | null;
  cost: CostEstimate | null;
  bom: BomSummary;
  markdown: string;
}
