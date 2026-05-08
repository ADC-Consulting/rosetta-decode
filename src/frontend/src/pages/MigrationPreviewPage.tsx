import { analyseMigration, submitMigration } from "@/api/migrate";
import type {
  AnalyseResponse,
  AssessedBlock,
  ConfigurationValue,
  OutputCoverage,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronDown, ChevronRight, Pencil } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

// ── Types ─────────────────────────────────────────────────────────────────────

interface LocationState {
  sasFiles?: File[];
  zipFile?: File;
  refDataset?: File;
  refTargetPath?: string | null;
  name?: string;
}

type ImportanceLevel = "low" | "medium" | "high";

// ── Helpers ───────────────────────────────────────────────────────────────────

function loadStoredImportance(inputHash: string): Record<string, ImportanceLevel> {
  try {
    const raw = localStorage.getItem(`rosetta_importance_${inputHash}`);
    if (!raw) return {};
    return JSON.parse(raw) as Record<string, ImportanceLevel>;
  } catch {
    return {};
  }
}

function saveStoredImportance(
  inputHash: string,
  overrides: Record<string, ImportanceLevel>,
): void {
  try {
    localStorage.setItem(`rosetta_importance_${inputHash}`, JSON.stringify(overrides));
  } catch {
    // storage quota exceeded — silently ignore
  }
}

function tierFor(
  block: AssessedBlock,
  overrides: Record<string, ImportanceLevel>,
): "manual" | "review" | "best-effort" | "auto" {
  const importance = overrides[block.block_id] ?? block.structural_importance;
  if (!block.is_translatable) return "manual";
  if (block.is_unknown_proc) return "best-effort";
  if (importance === "high") return "review";
  return "auto";
}

function fmtMinutes(low: number, high: number): string {
  if (high < 60) return `${low}–${high} min`;
  const hLow = Math.floor(low / 60);
  const hHigh = Math.ceil(high / 60);
  return `${hLow}–${hHigh} hr`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface ImportanceSelectProps {
  blockId: string;
  value: ImportanceLevel;
  onChange: (id: string, val: ImportanceLevel) => void;
}

function ImportanceSelect({ blockId, value, onChange }: ImportanceSelectProps) {
  return (
    <select
      aria-label="Structural importance"
      value={value}
      onChange={(e) => onChange(blockId, e.target.value as ImportanceLevel)}
      className={
        "rounded border border-input bg-background px-2 py-0.5 text-xs focus:outline-none focus:ring-2 focus:ring-ring " +
        (value === "high"
          ? "text-amber-700 dark:text-amber-400"
          : value === "medium"
            ? "text-blue-700 dark:text-blue-400"
            : "text-muted-foreground")
      }
    >
      <option value="low">Low</option>
      <option value="medium">Medium</option>
      <option value="high">High</option>
    </select>
  );
}

interface BlockCardProps {
  block: AssessedBlock;
  overrides: Record<string, ImportanceLevel>;
  onImportanceChange: (id: string, val: ImportanceLevel) => void;
  showBlastRadius?: boolean;
  showCode?: boolean;
}

function BlockCard({
  block,
  overrides,
  onImportanceChange,
  showBlastRadius = false,
  showCode = false,
}: BlockCardProps) {
  const [codeOpen, setCodeOpen] = useState(false);
  const importance = overrides[block.block_id] ?? block.structural_importance;

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground truncate">
            {block.functional_description}
          </p>
          <p className="text-xs text-muted-foreground">
            {block.source_file}:{block.start_line}–{block.end_line}
          </p>
        </div>
        <ImportanceSelect
          blockId={block.block_id}
          value={importance}
          onChange={onImportanceChange}
        />
      </div>

      {block.importance_reason && (
        <p className="text-xs text-muted-foreground">{block.importance_reason}</p>
      )}

      {showBlastRadius && block.blast_radius.length > 0 && (
        <div className="rounded bg-muted/50 p-2 text-xs">
          <p className="font-medium text-foreground mb-1">Downstream impact:</p>
          <ul className="space-y-0.5 pl-3 list-disc list-inside">
            {block.blast_radius.map((ds) => (
              <li key={ds} className="text-muted-foreground font-mono">
                {ds}
              </li>
            ))}
          </ul>
        </div>
      )}

      {showCode && (
        <div>
          <button
            type="button"
            onClick={() => setCodeOpen((o) => !o)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            aria-expanded={codeOpen}
          >
            {codeOpen ? (
              <ChevronDown className="h-3 w-3" aria-hidden />
            ) : (
              <ChevronRight className="h-3 w-3" aria-hidden />
            )}
            View code
          </button>
          {codeOpen && (
            <pre className="mt-1 overflow-x-auto rounded bg-muted p-2 text-xs font-mono whitespace-pre-wrap">
              {block.raw_sas_snippet}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

interface TierSectionProps {
  label: string;
  count: number;
  tier: "manual" | "review" | "best-effort" | "auto";
  blocks: AssessedBlock[];
  overrides: Record<string, ImportanceLevel>;
  onImportanceChange: (id: string, val: ImportanceLevel) => void;
}

function TierSection({
  label,
  count,
  tier,
  blocks,
  overrides,
  onImportanceChange,
}: TierSectionProps) {
  const [expanded, setExpanded] = useState(tier !== "auto");

  if (count === 0) return null;

  const bgClass =
    tier === "manual"
      ? "border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/30"
      : tier === "review"
        ? "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30"
        : tier === "best-effort"
          ? "border-blue-300 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30"
          : "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30";

  return (
    <div className={`rounded-lg border p-4 space-y-3 ${bgClass}`}>
      <button
        type="button"
        onClick={() => setExpanded((o) => !o)}
        className="flex w-full items-center justify-between text-left"
        aria-expanded={expanded}
      >
        <span className="text-sm font-semibold text-foreground">
          {label}{" "}
          <span className="font-normal text-muted-foreground">({count})</span>
        </span>
        {tier === "auto" ? (
          <span className="text-xs text-muted-foreground">
            {expanded ? "Hide" : `Show ${count} step${count !== 1 ? "s" : ""}`}
          </span>
        ) : expanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" aria-hidden />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden />
        )}
      </button>

      {expanded && (
        <div className="space-y-2">
          {blocks.map((block) => (
            <BlockCard
              key={block.block_id}
              block={block}
              overrides={overrides}
              onImportanceChange={onImportanceChange}
              showBlastRadius={tier === "manual"}
              showCode={tier === "manual"}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface OutputCoverageRowProps {
  item: OutputCoverage;
}

function OutputCoverageRow({ item }: OutputCoverageRowProps) {
  const [colsOpen, setColsOpen] = useState(false);
  return (
    <div className="rounded border border-border bg-card p-3 space-y-1">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium font-mono text-foreground">
          {item.dataset_name}
        </span>
        <span
          className={
            item.has_reference
              ? "text-xs text-emerald-600 dark:text-emerald-400 font-medium"
              : "text-xs text-muted-foreground"
          }
        >
          {item.has_reference ? `Reference: ${item.reference_filename ?? ""}` : "No reference file"}
        </span>
      </div>
      {item.has_reference && (
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          {item.row_count != null && <span>{item.row_count.toLocaleString()} rows</span>}
          {item.column_names.length > 0 && (
            <button
              type="button"
              onClick={() => setColsOpen((o) => !o)}
              className="flex items-center gap-1 hover:text-foreground transition-colors"
              aria-expanded={colsOpen}
            >
              {colsOpen ? (
                <ChevronDown className="h-3 w-3" aria-hidden />
              ) : (
                <ChevronRight className="h-3 w-3" aria-hidden />
              )}
              {item.column_names.length} column{item.column_names.length !== 1 ? "s" : ""}
            </button>
          )}
        </div>
      )}
      {colsOpen && (
        <div className="flex flex-wrap gap-1 pt-1">
          {item.column_names.map((col) => (
            <span
              key={col}
              className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono text-muted-foreground"
            >
              {col}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

interface ConfigValueRowProps {
  item: ConfigurationValue;
}

function ConfigValueRow({ item }: ConfigValueRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 rounded border border-border bg-card px-3 py-2 text-sm">
      <span className="font-mono text-foreground">{item.name}</span>
      <span className="flex items-center gap-2 min-w-0">
        <span className="truncate font-mono text-muted-foreground">{item.value}</span>
        {item.looks_dynamic && (
          <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">
            Dynamic
          </span>
        )}
      </span>
    </div>
  );
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-72" />
      <Skeleton className="h-4 w-48" />
      <div className="grid grid-cols-3 gap-4">
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
      <Skeleton className="h-32" />
      <Skeleton className="h-48" />
      <Skeleton className="h-32" />
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MigrationPreviewPage(): React.ReactElement {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as LocationState | null;

  const [assessment, setAssessment] = useState<AnalyseResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [importanceOverrides, setImportanceOverrides] = useState<Record<string, ImportanceLevel>>({});
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionText, setDescriptionText] = useState<string>("");
  const [acknowledgments, setAcknowledgments] = useState<Record<string, boolean>>({});
  const [sensitiveConfirmed, setSensitiveConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Redirect guard
  useEffect(() => {
    if (!state?.sasFiles?.length && !state?.zipFile) {
      navigate("/jobs", { replace: true });
    }
  }, [state, navigate]);

  // Fetch assessment on mount
  useEffect(() => {
    if (!state?.sasFiles?.length && !state?.zipFile) return;

    analyseMigration({
      sasFiles: state.sasFiles ?? [],
      zipFile: state.zipFile,
      refDataset: state.refDataset,
      refTargetPath: state.refTargetPath,
    })
      .then((data) => {
        setAssessment(data);
        setDescriptionText(data.pipeline_description ?? "");

        const stored = loadStoredImportance(data.input_hash);
        setImportanceOverrides(stored);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Analysis failed");
      })
      .finally(() => {
        setLoading(false);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleImportanceChange(blockId: string, val: ImportanceLevel) {
    setImportanceOverrides((prev) => {
      const next = { ...prev, [blockId]: val };
      if (assessment) saveStoredImportance(assessment.input_hash, next);
      return next;
    });
  }

  function handleAckChange(blockId: string, checked: boolean) {
    setAcknowledgments((prev) => ({ ...prev, [blockId]: checked }));
  }

  async function handleStartMigration() {
    if (!assessment || !state) return;
    setSubmitting(true);
    try {
      const ackRecords = manualBlocks.map((b) => ({
        block_id: b.block_id,
        text: `I understand ${b.functional_description} in ${b.source_file} cannot be converted automatically`,
        confirmed_at: new Date().toISOString(),
      }));

      const snapshot = {
        pipeline_description: descriptionText,
        importance_overrides: importanceOverrides,
        acknowledgments: ackRecords,
        sensitive_data_confirmed: sensitiveConfirmed,
        assessed_at: new Date().toISOString(),
      };

      await submitMigration(
        state.sasFiles ?? [],
        state.refDataset,
        state.zipFile,
        state.name,
        state.refTargetPath,
        undefined,
        importanceOverrides,
        snapshot,
      );

      navigate("/jobs");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  }

  // Tier groupings
  const manualBlocks = (assessment?.blocks ?? []).filter(
    (b) => !b.is_translatable,
  );
  const reviewBlocks = (assessment?.blocks ?? []).filter(
    (b) =>
      b.is_translatable &&
      !b.is_unknown_proc &&
      (importanceOverrides[b.block_id] ?? b.structural_importance) === "high",
  );
  const bestEffortBlocks = (assessment?.blocks ?? []).filter(
    (b) => b.is_translatable && b.is_unknown_proc,
  );
  const autoBlocks = (assessment?.blocks ?? []).filter(
    (b) => tierFor(b, importanceOverrides) === "auto",
  );

  // Acknowledgment gate
  const requiredAcks = new Set(manualBlocks.map((b) => b.block_id));
  const allAcked =
    [...requiredAcks].every((id) => acknowledgments[id]) &&
    (assessment?.sensitive_data_findings.length ?? 0) === 0 ||
    ([...requiredAcks].every((id) => acknowledgments[id]) &&
      (assessment?.sensitive_data_findings.length ?? 0) > 0 &&
      sensitiveConfirmed);

  const submitDisabled = submitting || !allAcked;

  if (!state?.sasFiles?.length && !state?.zipFile) {
    return <></>;
  }

  return (
    <div className="px-6 py-6 overflow-y-auto flex-1 h-full">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Back */}
        <div>
          <button
            type="button"
            onClick={() => navigate("/jobs")}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Back to migrations
          </button>
        </div>

        <h1 className="text-xl font-semibold text-foreground">
          Pre-Migration Assessment
        </h1>

        {/* ── Loading ─────────────────────────────────────────────── */}
        {loading && <LoadingSkeleton />}

        {/* ── Error ───────────────────────────────────────────────── */}
        {!loading && error && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* ── Assessment ──────────────────────────────────────────── */}
        {!loading && assessment && (
          <div className="space-y-8">
            {/* Parser warning banner */}
            {assessment.parser_warning && (
              <div
                role="alert"
                className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-200"
              >
                <span className="shrink-0 font-semibold">Warning:</span>
                <span>{assessment.parser_warning}</span>
              </div>
            )}

            {/* ── 1. Verdict ──────────────────────────────────────── */}
            <section aria-labelledby="verdict-heading">
              <h2 id="verdict-heading" className="text-base font-semibold text-foreground mb-3">
                Readiness verdict
              </h2>
              <div className="flex flex-wrap gap-4">
                <StatPill
                  value={assessment.stats.needs_manual}
                  label="need manual work"
                  color="red"
                />
                <StatPill
                  value={assessment.stats.review_recommended}
                  label="recommend review"
                  color="amber"
                />
                <StatPill
                  value={assessment.stats.best_effort}
                  label="best-effort"
                  color="blue"
                />
                <StatPill
                  value={assessment.stats.auto_converts}
                  label="convert automatically"
                  color="emerald"
                />
              </div>
            </section>

            {/* ── 2. Blockers (conditional) ───────────────────────── */}
            {(assessment.missing_dependencies.length > 0 ||
              assessment.circular_dependencies.length > 0) && (
              <section aria-labelledby="blockers-heading">
                <h2
                  id="blockers-heading"
                  className="text-base font-semibold text-foreground mb-3"
                >
                  Blockers
                </h2>
                <div className="space-y-3">
                  {assessment.missing_dependencies.length > 0 && (
                    <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 space-y-2">
                      <p className="text-sm font-medium text-destructive">
                        Missing dependencies ({assessment.missing_dependencies.length})
                      </p>
                      <ul className="space-y-1">
                        {assessment.missing_dependencies.map((dep, i) => (
                          <li key={i} className="text-xs text-muted-foreground">
                            <span className="font-mono text-foreground">{dep.name}</span>{" "}
                            ({dep.dependency_type}) — referenced in{" "}
                            <span className="font-mono">{dep.referenced_in}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {assessment.circular_dependencies.length > 0 && (
                    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 space-y-2 dark:border-amber-700 dark:bg-amber-950/30">
                      <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                        Circular dependencies ({assessment.circular_dependencies.length})
                      </p>
                      <ul className="space-y-1">
                        {assessment.circular_dependencies.map((cd, i) => (
                          <li key={i} className="text-xs font-mono text-muted-foreground">
                            {cd.cycle.join(" → ")}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* ── 3. Scope + AI description ───────────────────────── */}
            <section aria-labelledby="scope-heading">
              <h2 id="scope-heading" className="text-base font-semibold text-foreground mb-3">
                Scope
              </h2>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 mb-4">
                <MiniStat label="Files" value={assessment.filenames.length} />
                <MiniStat label="Blocks" value={assessment.stats.total_blocks} />
                <MiniStat label="Macro vars" value={assessment.stats.macro_var_count} />
                <MiniStat label="Macro defs" value={assessment.stats.macro_def_count} />
              </div>

              <div className="rounded-lg border border-border bg-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-foreground">Pipeline description</p>
                  {!editingDescription && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditingDescription(true);
                        setTimeout(() => textareaRef.current?.focus(), 0);
                      }}
                      aria-label="Edit pipeline description"
                      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      Edit <Pencil className="h-3 w-3" aria-hidden />
                    </button>
                  )}
                </div>

                {assessment.llm_skipped ? (
                  <p className="text-sm text-muted-foreground italic">
                    Summary unavailable — could not reach the translation model
                  </p>
                ) : editingDescription ? (
                  <div className="space-y-2">
                    <textarea
                      ref={textareaRef}
                      value={descriptionText}
                      onChange={(e) => setDescriptionText(e.target.value)}
                      rows={4}
                      className="w-full rounded border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-y"
                      aria-label="Edit pipeline description"
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setEditingDescription(false)}
                    >
                      Save
                    </Button>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {descriptionText || "No description available."}
                  </p>
                )}
              </div>

              {(assessment.input_sources.length > 0 ||
                assessment.output_datasets.length > 0) && (
                <div className="mt-3 grid grid-cols-2 gap-3">
                  {assessment.input_sources.length > 0 && (
                    <div className="rounded border border-border bg-card p-3">
                      <p className="text-xs font-medium text-muted-foreground mb-1">
                        Input sources ({assessment.input_sources.length})
                      </p>
                      <ul className="space-y-0.5">
                        {assessment.input_sources.map((ds) => (
                          <li key={ds} className="text-xs font-mono text-foreground">
                            {ds}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {assessment.output_datasets.length > 0 && (
                    <div className="rounded border border-border bg-card p-3">
                      <p className="text-xs font-medium text-muted-foreground mb-1">
                        Output datasets ({assessment.output_datasets.length})
                      </p>
                      <ul className="space-y-0.5">
                        {assessment.output_datasets.map((ds) => (
                          <li key={ds} className="text-xs font-mono text-foreground">
                            {ds}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </section>

            {/* ── 4. Migration risk ───────────────────────────────── */}
            <section aria-labelledby="risk-heading">
              <h2 id="risk-heading" className="text-base font-semibold text-foreground mb-3">
                Migration risk
              </h2>
              <div className="space-y-3">
                <TierSection
                  label="🔴 Needs manual work"
                  count={manualBlocks.length}
                  tier="manual"
                  blocks={manualBlocks}
                  overrides={importanceOverrides}
                  onImportanceChange={handleImportanceChange}
                />
                <TierSection
                  label="🟡 Recommend review"
                  count={reviewBlocks.length}
                  tier="review"
                  blocks={reviewBlocks}
                  overrides={importanceOverrides}
                  onImportanceChange={handleImportanceChange}
                />
                <TierSection
                  label="🔵 Best-effort"
                  count={bestEffortBlocks.length}
                  tier="best-effort"
                  blocks={bestEffortBlocks}
                  overrides={importanceOverrides}
                  onImportanceChange={handleImportanceChange}
                />
                <TierSection
                  label="✅ Converts automatically"
                  count={autoBlocks.length}
                  tier="auto"
                  blocks={autoBlocks}
                  overrides={importanceOverrides}
                  onImportanceChange={handleImportanceChange}
                />
              </div>
            </section>

            {/* ── 5. Validation coverage ──────────────────────────── */}
            {assessment.output_coverage.length > 0 && (
              <section aria-labelledby="coverage-heading">
                <h2
                  id="coverage-heading"
                  className="text-base font-semibold text-foreground mb-3"
                >
                  Validation coverage
                </h2>
                <div className="space-y-2">
                  {assessment.output_coverage.map((item) => (
                    <OutputCoverageRow key={item.dataset_name} item={item} />
                  ))}
                </div>
              </section>
            )}

            {/* ── 6. Post-migration effort ─────────────────────────── */}
            <section aria-labelledby="effort-heading">
              <h2 id="effort-heading" className="text-base font-semibold text-foreground mb-3">
                Post-migration effort estimate
              </h2>
              <div className="rounded-lg border border-border bg-card p-4">
                <p className="text-2xl font-semibold text-foreground">
                  {fmtMinutes(
                    assessment.stats.estimated_minutes_low,
                    assessment.stats.estimated_minutes_high,
                  )}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Estimated manual review time across{" "}
                  {assessment.stats.needs_manual + assessment.stats.review_recommended} block
                  {assessment.stats.needs_manual + assessment.stats.review_recommended !== 1
                    ? "s"
                    : ""}{" "}
                  requiring attention
                </p>
              </div>
            </section>

            {/* ── 7. Configuration values ──────────────────────────── */}
            {assessment.configuration_values.length > 0 && (
              <section aria-labelledby="config-heading">
                <h2
                  id="config-heading"
                  className="text-base font-semibold text-foreground mb-3"
                >
                  Configuration values
                </h2>
                <div className="space-y-1.5">
                  {assessment.configuration_values.map((item) => (
                    <ConfigValueRow key={item.name} item={item} />
                  ))}
                </div>
              </section>
            )}

            {/* ── 8. Sensitive data (conditional) ─────────────────── */}
            {assessment.sensitive_data_findings.length > 0 && (
              <section aria-labelledby="pii-heading">
                <h2
                  id="pii-heading"
                  className="text-base font-semibold text-foreground mb-3"
                >
                  Sensitive data detected
                </h2>
                <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 space-y-3">
                  <p className="text-sm text-destructive font-medium">
                    The following PII-pattern column names were found:
                  </p>
                  <ul className="space-y-1">
                    {assessment.sensitive_data_findings.map((f, i) => (
                      <li key={i} className="text-xs text-muted-foreground">
                        Pattern{" "}
                        <span className="font-mono text-foreground">{f.pattern}</span>{" "}
                        in <span className="font-mono">{f.found_in}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </section>
            )}

            {/* ── 9. Acknowledgments + actions ─────────────────────── */}
            <section aria-labelledby="ack-heading">
              <h2 id="ack-heading" className="text-base font-semibold text-foreground mb-3">
                Acknowledgments
              </h2>
              <div className="space-y-3">
                {manualBlocks.map((block) => (
                  <label
                    key={block.block_id}
                    className="flex items-start gap-3 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      className="mt-0.5 h-4 w-4 rounded border-input accent-primary cursor-pointer"
                      checked={acknowledgments[block.block_id] ?? false}
                      onChange={(e) =>
                        handleAckChange(block.block_id, e.target.checked)
                      }
                      aria-label={`Acknowledge that ${block.functional_description} in ${block.source_file} cannot be converted automatically`}
                    />
                    <span className="text-sm text-foreground">
                      I understand{" "}
                      <strong>{block.functional_description}</strong> in{" "}
                      <span className="font-mono">{block.source_file}</span> cannot be
                      converted automatically and requires manual implementation.
                    </span>
                  </label>
                ))}

                {assessment.sensitive_data_findings.length > 0 && (
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      className="mt-0.5 h-4 w-4 rounded border-input accent-primary cursor-pointer"
                      checked={sensitiveConfirmed}
                      onChange={(e) => setSensitiveConfirmed(e.target.checked)}
                      aria-label="Acknowledge sensitive data findings"
                    />
                    <span className="text-sm text-foreground">
                      I acknowledge that potentially sensitive data (PII) was detected and
                      confirm that appropriate data handling procedures will be followed.
                    </span>
                  </label>
                )}

                {manualBlocks.length === 0 &&
                  assessment.sensitive_data_findings.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                      No acknowledgments required — this migration can proceed automatically.
                    </p>
                  )}
              </div>

              <div className="mt-6 flex items-center gap-3">
                <Button
                  onClick={() => void handleStartMigration()}
                  disabled={submitDisabled}
                  aria-busy={submitting}
                  aria-label="Start migration"
                >
                  {submitting ? "Starting…" : "Start Migration"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => navigate("/jobs")}
                  disabled={submitting}
                >
                  Cancel
                </Button>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Utility components ────────────────────────────────────────────────────────

interface StatPillProps {
  value: number;
  label: string;
  color: "red" | "amber" | "blue" | "emerald";
}

function StatPill({ value, label, color }: StatPillProps) {
  const colorClass = {
    red: "bg-red-100 text-red-700 dark:bg-red-950/30 dark:text-red-400",
    amber: "bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400",
    blue: "bg-blue-100 text-blue-700 dark:bg-blue-950/30 dark:text-blue-400",
    emerald:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400",
  }[color];

  return (
    <div className={`rounded-lg px-4 py-3 text-center ${colorClass}`}>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs mt-0.5 leading-tight">{label}</p>
    </div>
  );
}

interface MiniStatProps {
  label: string;
  value: number;
}

function MiniStat({ label, value }: MiniStatProps) {
  return (
    <div className="rounded border border-border bg-card px-3 py-2 text-center">
      <p className="text-lg font-semibold text-foreground">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
