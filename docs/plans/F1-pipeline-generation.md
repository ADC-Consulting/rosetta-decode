# F1 — Automated SAS-to-Python Pipeline Generation

**Phase:** 1
**Area:** Backend / Worker
**Status:** complete

## Goal

Implement the end-to-end migration engine inside the worker service: parse SAS source files into typed blocks, send each block to a hosted LLM via Pydantic AI for translation, assemble the translated blocks into a single runnable Python file with provenance comments, run reconciliation (schema parity + row count + aggregate parity), and persist the result to the `jobs` table. Done when uploading real SAS files produces a downloadable, locally-executable Python pipeline that passes reconciliation.

## Key Findings (pre-plan audit)

- `lark`, `sqlparse`, `jinja2`, `networkx` are **already in `pyproject.toml`** — no new deps needed for parser/codegen.
- `pydantic-ai` is **NOT** in `pyproject.toml` — only `anthropic>=0.25`. Must add `pydantic-ai[anthropic]` in S00.
- `llm_model` column does **not** exist on `jobs` table or ORM model — S10 Alembic migration is required.
- `LocalBackend.run_sql` stub has a stale comment referencing DuckDB; implementation must use pandas (decisions log locked in PostgreSQL/pandas only — no DuckDB).
- Routes are split: `src/backend/api/routes/jobs.py` and `routes/migrate.py` — audit/download endpoints go in `routes/jobs.py`.
- `networkx` already declared — use it for multi-file dependency ordering in parser.
- ORM `Job.id` stored as `String(36)` for SQLite compat; Alembic migration uses native PostgreSQL UUID.

## Acceptance Criteria

- [ ] `pydantic-ai[anthropic]` added to `pyproject.toml` dependencies
- [ ] `SASParser` extracts DATA step and PROC SQL blocks from one or more `.sas` files, ordered by dependency
- [ ] Untranslatable constructs preserved as `# SAS-UNTRANSLATABLE: <reason>` — never silently dropped
- [ ] Every generated line group carries `# SAS: <filename>:<line>` provenance
- [ ] `LLMClient.translate` returns structured `GeneratedBlock` via Pydantic AI agent; model from `LLM_MODEL`
- [ ] `CodeGenerator.assemble` produces full `pipeline.py`; no pandas-only idioms; uses Jinja2 templates
- [ ] `LocalBackend` methods fully implemented (read_csv, run_sql via pandas, write_parquet)
- [ ] `ReconciliationService.run` executes schema parity, row count, and aggregate parity; returns structured report
- [ ] Worker poll loop calls engine end-to-end; updates job to `done` with `python_code` + `report`
- [ ] `llm_model` column added to `jobs` table via Alembic migration
- [ ] `GET /jobs/{id}/audit` returns immutable audit record (404 if not found)
- [ ] `GET /jobs/{id}/download` returns zip with `pipeline.py`, `reconciliation_report.json`, `audit.json`
- [ ] At least one reconciliation pytest test passes (DATA step → pandas DataFrame, `@pytest.mark.reconciliation`)
- [ ] Sample SAS files in `samples/` with reference CSV
- [ ] `make test` exits 0; ruff and mypy pass; coverage ≥ 90% (`fail_under = 90` in `pyproject.toml`)

## Subtasks

### S00: add pydantic-ai dependency
**File:** `pyproject.toml`
**Depends on:** none
**Done when:** `pydantic-ai[anthropic]>=0.0.36` is in `[project.dependencies]` and `uv.lock` is updated
- [x] done

### S01: sample SAS files
**File:** `samples/basic_etl.sas`, `samples/basic_etl_ref.csv`
**Depends on:** none
**Done when:** one `.sas` file (DATA step + PROC SQL, no macros) and a matching reference CSV exist in `samples/`
- [x] done

### S02: SASBlock + GeneratedBlock models
**File:** `src/worker/engine/models.py`
**Depends on:** none
**Done when:** `SASBlock` and `GeneratedBlock` Pydantic models defined with all fields needed by parser, LLM client, and codegen (block type, source file, start/end line, raw SAS text, translated code, untranslatable flag)
- [x] done

### S03: SASParser — DATA step + PROC SQL extraction
**File:** `src/worker/engine/parser.py`
**Depends on:** S02
**Done when:** `SASParser.parse(files: dict[str, str]) -> list[SASBlock]` extracts and dependency-orders DATA step and PROC SQL blocks across multiple files using `networkx`; untranslatable constructs flagged inline as `# SAS-UNTRANSLATABLE: <reason>`
- [x] done

### S04: parser unit tests
**File:** `tests/test_parser.py`
**Depends on:** S03, S01
**Done when:** tests cover DATA step extraction, PROC SQL extraction, multi-file input, dependency ordering, and untranslatable construct flagging; all pass via `make test`
- [x] done

### S05: LLMClient — Pydantic AI agent
**File:** `src/worker/engine/llm_client.py`
**Depends on:** S00, S02
**Done when:** `LLMClient.translate(block: SASBlock) -> GeneratedBlock` uses a Pydantic AI agent with `result_type=GeneratedBlock`; model string from `LLM_MODEL` env var; structured output includes translated code and provenance metadata
- [x] done

### S06: CodeGenerator — assemble pipeline.py
**File:** `src/worker/engine/codegen.py`
**Depends on:** S02, S05
**Done when:** `CodeGenerator.assemble(blocks: list[GeneratedBlock]) -> str` produces a complete Python file using Jinja2; every line group has `# SAS: <file>:<line>`; untranslatable blocks rendered as `# SAS-UNTRANSLATABLE: <reason>`; no pandas-specific idioms
- [x] done

### S07: LocalBackend — full implementation
**File:** `src/worker/compute/local.py`
**Depends on:** none
**Done when:** `read_csv` (pandas), `run_sql` (pandas + `pandasql` or equivalent), `write_parquet` (pyarrow), `to_pandas` are fully implemented; stale DuckDB reference removed from docstring
- [x] done

### S08: ReconciliationService
**File:** `src/worker/validation/reconciliation.py`
**Depends on:** S06, S07
**Done when:** `ReconciliationService.run(ref_csv_path: str, python_code: str, backend: ComputeBackend) -> dict` executes schema parity, row count, and aggregate parity checks; returns `{ "checks": [{ "name", "status", "detail?" }] }` matching the API `report` JSONB schema
- [x] done

### S09: reconciliation pytest test — DATA step
**File:** `tests/reconciliation/test_data_step.py`
**Depends on:** S08, S01
**Done when:** test generates code from `samples/basic_etl.sas`, runs it against `samples/basic_etl_ref.csv` via `LocalBackend`, asserts all three reconciliation checks pass; marked `@pytest.mark.reconciliation`
- [x] done

### S10: Alembic migration — add llm_model column
**File:** `alembic/versions/002_add_llm_model.py`
**Depends on:** none
**Done when:** migration adds nullable `llm_model TEXT` column to `jobs` table; `Job` ORM model updated with `llm_model: Mapped[str | None]`
- [x] done

### S11: wire engine into worker poll loop
**File:** `src/worker/main.py`
**Depends on:** S03, S05, S06, S08, S10
**Done when:** `_process_job` calls `SASParser → LLMClient → CodeGenerator → ReconciliationService` in order; persists `python_code`, `report`, `llm_model` to job row; sets `status=done` (or `status=failed` with `error` on exception); `NotImplementedError` stub removed
- [x] done

### S12: audit + download API schemas
**File:** `src/backend/api/schemas.py`
**Depends on:** S10
**Done when:** `AuditResponse` and `DownloadResponse` (or equivalent) Pydantic models added to schemas; existing schemas unchanged
- [x] done

### S13: audit endpoint
**File:** `src/backend/api/routes/jobs.py`
**Depends on:** S12
**Done when:** `GET /jobs/{id}/audit` route added; returns `AuditResponse` with `id`, `input_hash`, `llm_model`, `created_at`, `updated_at`, `report`; 404 if job not found
- [x] done

### S14: download endpoint
**File:** `src/backend/api/routes/jobs.py`
**Depends on:** S13, S11
**Done when:** `GET /jobs/{id}/download` route returns a `StreamingResponse` zip containing `pipeline.py`, `reconciliation_report.json`, `audit.json`; zip filename is `rosetta-{job_id}.zip`; 404 if not found, 409 if job not done
- [x] done

### S15: API route tests — audit + download
**File:** `tests/test_api_routes.py`
**Depends on:** S13, S14
**Done when:** tests cover audit endpoint (happy path + 404) and download endpoint (zip contents verified + 404 + 409); all pass via `make test`
- [x] done

### S16: make test — full suite green + raise coverage to 90%
**File:** `pyproject.toml`
**Depends on:** S04, S09, S11, S15
**Done when:** `fail_under` raised from 40 to 90 in `[tool.coverage.report]`; `make test` exits 0 with no ruff or mypy errors
- [x] done

## Dependencies on other features

- F0 (done) — `jobs` table, `ComputeBackend` ABC, `BackendFactory`, worker poll loop scaffold all exist

## Out of scope for this feature

- Macro definitions, macro calls, `%LET` variable resolution (Phase 2)
- PROC SORT (Phase 2)
- Row-level hash diff (Phase 2 — F15)
- `DatabricksBackend` activation (Phase 4)
- Frontend upload UI / results page (Phase 3)
- F10 artefact versioning
