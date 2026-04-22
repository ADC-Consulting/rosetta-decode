# F-backend-postmvp — Post-MVP Backend Extensions

**Status:** in-progress
**Branch:** feat/F-UI-postmvp
**Depends on:** F1-pipeline-generation, F-sas7bdat, F-LLM (all complete)

## Goal

Add the backend endpoints, DB columns, and worker steps required by the post-MVP UI features:
- SAS source exposure for Monaco DiffEditor (F7)
- Zip bulk upload with per-file manifest
- Lineage JSON extraction and endpoint (F5/F6)
- Plain-language LLM doc generation and endpoint (F11)
- Re-reconciliation-only pathway (F13)
- Refine action (F18)

## Subtasks

### No DB migration required

- [x] S-BE1 — `GET /jobs/{id}/sources` *(no migration)*
  - File: `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py`
  - New schema: `JobSourcesResponse(job_id: UUID, sources: dict[str, str])`
  - Reads `job.files`, excludes keys starting with `__` (internal sentinels)
  - Returns 404 if job not found, 200 with sources dict otherwise

- [x] S-BE2 — Zip bulk upload *(no migration)*
  - File: `src/backend/api/routes/migrate.py`, `src/backend/api/schemas.py`, `src/backend/core/config.py`
  - Add `zip_file: UploadFile | None = None` to `POST /migrate`; 400 if both `sas_files` and `zip_file` are supplied
  - Helper: `_unpack_zip(raw: bytes, upload_dir: str, job_id: str) -> ZipManifest`
  - Accepted inside zip: `.sas`, `.sas7bdat`, `.csv`, `.log`, `.xlsx`, `.xls`
    - `.sas` → `file_contents` dict (text decoded utf-8)
    - others → written to `upload_dir` as `{job_id}_{filename}`, stored as `__ref_{ext}_{filename}__` sentinel
    - unknown extension → added to `rejected` list (not a 400)
  - No file count limit inside zip
  - `max_zip_bytes: int = 524_288_000` in `BackendSettings`; reject zip > limit with 413
  - Extend `MigrateResponse`: add `accepted: list[str]`, `rejected: list[FileRejection]`
  - New schema: `FileRejection(filename: str, reason: str)`

### DB migration 002

Migration file: `alembic/versions/002_add_lineage_doc_columns.py`
Adds two nullable columns to `jobs` table: `lineage JSON`, `doc TEXT`

- [x] S-BE3 — Lineage extraction + endpoint
  - Worker file: `src/worker/engine/parser.py`
    - After `SASParser().parse(files)`, serialize `nx.DiGraph` into `JobLineageResponse` schema
    - Each `SASBlock` becomes a node: `id = f"{block.source_file}::{block.start_line}"`
    - `status` field: check `python_code` for `# SAS-UNTRANSLATABLE` → `"untranslatable"`; check reconciliation flags → `"manual_review"`; otherwise `"migrated"`
    - Edges: for each block B, for each `dataset` in `B.input_datasets`, find predecessor block P where `dataset` in `P.output_datasets`; edge `source=P.id, target=B.id, dataset=dataset, inferred=False`
    - Write serialized lineage to `job.lineage` after parse step
  - Backend files: `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py`
    - New schemas: `LineageNode`, `LineageEdge`, `JobLineageResponse`
    - `GET /jobs/{id}/lineage` → `JobLineageResponse`; 404 if not found, 202 if `job.lineage is None`

- [x] S-BE4 — Plain-language doc generation + endpoint
  - New file: `src/worker/engine/doc_generator.py`
    - `DocGenerator` class with `async def generate(job: Job, llm_client: LLMClient) -> str`
    - Prompt: SAS source + reconciliation report → LLM → structured Markdown summary
    - Called in worker after `ReconciliationService.run`; result stored in `job.doc`
  - Backend files: `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py`
    - New schema: `JobDocResponse(job_id: UUID, doc: str | None)`
    - `GET /jobs/{id}/doc` → `JobDocResponse`; 202 with `doc=None` if not yet generated

### DB migration 003

Migration file: `alembic/versions/003_add_skip_llm_parent.py`
Adds to `jobs` table: `skip_llm BOOLEAN DEFAULT FALSE`, `parent_job_id VARCHAR(36) NULL`

- [ ] S-BE5 — Re-reconciliation pathway
  - Backend files: `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py`
    - New schema: `UpdatePythonCodeRequest(python_code: str)`
    - `PUT /jobs/{id}/python_code` → updates `job.python_code`, sets `job.status = "queued"`, `job.skip_llm = True`, re-enqueues job
    - 404 if not found; 409 if job is currently `"running"`
  - Worker file: `src/worker/main.py`
    - Branch on `job.skip_llm`: if True, skip `SASParser` + `LLMClient`, use `job.python_code` directly, run `ReconciliationService` only

- [ ] S-BE6 — Refine action *(depends on S-BE5)*
  - Backend files: `src/backend/api/routes/jobs.py`, `src/backend/api/schemas.py`
    - New schema: `RefineRequest(hint: str | None = None)`, `RefineResponse(job_id: UUID)`
    - `POST /jobs/{id}/refine` → create new Job row; `files` copied from parent; `parent_job_id = str(job_id)`;
      enqueue with `prior_python_code` and `hint` stored in `files["__refine_context__"]` as JSON
    - Returns `RefineResponse`
  - Worker file: `src/worker/engine/llm_client.py`
    - `translate()` gains `prior_python_code: str | None = None`, `hint: str | None = None`
    - If present, prepended to LLM prompt as "Prior output to improve" context block

## Key constraints

- All new endpoints must have unit tests in `tests/backend/`
- Alembic migrations: use `server_default` for boolean columns to avoid backfill issues on existing rows
- Sentinel keys in `job.files` always start with `__` — source endpoint must strip these consistently
- `DocGenerator` must not crash worker if LLM call fails — catch exception, log warning, leave `job.doc = None`
- `skip_llm` pathway must produce a new reconciliation report (overwrite old `job.report`), not preserve it
- `POST /refine` must work even if original job has `status="failed"` (allows re-trying failed migrations)
