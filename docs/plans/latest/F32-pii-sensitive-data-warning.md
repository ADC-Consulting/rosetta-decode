# F32 — PII / Sensitive Data Warning on Plan Tab

**Phase:** 2
**Area:** Both (Backend / Worker + Frontend)
**Status:** in-progress
**GitHub issue:** #62

## Goal

Detect column names and SAS variable references that suggest personal data using word-boundary pattern matching — no LLM call. Store findings on the job, expose via the plan API, and render a warning banner on the Plan tab before the user accepts. Critical for regulated clients (pharma, finance, insurance) who must know that a migration pipeline processes PII.

## Acceptance Criteria

- [ ] `SensitiveDataFinding` typed model defined in `models.py`
- [ ] PII scanner uses word-boundary matching (not substring) to minimise false positives
- [ ] `source_type` field distinguishes "file" (data file column) from "block" (SAS source hint)
- [ ] Unit tests for `scan_for_pii()` with PII-positive and PII-negative column names
- [ ] `sensitive_data_findings` stored on `MigrationPlan` and surfaced via `GET /jobs/{id}/plan`
- [ ] Plan tab shows warning banner when findings are non-empty
- [ ] `make test` exits 0

## Subtasks

### S-A: Define SensitiveDataFinding typed model
**File:** `src/worker/engine/models.py`
**Depends on:** none
**Done when:** A `SensitiveDataFinding` Pydantic model is defined with fields `column: str`, `matched_signal: str`, `source_type: Literal["file", "block"]`, `source: str` (file path or block_id respectively); and `MigrationPlan` has `sensitive_data_findings: list[SensitiveDataFinding] = Field(default_factory=list)`
- [ ] done

### S-B: Create PII scanner with word-boundary matching
**File:** `src/worker/engine/pii_scanner.py` (new file)
**Depends on:** S-A
**Done when:** A function `scan_for_pii(blocks: list[SASBlock], data_files: dict[str, DataFileInfo]) -> list[SensitiveDataFinding]` is implemented; column names sourced from: (1) `data_files[path].columns` for uploaded data files, (2) SAS block hint fields (`var_cols`, `class_vars`, `by_vars`, `table_vars`, `id_cols`, `rank_cols`, `keep_cols`, `drop_cols`) for SAS source blocks; matching uses **word-boundary splitting**: column name is split on `_`, spaces, and CamelCase boundaries then matched token-by-token against the signal list (e.g. `SOCIAL_SECURITY_NUMBER` → tokens `[social, security, number]`; `DateOfBirth` → tokens `[date, of, birth]`) — this prevents `TOPZIP` matching `zip` or `DOBERMAN` matching `dob`; signal list covers common PII patterns relevant to European financial/pharma/insurance clients: `ssn`, `social_security`, `nin`, `national_id`, `cpr`, `personnummer`, `cvr`, `passport`, `dob`, `birth_date`, `birthdate`, `date_of_birth`, `age`, `email`, `phone`, `mobile`, `address`, `street`, `postcode`, `zip`, `ip`, `credit_card`, `iban`, `account_number`, `bank_account`, `tax_id`, `bsn`, `nino`, `pps`; findings deduplicated by `(column, matched_signal, source)` triple; unit tests cover: obvious PII column matches, non-PII false-positive candidates (`topzip`, `doberman`, `phone_confirmed`, `address_flag`), CamelCase splitting, underscore splitting, data file source vs block source labelling
- [ ] done

### S-C: Call PII scanner in worker pipeline
**File:** `src/worker/main.py`
**Depends on:** S-A, S-B
**Done when:** `scan_for_pii(parse_result.blocks, context.data_files)` is called after the data_file assembly step (when `context.data_files` is populated) AND after `MigrationPlannerAgent` has constructed the plan; result assigned to `context.migration_plan.sensitive_data_findings` before `job.migration_plan` is persisted; skipped gracefully if `context.migration_plan` is None
- [ ] done

### S-D: Add sensitive_data_findings to JobPlanResponse API schema
**File:** `src/backend/api/schemas.py`
**Depends on:** S-A
**Done when:** `JobPlanResponse` has `sensitive_data_findings: list[SensitiveDataFinding] = []`; `SensitiveDataFinding` duplicated as a matching Pydantic model in `schemas.py` (avoid cross-service import)
- [ ] done

### S-E: Update JobPlanResponse TypeScript type
**File:** `src/frontend/src/api/types.ts`
**Depends on:** S-D
**Done when:** `JobPlanResponse` interface has `sensitive_data_findings?: Array<{column: string; matched_signal: string; source_type: "file" | "block"; source: string}>`
- [ ] done

### S-F: Render PII warning banner on Plan tab
**File:** `src/frontend/src/components/JobDetail/PlanTab.tsx`
**Depends on:** S-E
**Done when:** A red-bordered warning banner renders above the verdict strip when `planData.sensitive_data_findings` is non-empty; shows unique matched signal names as a comma-separated list (e.g. "email, dob, ssn") with total affected column count; distinguishes data file sources from SAS source hints in the detail; hidden when list is empty
- [ ] done

### S-G: make test exits 0
**Depends on:** S-A through S-F
**Done when:** All 7 gates green; unit tests for `scan_for_pii()` passing including false-positive regression cases
- [ ] done

## Known limitation

Existing jobs in the database will not have `sensitive_data_findings` populated. Only jobs processed after this feature ships will have the data. PII detection is heuristic — it will miss non-standard column naming conventions and may produce occasional false positives despite word-boundary matching.

## Dependencies on other features

- Merge after F30 and F31 (all share `models.py`, `schemas.py`, `types.ts`)

## Out of scope

- LLM-based PII detection
- Per-column remediation guidance
- Alembic migration (stored in existing `job.migration_plan` JSON column)
