# F2-improvements — Agentic Pipeline: Prompts, New Agents, Multi-file Output, Editor 1:1 View

**Phase:** 2 (extension of F2-agentic-workflow)
**Area:** Worker / Backend / Frontend
**Status:** in-progress
**Branch:** feat/F2-agentic-workflow

## Goal

Improve the agentic pipeline end-to-end: better prompts, two new agents, uncertainty
flagging, deterministic routing for trivial constructs, multi-file Python output, a
SAS→Python 1:1 comparison view in the editor, and a Plan tab for clients.

Done looks like: a migrated job runs through the full updated pipeline; the frontend
shows a Plan tab; clicking a SAS file in the editor shows only the Python it produced;
`make test` exits 0; ruff and mypy pass.

---

## Context: what exists today

| File | Purpose |
|------|---------|
| `src/worker/engine/agents/analysis.py` | AnalysisAgent |
| `src/worker/engine/agents/data_step.py` | DataStepAgent |
| `src/worker/engine/agents/proc.py` | ProcAgent |
| `src/worker/engine/agents/macro_resolver.py` | MacroResolverAgent |
| `src/worker/engine/agents/failure_interpreter.py` | FailureInterpreterAgent |
| `src/worker/engine/agents/documentation.py` | DocumentationAgent |
| `src/worker/engine/router.py` | TranslationRouter + _ProcSortHelper |
| `src/worker/engine/models.py` | JobContext, SASBlock, GeneratedBlock, etc. |
| `src/worker/main.py` | JobOrchestrator._execute() |
| `src/backend/db/models.py` | Job ORM |
| `src/frontend/src/pages/JobDetailPage.tsx` | 3 tabs: Editor, Report, Lineage |

---

## Subtasks

### S-A: Enrich models — `src/worker/engine/models.py`
**Depends on:** none
**Done when:** new types compile; existing tests still pass.

Add after `ReconciliationReport`, before `JobContext`:

```python
class TranslationStrategy(StrEnum):
    TRANSLATE = "translate"
    STUB = "stub"
    SKIP = "skip"

class BlockRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class BlockPlan(BaseModel):
    block_id: str
    source_file: str
    start_line: int
    block_type: str
    strategy: TranslationStrategy
    risk: BlockRisk
    rationale: str
    estimated_effort: str   # "low" | "medium" | "high"

class MigrationPlan(BaseModel):
    summary: str
    block_plans: list[BlockPlan]
    overall_risk: BlockRisk
    recommended_review_blocks: list[str]
    cross_file_dependencies: list[str]

class ColumnFlow(BaseModel):
    column: str
    source_dataset: str
    target_dataset: str
    via_block_id: str
    transformation: str | None = None

class MacroUsage(BaseModel):
    macro_name: str
    macro_value: str
    used_in_block_id: str

class EnrichedLineage(BaseModel):
    column_flows: list[ColumnFlow]
    macro_usages: list[MacroUsage]
    cross_file_edges: list[dict[str, str]]
    dataset_summaries: dict[str, str]
```

Modify `GeneratedBlock`:
```python
class GeneratedBlock(BaseModel):
    source_block: SASBlock
    python_code: str
    is_untranslatable: bool = False
    confidence: str = "high"          # "high" | "medium" | "low"
    uncertainty_notes: list[str] = []
```

Add to `JobContext`:
```python
migration_plan: MigrationPlan | None = None
enriched_lineage: EnrichedLineage | None = None
```

Update `windowed_context()` to propagate `migration_plan` but not `enriched_lineage`.
- [x] done

---

### S-B: Create `MigrationPlannerAgent`
**New file:** `src/worker/engine/agents/migration_planner.py`
**Depends on:** S-A
**Done when:** `plan(context) -> MigrationPlan` works; unit test mocks LLM and validates output shape.

Follows identical Pydantic-AI pattern to existing agents.

**LLM output model:**
```python
class PlannerResult(BaseModel):
    summary: str
    overall_risk: str
    block_plans: list[dict]   # flat dict, constructed to BlockPlan in agent class
    recommended_review_blocks: list[str]
    cross_file_dependencies: list[str]
```

**max_tokens:** 6000

**System prompt:**
```
# agent: MigrationPlannerAgent

You are a senior SAS-to-Python migration architect. Before any code is translated,
analyse the full SAS codebase and produce a structured migration plan that guides
the downstream translation agents and gives the client a clear action list.

Input:
- One or more SAS source files with their filenames.
- A list of pre-resolved macro variables.
- A list of parsed blocks: each has block_id ("source_file:start_line"), block_type
  (DATA_STEP | PROC_SQL | PROC_SORT | UNTRANSLATABLE), input_datasets, output_datasets.

Your tasks:
1. Write a 2-3 sentence plain-English summary of what this SAS codebase does as a
   whole, at a business level (not technical). Assume the reader is a business analyst.
2. For each block, assign:
   - strategy: "translate" (automated), "stub" (needs manual completion), or "skip"
     (already handled, e.g. simple PROC SORT).
   - risk: "low", "medium", or "high" based on:
       HIGH  — CALL SYMPUT/SYMPUTX, dynamic dataset names, nested macros, %INCLUDE,
               PROC types we don't handle, deeply nested DO loops with RETAIN
       MEDIUM — BY-group processing, MERGE with complex BY, multi-output DATA steps,
                CASE expressions in PROC SQL, PROC SORT with complex BY clause
       LOW   — simple SET/filter/rename DATA steps, straightforward PROC SQL SELECTs
   - rationale: one sentence explaining the risk level and strategy.
   - estimated_effort: "low" (< 1 hour review), "medium" (1-4 hours),
     "high" (> 4 hours or requires domain knowledge).
3. Set overall_risk to the highest risk level across all blocks.
4. List recommended_review_blocks: block_ids the human should inspect first
   (all HIGH risk blocks, plus MEDIUM blocks with cross-file dependencies).
5. List cross_file_dependencies: plain-English notes for any dataset that flows
   between files.

Return ONLY a JSON object — no prose, no markdown fences:
{
  "summary": "...",
  "overall_risk": "low|medium|high",
  "block_plans": [
    {
      "block_id": "source_file:start_line",
      "source_file": "...",
      "start_line": <int>,
      "block_type": "DATA_STEP|PROC_SQL|PROC_SORT|UNTRANSLATABLE",
      "strategy": "translate|stub|skip",
      "risk": "low|medium|high",
      "rationale": "...",
      "estimated_effort": "low|medium|high"
    }
  ],
  "recommended_review_blocks": ["source_file:start_line", ...],
  "cross_file_dependencies": ["...", ...]
}
```
- [x] done

---

### S-C: Create `LineageEnricherAgent`
**New file:** `src/worker/engine/agents/lineage_enricher.py`
**Depends on:** S-A
**Done when:** `enrich(context) -> EnrichedLineage` works; unit test mocks LLM.

**max_tokens:** 8000

**System prompt:**
```
# agent: LineageEnricherAgent

You are a SAS data lineage analyst. Given the original SAS source files, resolved
macro variables, and the dependency-ordered list of parsed blocks, produce an enriched
lineage map that goes beyond block-to-block edges.

Input:
- SAS source files with filenames.
- Resolved macro variables.
- Parsed blocks with block_id ("source_file:start_line"), block_type, input_datasets,
  output_datasets, and raw SAS text.

Your tasks:
1. column_flows: For each dataset-to-dataset data flow, identify columns that are
   passed, renamed, or derived. Only emit entries you can determine with confidence.
   Do not guess column names not present in the SAS source.
   Each entry: { column, source_dataset, target_dataset, via_block_id, transformation }
   where transformation is a short description or null for pass-through.

2. macro_usages: For each block referencing a macro variable (&name), one entry per
   block per macro referenced:
   { macro_name (UPPERCASE), macro_value, used_in_block_id }

3. cross_file_edges: If a dataset produced in one file is consumed in a different file:
   { source_block_id, target_block_id, shared_dataset (lowercased) }

4. dataset_summaries: For each distinct dataset name, one sentence describing what it
   contains, inferred from column names and SAS logic. Write "No description available."
   if nothing can be inferred.

Return ONLY a JSON object — no prose, no markdown fences:
{
  "column_flows": [...],
  "macro_usages": [...],
  "cross_file_edges": [...],
  "dataset_summaries": {"dataset_name": "description", ...}
}
```
- [x] done

---

### S-D: Improved system prompts for 6 existing agents
**Files:** all 6 agent files
**Depends on:** none (independent)
**Done when:** `_SYSTEM_PROMPT` replaced in each file; `make test` still green.

#### AnalysisAgent prompt (replace `_SYSTEM_PROMPT`):
```
# agent: AnalysisAgent

You are a SAS migration analyst. Given one or more SAS source files and a list of
already-resolved macro variables, perform a structural analysis and return a single
JSON object — no prose, no markdown fences.

Your tasks:
1. Identify all macro variable declarations (%LET) and their resolved values.
   Include pre-resolved macro vars supplied in the input AND any additional ones you
   discover. Each entry: name (UPPERCASE), raw_value, source_file, line (int).

2. Determine the dataset dependency order.
   Topologically sorted list of DATASET NAMES (not block IDs):
   - A dataset that is an input to any block must appear before the dataset that block outputs.
   - If no dependency between two datasets, preserve document order.
   - If a dataset appears only as output, list it last.
   - Use lowercased dataset names exactly as they appear in the SAS source.

3. Flag high-risk SAS patterns in risk_flags.
   Each entry MUST be: "<source_file>:<start_line> — <short description>"
   Patterns to flag: nested %MACRO/%MEND, %INCLUDE, PROC DATASETS, dynamic dataset
   names from macros (DATA &prefix.out), CALL SYMPUT/CALL SYMPUTX, %SYSCALL/%SYSFUNC
   with non-trivial expressions, multiple output datasets (DATA a b c;), RETAIN with
   array references, DO loops with conditional OUTPUT statements.

Return ONLY:
{
  "resolved_macros": [{"name":"...","raw_value":"...","source_file":"...","line":<int>}],
  "dependency_order": ["dataset1", ...],
  "risk_flags": ["file.sas:12 — CALL SYMPUT assigns macro at runtime", ...]
}
```

#### DataStepAgent prompt (replace `_SYSTEM_PROMPT`):
```
# agent: DataStepAgent

You are a SAS-to-Python migration engineer. Translate the SAS DATA step below into
idiomatic pandas code.

Rules:
- Emit only Python code. No prose. No markdown fences.
- Return: {"python_code": "...", "confidence": "high|medium|low", "uncertainty_notes": [...]}
- Set confidence: "high" if certain; "medium" if pattern applied but logic is ambiguous;
  "low" if one or more constructs cannot be confidently translated.
- For each uncertain construct, add to uncertainty_notes a short human-readable note.
- For low/medium confidence constructs, insert before the relevant lines:
    # UNCERTAIN: <reason> — human review required
- Add # SAS: <source_file>:<line_number> after each logical section.
- Use pd.DataFrame and numpy only. No PySpark, no SQL, no pandasql.
- Preserve SAS column names exactly, lowercased.
- Treat each SAS dataset name as an already-loaded pd.DataFrame variable (lowercased).
- Macro variables are pre-resolved; use their literal values directly.

Translation patterns:
- IF/THEN/ELSE → np.where() for simple; .loc[mask] for multi-statement blocks.
- RETAIN → iterrows() with explicit accumulator, or shift()+cumsum() for running totals.
- Arrays (ARRAY x{n}) → Python list of column names; iterate with for-loop.
- BY-group (BY var; FIRST.var / LAST.var) → sort + groupby().transform() or .diff().ne(0).
- DO / END → for-loop or vectorised; prefer vectorised.
- Implicit OUTPUT → every-row output; use standard DataFrame construction.
- Explicit OUTPUT inside DO → build list of dicts, convert with pd.DataFrame(rows).
- MERGE with BY → df.merge(..., how="outer") + sort_values(BY).
- KEEP / DROP → df[kept_cols] or df.drop(columns=[...]).
- LENGTH / FORMAT / INFORMAT → comment out with # SAS: preserved as metadata.
- SET with multiple datasets → pd.concat([...], ignore_index=True).

Assign final output to lowercased OUTPUT dataset name (dots → underscores).
```

#### ProcAgent prompt (replace `_SYSTEM_PROMPT`):
```
# agent: ProcAgent

You are a SAS-to-Python migration engineer specialising in SQL translation.
Translate the SAS PROC SQL block below into idiomatic pandas code.

Rules:
- Emit only Python code. No prose. No markdown fences.
- Return: {"python_code": "...", "confidence": "high|medium|low", "uncertainty_notes": [...]}
- Set confidence and uncertainty_notes following the same rules as DataStepAgent.
- Add # SAS: <source_file>:<line_number> after each logical section (once per statement).
- Do NOT use pandasql, sqlite3, duckdb, or any SQL engine. Use pure pandas.
- Treat SAS dataset names as already-loaded pd.DataFrame variables (lowercased).
- Macro variables are pre-resolved; use their literal values directly.

Translation patterns:
- JOIN → df.merge(right, on=[...], how="inner|left|right|outer")
- GROUP BY + agg → .groupby([...]).agg({...}).reset_index()
- WHERE (pre-agg) → boolean indexing or .query()
- HAVING (post-agg) → .loc[condition] after .agg()
- ORDER BY → .sort_values([...])
- CREATE TABLE x AS SELECT → assign to x (lowercased)
- DISTINCT → .drop_duplicates()
- CASE WHEN → np.select(conditions, choices, default=...) or np.where() for binary
- Window: SUM(col) OVER (PARTITION BY p) → .groupby(p)[col].transform("sum")
- Window: ROW_NUMBER() OVER (PARTITION BY p ORDER BY o) →
    df.sort_values(o).groupby(p).cumcount() + 1
- CTEs (WITH x AS ...) → assign intermediate to variable named after CTE alias
- INSERT INTO existing SELECT → pd.concat([existing, new_rows]).reset_index(drop=True)
- SELECT INTO :macro_var → extract scalar, assign to Python var, add # SAS: comment
- CALCULATED col → use Python expression; no SAS CALCULATED keyword
```

#### MacroResolverAgent prompt (replace `_SYSTEM_PROMPT`):
```
# agent: MacroResolverAgent

You are a SAS macro expansion expert. Given SAS code with macro calls the deterministic
expander could not handle, attempt to expand them from context.

Resolution rules:
- could_resolve = true when ALL hold:
    (a) macro references only variables listed in "Already-resolved macros"
    (b) expansion produces a fixed string — no remaining &var or %macro refs
    (c) no SAS functions (%SYSFUNC, %EVAL with complex expressions) need to execute
- could_resolve = false when:
    - macro variable was set via CALL SYMPUT / CALL SYMPUTX
    - macro is a parameterized %MACRO ... %MEND
    - expansion requires executing %SYSFUNC or %SYSCALL
    - recursive or deeply nested macros cannot be flattened statically

Unambiguous examples (always resolve):
- "&REPORT_YEAR" with REPORT_YEAR="2023" → "2023", could_resolve: true
- "data &PREFIX.output;" with PREFIX="q1_" → "data q1_output;", could_resolve: true
- "&START_DT"d with START_DT="01JAN2023" → "'01JAN2023'd", could_resolve: true

Return ONLY: { "expanded_text": "...", "could_resolve": true|false }
No prose. No markdown fences.
```

#### FailureInterpreterAgent prompt (replace `_SYSTEM_PROMPT`):
```
# agent: FailureInterpreterAgent

You are a SAS-to-Python migration debugger. A reconciliation test has failed.
Identify the most likely root cause and produce a concise actionable retry hint.

Output: { "retry_hint": "...", "affected_block_id": "..." }
- retry_hint: 1-2 sentences naming the specific column/operation/construct that was
  mistranslated and exactly how to fix it on retry.
- affected_block_id: "source_file:start_line"
    - Use # SAS: <file>:<line> provenance comments if present (nearest to offending lines)
    - If no provenance comments, inspect code structure and name the most plausible block
    - Use "unknown:0" only as last resort
    - If multiple blocks contribute, pick the one whose fix resolves the most diff rows

Common failure patterns:
- Row count mismatch → wrong merge type (inner vs outer), missing filter, implicit OUTPUT not replicated
- Column value mismatch → RETAIN not initialised to zero, wrong CASE branch, numeric precision
- Column name mismatch → column not lowercased, KEEP/DROP misapplied
- Type mismatch → SAS character vs numeric conflated; SAS dates are days since 1960-01-01

No prose, no markdown fences.
```

#### DocumentationAgent prompt (replace `_SYSTEM_PROMPT`):
```
# agent: DocumentationAgent

You are a technical documentation expert for SAS-to-Python migrations.
Produce structured Markdown a business analyst can read without further editing.

Required ## sections in this order:

## Overview
2-4 sentences describing what this codebase does at a BUSINESS level (not technical).
Infer domain from dataset/column/variable names.
Example: dataset CLAIMS_PAID with MEMBER_ID, AMOUNT → insurance claims processing.

## Key Datasets
Table: | Dataset | Role | Row-level description |
- Role: "Input", "Intermediate", or "Final Output"
- Row-level description: what one row represents (e.g. "one claim payment per member
  per date"). Infer from column names. Write "Unknown" only if no inference is possible.

## Macro Variables
Table: | Name | Resolved Value | Declared In | Purpose |
- Purpose: what the macro controls. Infer from usage; write "Unknown" if not clear.

## Business Logic
Numbered list in dependency order. Each item: one sentence stating WHAT HAPPENS
(avoid pandas/SAS jargon).
Example: "3. Claims are filtered to the report year and joined to the eligibility table."

## Migration Notes
Bullet list per risk flag or untranslatable block:
- `file.sas:42` — issue description — recommended action
Write "No migration issues identified." if none.

## Reconciliation Summary
One sentence stating pass/fail. If failed, list specific failed checks and implications.

Return: { "markdown": "..." }
No preamble. No code fences around JSON. Valid GitHub-Flavored Markdown inside.
```
- [x] done

---

### S-E: `_SimpleCopyHelper` in `TranslationRouter`
**File:** `src/worker/engine/router.py`
**Depends on:** S-A
**Done when:** pure SET+KEEP/DROP DATA steps bypass the LLM; unit test confirms no LLM call.

Add `_SimpleCopyHelper` class that handles DATA steps matching the pattern:
`DATA out; SET in; KEEP col1 col2; RUN;` (or with DROP instead of KEEP, no other statements).

Detection regex (in `TranslationRouter.route()`): if `block.block_type == DATA_STEP` AND
raw_sas contains only `DATA`, `SET`, and `KEEP`/`DROP` statements (no IF, DO, MERGE,
RETAIN, ARRAY, OUTPUT), route to `_SimpleCopyHelper` instead of `DataStepAgent`.

```python
class _SimpleCopyHelper:
    async def translate(self, block: SASBlock, context: JobContext) -> GeneratedBlock:
        # parse KEEP/DROP from raw_sas; emit df[kept_cols].copy() or df.drop(...)
        ...
        return GeneratedBlock(source_block=block, python_code=code, confidence="high")
```
- [x] done

---

### S-F: Two-phase refinement loop — `src/worker/main.py`
**Depends on:** S-A
**Done when:** `_execute()` runs reconciliation exactly twice (initial + one retry); no `while` loop; `_MAX_RETRIES` removed.

Replace `_translate_with_refinement()` with an explicit two-phase sequence:
```
phase 1: translate all blocks → generated_v1
         reconcile(generated_v1) → report_v1
         if report_v1 passed: use as final
         if failed: continue to phase 2
phase 2: FailureInterpreterAgent → retry_hint, affected_block_id
         re-translate affected block → generated_v2
         reconcile(generated_v2) → report_v2 (final regardless of pass/fail)
```

The `context.retry_count` field is still updated (+1 after phase 2) for observability.
- [x] done

---

### S-G: Wire new agents into `JobOrchestrator._execute()`
**File:** `src/worker/main.py`
**Depends on:** S-B, S-C, S-F
**Done when:** all new agents run in the pipeline; `migration_plan` persisted to DB.

Orchestration sequence after changes:
```
1.  SASParser.parse()
2.  MacroExpander.expand()  (per-block, soft-fail)
3.  AnalysisAgent.analyse()      → JobContext
3.5 MigrationPlannerAgent.plan() → MigrationPlan (best-effort, try/except)
4.  Two-phase translate + reconcile (see S-F)
5.  CodeGenerator.assemble()     → dict[str, str] generated_files (see S-H)
6.  Final reconciliation
7.5 LineageEnricherAgent.enrich() → EnrichedLineage (best-effort, try/except)
8.  DocumentationAgent.generate()
9.  Lineage extraction + merge enriched fields
10. Persist: status=done, python_code (concatenated), generated_files, report,
             lineage (enriched), doc, migration_plan
```
- [x] done

---

### S-H: Multi-file output — `src/worker/engine/codegen.py`
**Depends on:** none (independent)
**Done when:** `assemble()` returns `dict[str, str]`; one `.py` per SAS source file + `pipeline.py` orchestrator; existing tests updated.

Changes:
- `assemble(generated, macro_vars) -> dict[str, str]`
  - Group `GeneratedBlock` objects by `source_block.source_file`
  - Emit one Python module per source SAS file (e.g. `etl.sas` → `etl.py`)
  - Emit `pipeline.py` that imports each module in dependency order and calls its `run()` function
  - Each module wraps its blocks in a `def run(dataframes: dict) -> dict:` function
  - Add `UNCERTAIN` block marker in module header if any block has `confidence != "high"`
- Keep a `assemble_flat()` helper that returns the concatenated string (used for reconciliation exec and `python_code` DB column)
- [x] done

---

### S-I: DB changes
**Files:** `src/backend/db/models.py`, `alembic/versions/`
**Depends on:** none
**Done when:** `migration_plan` and `generated_files` columns exist; Alembic migration runs clean.

Add to `Job`:
```python
migration_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
generated_files: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
```

Alembic migration:
```python
def upgrade() -> None:
    op.add_column("jobs", sa.Column("migration_plan", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("generated_files", sa.JSON(), nullable=True))
def downgrade() -> None:
    op.drop_column("jobs", "migration_plan")
    op.drop_column("jobs", "generated_files")
```
- [x] done

---

### S-J: API schemas + routes
**Files:** `src/backend/api/schemas.py`, `src/backend/api/routes/jobs.py`
**Depends on:** S-I
**Done when:** `GET /jobs/{id}/plan` returns `JobPlanResponse` or 202; `JobStatusResponse` includes `generated_files`; `JobLineageResponse` includes enriched fields.

Add to `schemas.py`:
```python
class BlockPlanResponse(BaseModel):
    block_id: str; source_file: str; start_line: int; block_type: str
    strategy: str; risk: str; rationale: str; estimated_effort: str

class JobPlanResponse(BaseModel):
    job_id: uuid.UUID; summary: str; overall_risk: str
    block_plans: list[BlockPlanResponse]
    recommended_review_blocks: list[str]
    cross_file_dependencies: list[str]

class ColumnFlowResponse(BaseModel):
    column: str; source_dataset: str; target_dataset: str
    via_block_id: str; transformation: str | None

class MacroUsageResponse(BaseModel):
    macro_name: str; macro_value: str; used_in_block_id: str
```

Extend `JobStatusResponse`:
```python
generated_files: dict[str, str] | None = None
```

Extend `JobLineageResponse`:
```python
column_flows: list[ColumnFlowResponse] = []
macro_usages: list[MacroUsageResponse] = []
cross_file_edges: list[dict] = []
dataset_summaries: dict[str, str] = {}
```

Add route `GET /jobs/{job_id}/plan` (same pattern as `get_job_doc`).
- [x] done

---

### S-K: Frontend — types + API function
**Files:** `src/frontend/src/api/types.ts`, `src/frontend/src/api/jobs.ts`
**Depends on:** S-J
**Done when:** TypeScript compiles; `getJobPlan` function available.

Add to `types.ts`: `BlockPlan`, `JobPlanResponse`, `ColumnFlow`, `MacroUsage`.
Extend `JobLineageResponse` with optional enriched fields (default `[]`/`{}`).
Add `generated_files: Record<string, string> | null` to `JobStatus`.

Add to `jobs.ts`:
```typescript
export async function getJobPlan(jobId: string): Promise<JobPlanResponse>
```
- [x] done

---

### S-L: Frontend — PlanTab + tab changes
**File:** `src/frontend/src/pages/JobDetailPage.tsx`
**Depends on:** S-K
**Done when:** "Plan" is the first tab; plan table renders with risk colours; clicking a tab navigates correctly.

Add `PlanTab` component:
- `useQuery` fetching `getJobPlan(jobId)` (enabled only when `isDone`)
- Summary card: overall risk colour-coded (green=low, amber=medium, red=high)
- "Blocks requiring manual review" — block IDs in amber monospace
- "Cross-file dependencies" — bullet list
- Block-plan table: Block | Type | Strategy | Risk | Effort | Rationale
  - Risk column colour-coded matching summary card

Tab order (update `defaultValue` to `"plan"`):
```
Plan → Editor → Report → Lineage
```
- [ ] done

---

### S-M: Frontend — Editor 1:1 SAS↔Python comparison
**File:** `src/frontend/src/pages/JobDetailPage.tsx` (EditorTab component)
**Depends on:** S-K
**Done when:** clicking a SAS file in the tree shows SAS on left and its Python module on right in MonacoDiffViewer; no full-pipeline Python shown unless no `generated_files`.

Changes to `EditorTab`:
- When user selects a SAS file from the file tree, look up `job.generated_files[selectedFile]`
  (derive key from SAS filename: `etl.sas` → `etl.py`) to get the matching Python.
- Pass SAS source (from `/sources`) as `original` and matching Python as `modified` to `MonacoDiffViewer`.
- Fallback: if `generated_files` is null (old jobs), show full `job.python_code` as before.
- [ ] done

---

### S-N: Frontend — LineageGraph column flow labels
**File:** `src/frontend/src/components/LineageGraph.tsx`
**Depends on:** S-K
**Done when:** edges show column count label when `column_flows` is non-empty; existing rendering unchanged when empty.

For each ReactFlow edge, compute column count from `lineage.column_flows` filtered by `via_block_id`. If > 0, set edge `label` to `"N columns"`.
- [ ] done

---

### S-O: Unit tests for new agents
**Files:** `tests/test_migration_planner_agent.py`, `tests/test_lineage_enricher_agent.py`
**Depends on:** S-B, S-C
**Done when:** both test files have at least 3 tests each (mocking `_agent.run`); `make test` green.
- [x] done

---

### S-P: `agents/__init__.py` exports
**File:** `src/worker/engine/agents/__init__.py`
**Depends on:** S-B, S-C
**Done when:** `MigrationPlannerAgent` and `LineageEnricherAgent` importable from the package.
- [x] done

---

### S-Q: `make test` + ruff + mypy full pass
**Depends on:** all above
- [ ] done

---

## Implementation Priority

**Phase A — Models + deterministic routing (unblocks everything)**
S-A → S-E, S-H (parallel)

**Phase B — New agents**
S-B, S-C (parallel after S-A) → S-O, S-P (parallel)

**Phase C — Prompt rewrites**
S-D (independent, can start immediately)

**Phase D — Orchestration wiring**
S-F → S-G (after S-B, S-C, S-F)

**Phase E — DB + API**
S-I → S-J

**Phase F — Frontend**
S-K → S-L, S-M, S-N (parallel)

**Phase G — Verification**
S-Q

---

## Acceptance Criteria

- [ ] `MigrationPlannerAgent` runs before translation; `migration_plan` stored in DB
- [ ] `LineageEnricherAgent` runs after translation; enriched fields merged into `lineage` JSON
- [ ] All 6 existing agent prompts replaced with improved versions
- [ ] Translation agents emit `confidence` + `uncertainty_notes`; `# UNCERTAIN:` comments appear in generated code where confidence < high
- [ ] Pure SET+KEEP/DROP DATA steps bypass LLM → `_SimpleCopyHelper`
- [ ] Refinement loop is exactly two phases (no `while` loop)
- [ ] `CodeGenerator.assemble()` returns `dict[str, str]` (one file per SAS source + `pipeline.py`)
- [ ] `generated_files` DB column populated; included in `GET /jobs/{id}` response
- [ ] `GET /jobs/{id}/plan` returns `JobPlanResponse` or 202
- [ ] Frontend: "Plan" is first tab with risk table
- [ ] Frontend: clicking a SAS file in Editor shows SAS ↔ that file's Python only
- [ ] Frontend: LineageGraph edges show column count where available
- [ ] `make test` exits 0; ruff + mypy clean
