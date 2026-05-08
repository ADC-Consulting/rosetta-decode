# F21 — Pre-Migration Assessment

**Phase:** 2  
**Area:** Both (Backend / API + Frontend)  
**Status:** in-progress

## Goal

Before committing to a migration run, the user — typically the manager or engineer who owns the legacy SAS code — is shown a full readiness assessment derived entirely from a static parse of the uploaded files plus a lightweight LLM summary call. No job is created and no worker is invoked. The assessment answers the four questions a code owner needs to make a confident sign-off decision: does the tool understand the code, what cannot be automatically translated, can the result be verified, and what manual effort will be required after the migration runs.

A new stateless `POST /analyse` endpoint runs the SAS parser synchronously and makes a single lightweight LLM call to generate a plain-English pipeline description. The frontend holds uploaded files in memory, sends them to `/analyse` to display the assessment at `/migrate/preview`, then (on confirmation) sends the same files to `POST /migrate`. From the user's perspective they select files once, review the assessment, and proceed.

Done looks like: a user uploads SAS files, sees the assessment page with all seven sections populated, can adjust structural importance per block, can add a name and notes, and confirms into a migration job — with all confirmation data stored on the job record.

## Acceptance Criteria

- [ ] `POST /analyse` returns `AnalyseResponse` within 10 seconds for a typical SAS project (3–5 files, ≤20 blocks)
- [ ] Assessment page shows all seven sections: verdict, scope + description, missing dependencies/circular deps (if any), migration risk (all four tiers), validation coverage with schema preview, post-migration effort, configuration values
- [ ] Sensitive data warning appears when PII-pattern column names are detected in uploaded `.sas7bdat` metadata
- [ ] Structural importance overrides are persisted in `localStorage` keyed on `input_hash` and survive page refresh
- [ ] "Start Migration" button is locked until all required acknowledgment checkboxes are ticked
- [ ] `POST /migrate` stores `notes` and `assessment` (including importance overrides and acknowledgment record) on the job row
- [ ] `/analyse` degrades gracefully: LLM failure → assessment shown without description; parser failure → scope section only with warning
- [ ] Navigating directly to `/migrate/preview` with no files in `location.state` redirects to `/jobs`
- [ ] `make test` exits 0
- [ ] ruff and mypy pass

## Layout

See brainstorm record in session journal. Final layout: full-page route `/migrate/preview`. Seven sections in order: verdict line → prior migration history (conditional) → blockers (missing deps + circular deps, conditional) → scope + AI description → unverifiable output warning (conditional) → migration risk (four tiers: 🔴 manual / 🟡 review / 🔵 best-effort / ✅ auto) → validation coverage → post-migration effort → configuration values → sensitive data (conditional) → acknowledgments + action buttons. Happy path collapses all conditional sections.

## Subtasks

---

### S-A: Alembic migration 018 — `notes` and `assessment` columns
**File:** `alembic/versions/018_add_job_notes_assessment.py`  
**Depends on:** none  
**Done when:** migration adds `notes TEXT NULL` and `assessment JSON NULL` to `jobs` table using `sa.JSON()` (not JSONB — SQLite compatibility); `alembic downgrade` removes them cleanly.
- [ ] done

---

### S-B: `Job` ORM model — add `notes` and `assessment` mapped columns
**File:** `src/backend/db/models.py`  
**Depends on:** S-A  
**Done when:** `Job` has `notes: Mapped[str | None] = mapped_column(Text, nullable=True)` and `assessment: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)`.
- [ ] done

---

### S-C: `AnalyseResponse` Pydantic schemas
**File:** `src/backend/api/schemas.py`  
**Depends on:** none  
**Done when:** the following models exist and pass mypy:

```python
class AssessedBlock(BaseModel):
    block_id: str                 # "{source_file}:{start_line}"
    source_file: str
    start_line: int
    end_line: int
    block_type: str               # BlockType value
    functional_description: str   # plain English, rule-based from block_type
    is_translatable: bool         # False for UNRECOGNIZED
    is_unknown_proc: bool         # True for PROC_UNKNOWN
    structural_importance: Literal["low", "medium", "high"]
    importance_reason: str        # "terminal output" / "pipeline entry" / "feeds N blocks" / etc.
    input_datasets: list[str]
    output_datasets: list[str]
    blast_radius: list[str]       # downstream dataset names affected if this block is wrong
    raw_sas_snippet: str          # first 10 lines of block source for "View code"

class MissingDependency(BaseModel):
    name: str
    referenced_in: str            # "main_pipeline.sas:14"
    dependency_type: Literal["file", "dataset"]

class CircularDependency(BaseModel):
    cycle: list[str]              # dataset names forming the cycle

class OutputCoverage(BaseModel):
    dataset_name: str
    structural_importance: Literal["low", "medium", "high"]
    has_reference: bool
    reference_filename: str | None
    row_count: int | None
    column_names: list[str]

class ConfigurationValue(BaseModel):
    name: str                     # "&YEAR"
    value: str                    # "2024"
    looks_dynamic: bool           # True for dates, env names, paths

class SensitiveDataFinding(BaseModel):
    pattern: str                  # "DOB"
    found_in: str                 # "customers.sas7bdat"

class PreviewStats(BaseModel):
    total_blocks: int
    needs_manual: int             # UNRECOGNIZED blocks
    best_effort: int              # PROC_UNKNOWN blocks
    review_recommended: int       # high importance, auto-translatable
    auto_converts: int            # low importance, auto-translatable
    macro_var_count: int
    macro_def_count: int
    estimated_minutes_low: int
    estimated_minutes_high: int   # derived: total_blocks × 45s ÷ 60, ±30%

class AnalyseResponse(BaseModel):
    input_hash: str               # SHA-256 of all SAS file contents — for localStorage keying
    filenames: list[str]
    input_sources: list[str]      # unique input datasets across all blocks
    output_datasets: list[str]    # terminal output datasets (not consumed by downstream blocks)
    stats: PreviewStats
    blocks: list[AssessedBlock]
    missing_dependencies: list[MissingDependency]
    circular_dependencies: list[CircularDependency]
    output_coverage: list[OutputCoverage]
    configuration_values: list[ConfigurationValue]
    sensitive_data_findings: list[SensitiveDataFinding]
    pipeline_description: str | None = None   # LLM-generated, absent on failure
    parser_warning: str | None = None
    llm_skipped: bool = False
```
- [ ] done

---

### S-D: `POST /analyse` route
**Files:** `src/backend/api/routes/analyse.py` (new), `src/backend/main.py` (register router)  
**Depends on:** S-C  
**Done when:** `POST /analyse` accepts the same multipart fields as `POST /migrate` (sas_files[], zip_file, ref_dataset, ref_csv), runs `SASParser().parse()` via `asyncio.to_thread()`, computes all `AnalyseResponse` fields, makes one lightweight LLM call for `pipeline_description`, and returns `AnalyseResponse`. Registered in `main.py` as `app.include_router(analyse.router)`.

**Implementation notes:**
- Import `SASParser` from `src.worker.engine.parser` — same pattern already used in `src/backend/api/routes/jobs.py`
- Wrap `SASParser().parse()` in `asyncio.to_thread()` to avoid blocking the event loop
- Structural importance algorithm:
  - Build dataset dependency graph from all blocks' `input_datasets` / `output_datasets`
  - `PROC_IMPORT` → HIGH (pipeline entry); `PROC_EXPORT` → HIGH (pipeline exit)
  - Terminal output (dataset not consumed by any downstream block) → HIGH
  - Fan-out ≥ 3 (dataset consumed by 3+ blocks) → HIGH
  - Fan-out 1–2 → MEDIUM
  - `PROC_PRINT`, `PROC_CONTENTS`, `PROC_DATASETS` → LOW
  - Isolated (no downstream) → LOW
- Blast radius: BFS forward from each blocking block's output datasets through the dependency graph; collect affected dataset names
- Missing dependencies: compare `%include` file references and `SET`/`MERGE`/`DATA=` dataset names against uploaded filenames and data file stems
- Circular dependencies: `networkx.find_cycle()` on the dataset dependency graph; catch `nx.NetworkXNoCycle` and return empty list
- Sensitive data: scan `.sas7bdat` column names via `pyreadstat.read_sas7bdat(..., metadataonly=True)` and `KEEP`/`DROP`/`VAR` column lists from `SASBlock`; match case-insensitively against: `SSN`, `SOCIAL_SECURITY`, `SIN`, `DOB`, `DATE_OF_BIRTH`, `BIRTH_DATE`, `PATIENT_ID`, `MEMBER_ID`, `BENEFICIARY_ID`, `NPI`, `ACCOUNT_NUM`, `ACCOUNT_NUMBER`, `ACCT_NO`, `CREDIT_CARD`, `CARD_NUMBER`, `PAN`, `EMAIL`, `EMAIL_ADDR`, `PHONE`, `PHONE_NUM`, `MOBILE`, `PASSPORT`, `PASSPORT_NUM`, `PASSWORD`, `PASSWD`
- Configuration value heuristic: `looks_dynamic=True` if value matches ISO date pattern, contains `PROD`/`DEV`/`UAT`/`TEST`/`STAGING`, looks like a file path (contains `/` or `\`), or is a 4-digit year ≥ current year
- Functional description mapping (rule-based, no LLM):
  - `DATA_STEP` → "Data transformation step"
  - `PROC_SQL` → "SQL query / join"
  - `PROC_IML` → "Matrix / statistical computation"
  - `PROC_FCMP` → "Custom function definition"
  - `PROC_SORT` → "Data sorting step"
  - `PROC_IMPORT` → "File ingestion step"
  - `PROC_EXPORT` → "File export step"
  - `PROC_MEANS` → "Statistical summary"
  - `PROC_FREQ` → "Frequency / cross-tabulation"
  - `PROC_TRANSPOSE` → "Data reshape / transpose"
  - `PROC_RANK` → "Ranking / quantile assignment"
  - `PROC_APPEND` → "Dataset append"
  - `PROC_UNKNOWN` → "Custom step (unrecognised type)"
  - `UNRECOGNIZED` → "Unrecognised construct — cannot auto-translate"
  - Others → "Processing step"
- LLM call: send filenames, all dataset names, block type counts, first 100 lines of the largest `.sas` file; prompt asks for 2–3 sentence plain-English pipeline description; wrap in try/except — on failure set `llm_skipped=True`, `pipeline_description=None`; use the same `LLM_MODEL` / `LLMClient` pattern as the worker
- Output coverage: for each terminal output dataset, find any uploaded reference file (CSV, sas7bdat) whose stem matches the dataset name; if found, read row count and column names via `pyreadstat` or `csv.DictReader`
- `input_hash`: SHA-256 of all SAS file content bytes (same algorithm as `POST /migrate`)
- Graceful degradation: parser exception → `parser_warning` set, return minimal response with `blocks=[]`; LLM exception → `llm_skipped=True`, continue
- [ ] done

---

### S-E: Extend `POST /migrate` to accept assessment fields
**File:** `src/backend/api/routes/migrate.py`  
**Depends on:** S-B, S-C  
**Done when:** handler accepts three new optional `Form` parameters — `notes: str | None = Form(default=None)`, `importance_overrides: str | None = Form(default=None)`, `assessment_json: str | None = Form(default=None)` — parses the two JSON strings with `json.loads()` (guarded), merges `importance_overrides` into the `assessment` dict, and writes both `job.notes` and `job.assessment` to the job row before commit. `MigrateResponse` is unchanged.

**Note:** `importance_overrides` is not stored as a separate column — it is embedded in the `assessment` JSON blob under the key `"importance_overrides"`. This avoids schema proliferation. Also fix pre-existing drift: remove `name?: string` from the TypeScript `MigrateResponse` interface (it is not returned by the backend).
- [ ] done

---

### S-F: Backend tests for `POST /analyse` and updated `POST /migrate`
**File:** `tests/test_analyse_route.py` (new)  
**Depends on:** S-D, S-E  
**Done when:** tests cover:
- `POST /analyse` with valid `.sas` files → 200, `AnalyseResponse` structure correct
- `POST /analyse` with a `.sas7bdat` containing a PII column name → `sensitive_data_findings` non-empty
- `POST /analyse` with missing `%include` reference → `missing_dependencies` non-empty
- `POST /analyse` with LLM mocked to raise → `llm_skipped=True`, 200 (not 500)
- `POST /analyse` with no SAS files → 400
- `POST /migrate` with `notes` and `assessment_json` → job row has `notes` and `assessment` set
- [ ] done

---

### S-G: Frontend TypeScript types
**File:** `src/frontend/src/api/types.ts`  
**Depends on:** S-C (contract defined)  
**Done when:** the following interfaces exist, matching the Pydantic schemas exactly (snake_case throughout):

```typescript
export interface AssessedBlock {
  block_id: string;
  source_file: string;
  start_line: number;
  end_line: number;
  block_type: string;
  functional_description: string;
  is_translatable: boolean;
  is_unknown_proc: boolean;
  structural_importance: "low" | "medium" | "high";
  importance_reason: string;
  input_datasets: string[];
  output_datasets: string[];
  blast_radius: string[];
  raw_sas_snippet: string;
}

export interface MissingDependency {
  name: string;
  referenced_in: string;
  dependency_type: "file" | "dataset";
}

export interface CircularDependency {
  cycle: string[];
}

export interface OutputCoverage {
  dataset_name: string;
  structural_importance: "low" | "medium" | "high";
  has_reference: boolean;
  reference_filename: string | null;
  row_count: number | null;
  column_names: string[];
}

export interface ConfigurationValue {
  name: string;
  value: string;
  looks_dynamic: boolean;
}

export interface SensitiveDataFinding {
  pattern: string;
  found_in: string;
}

export interface PreviewStats {
  total_blocks: number;
  needs_manual: number;
  best_effort: number;
  review_recommended: number;
  auto_converts: number;
  macro_var_count: number;
  macro_def_count: number;
  estimated_minutes_low: number;
  estimated_minutes_high: number;
}

export interface AnalyseResponse {
  input_hash: string;
  filenames: string[];
  input_sources: string[];
  output_datasets: string[];
  stats: PreviewStats;
  blocks: AssessedBlock[];
  missing_dependencies: MissingDependency[];
  circular_dependencies: CircularDependency[];
  output_coverage: OutputCoverage[];
  configuration_values: ConfigurationValue[];
  sensitive_data_findings: SensitiveDataFinding[];
  pipeline_description: string | null;
  parser_warning: string | null;
  llm_skipped: boolean;
}
```

Also fix pre-existing drift: remove `name?: string` from `MigrateResponse` interface.
- [ ] done

---

### S-H: Frontend API functions — `analyseMigration` and updated `submitMigration`
**File:** `src/frontend/src/api/migrate.ts`  
**Depends on:** S-G  
**Done when:**
- `analyseMigration(files: AnalyseInput): Promise<AnalyseResponse>` added — sends same multipart fields as `submitMigration` to `POST /analyse`
- `submitMigration` extended with optional `notes?: string`, `importanceOverrides?: Record<string, "low" | "medium" | "high">`, `assessmentSnapshot?: object` params; appends them to FormData before fetch

```typescript
export interface AnalyseInput {
  sasFiles: File[];
  refDataset?: File;
  zipFile?: File;
  refTargetPath?: string | null;
}
```
- [ ] done

---

### S-I: `MigrationPreviewPage` component
**File:** `src/frontend/src/pages/MigrationPreviewPage.tsx`  
**Depends on:** S-H  
**Done when:** full assessment page renders all seven sections from the final layout (see session journal). Specific requirements:

- Reads `location.state` on mount; if no files present, redirects to `/jobs` immediately
- Calls `analyseMigration` on mount; shows loading skeleton while pending
- `pipeline_description` section has `[Edit ✎]` — clicking opens an inline `<textarea>` replacing the paragraph; save updates local state; edited value is included in `assessmentSnapshot` on submission
- Per-block structural importance: dropdown (`low` / `medium` / `high`) pre-filled from `AssessedBlock.structural_importance`; changes written to `localStorage` under key `rosetta_importance_${input_hash}`; on mount, localStorage values override API values
- Four risk tiers rendered from `blocks`:
  - 🔴 `is_translatable === false` (UNRECOGNIZED) — shows blast radius tree and "View code" expandable
  - 🟡 `structural_importance === "high" && is_translatable && !is_unknown_proc`
  - 🔵 `is_unknown_proc === true`
  - ✅ remaining — collapsed by default, "Show N steps" toggle
- Acknowledgment checkboxes: one per blocking (🔴) block ("I understand [functional_description] in [source_file] cannot be converted automatically"); one for sensitive data if `sensitive_data_findings` non-empty; "Start Migration" button disabled until all required boxes checked
- On "Start Migration": builds `assessmentSnapshot` from current state (description, importance overrides from localStorage, acknowledgment texts + timestamp, `sensitive_data_confirmed`); calls `submitMigration` with all fields; on success navigates to `/jobs`
- `parser_warning` → shows amber banner at top of page
- `llm_skipped` → shows notice in the description section: "Summary unavailable — could not reach the translation model"
- Prior migration history: not in this feature — deferred (requires a `GET /jobs?input_hash=` query not currently exposed)
- Export PDF: not in this feature — deferred (requires a PDF generation library)
- [ ] done

---

### S-J: Add `/migrate/preview` route and upload dialog wiring
**Files:** `src/frontend/src/App.tsx`, `src/frontend/src/pages/JobsPage.tsx`  
**Depends on:** S-I  
**Done when:**
- `App.tsx`: `<Route path="/migrate/preview" element={<MigrationPreviewPage />} />` added alongside existing routes
- `JobsPage.tsx`: upload dialog's submit handler (`handleSubmit` or equivalent) navigates to `/migrate/preview` with `location.state = { sasFiles, zipFile, refDataset, refTargetPath, name }` instead of calling `submitMigration` directly; the dialog closes after navigation
- [ ] done

---

### S-K: `make test` exits 0, ruff and mypy pass
**Depends on:** S-A through S-J  
**Done when:** `make test` green, no ruff errors, no mypy errors.
- [ ] done

## API Contract Summary

```
POST /analyse
  Request:  multipart/form-data — same fields as POST /migrate
            (sas_files[], zip_file, ref_dataset, ref_csv, ref_target_path)
  Response: AnalyseResponse (200)
            400 if no SAS files provided
  Notes:    Stateless — no DB write. Degrades gracefully on LLM/parser failure.

POST /migrate (extended)
  New fields: notes (Form, optional string)
              importance_overrides (Form, optional JSON string)
              assessment_json (Form, optional JSON string)
  Response:   MigrateResponse — unchanged
  Notes:      importance_overrides embedded in assessment blob on job row.
```

## Deferred to follow-on features

- **Export PDF** — requires a PDF generation library; not in scope for F21
- **Prior migration history banner** — requires `GET /jobs?input_hash=` query endpoint; not currently exposed
- **Importance override persistence across sessions beyond localStorage** — localStorage is sufficient for F21; DB persistence can be added if enterprise requirements demand it
- **`JobStatusResponse` / `JobSummary` exposure of `notes` and `assessment`** — the columns are written in F21; surfacing them in the GET response is a separate UI concern

## Dependencies on other features

- None blocking. Uses existing `SASParser`, `LLMClient`, `pyreadstat`, and `networkx` — all already in the dependency tree.

## Out of scope for this feature

- Any LLM call beyond the single pipeline description summary
- Block-level confidence scores (those require the migration planner agent, which runs post-job)
- Lineage graph visualisation (pre-migration data is too sparse for the full `LineageGraph` component)
- PDF export
- Prior migration history banner
- Any changes to the worker pipeline
