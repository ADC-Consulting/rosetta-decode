# Backlog

## Phase 0 — Foundation
- [x] Define user stories (`docs/user-stories.md`)
- [x] Define and expand features (`docs/features.md`)
- [x] Define MVP scope (`docs/mvp-scope.md`)
- [x] Document architecture (`docs/architecture.md`)
- [x] Document migration approaches (`docs/context/migration-approaches.md`)
- [x] Build SAS pattern catalog (`docs/context/sas-patterns.md`)
- [x] Write all skill SKILL.md files (session-start, session-end, plan-feature, feature-planner, backend-builder, frontend-builder, git-committer)
- [x] Update CLAUDE.md with skills table

---

## Phase 1 — Vertical Slice (MVP core, CLOUD=false)
- [x] Set up Python project: `pyproject.toml`, `ruff`, `mypy`, `pytest`, `uv`, `pydantic-ai`
- [x] Create `Makefile` with dev targets: `make test`, `make lint`, `make format`, `make check`, `make dev`
- [x] Set up `pre-commit`: `.pre-commit-config.yaml` with ruff-format, ruff-lint, mypy hooks; run `pre-commit install`
- [x] Add GitHub Actions CI pipeline with uv caching and future job stubs
- [ ] Fix CI: skip ruff/mypy/pytest gracefully when `src/` and `tests/` don't exist (CI auto-heals when folders are created)
- [ ] Revise `docker-compose.yml`: 4 services — postgres, backend, worker, frontend; shared `rosetta-net` network
- [ ] Scaffold `src/backend/` (Dockerfile, api/, db/, core/)
- [ ] Scaffold `src/worker/` (Dockerfile, engine/, validation/, compute/, core/)
- [ ] Scaffold `src/frontend/` (Dockerfile, Vite+React+TS+Tailwind+shadcn/ui)
- [ ] Add SQLAlchemy async setup + Alembic + asyncpg to `pyproject.toml`
- [ ] DB: `jobs` table Alembic migration (id, status, input_hash, files JSONB, python_code, report JSONB, error, timestamps)
- [ ] Define `ComputeBackend` abstract interface (`src/worker/compute/base.py`)
- [ ] Implement `LocalBackend` (pandas + DuckDB) (`src/worker/compute/local.py`)
- [ ] Implement `BackendFactory` — reads `CLOUD` from env, returns correct backend
- [ ] F1: SAS parser — extract DATA step + PROC SQL blocks from N SAS files, order by dependency (`src/worker/engine/parser.py`)
- [ ] F1: LLM client — Pydantic AI agent, model from `LLM_MODEL` env var, structured output (`src/worker/engine/llm_client.py`)
- [ ] F1: Code generator — assemble full pipeline file with `# SAS: <file>:<line>` provenance (`src/worker/engine/codegen.py`)
- [ ] F3: Reconciliation service — schema parity + row count + aggregate parity, runs inline in worker (`src/worker/validation/reconciliation.py`)
- [ ] Backend: `POST /migrate` — validate + persist files + insert job → `{ job_id }` (`src/backend/api/`)
- [ ] Backend: `GET /jobs/{id}` — read job row → `{ status, python_code?, report?, error? }`
- [ ] Worker: poll loop — pick queued jobs, run full pipeline, update job row
- [ ] F8: Audit traceability — expose `GET /jobs/{id}/audit` returning immutable record (input hashes, model, timestamps, reconciliation results)
- [ ] F9: Downloadable output — `GET /jobs/{id}/download` returns zip (pipeline.py + reconciliation_report.json + audit.json)
- [ ] Reconciliation test: DATA step → DataFrame (pytest, CLOUD=false)
- [ ] Sample SAS files in `samples/` + corresponding reference output CSVs

---

## Phase 2 — Core Backend Extension
- [ ] F1: PROC SORT parser + translation
- [ ] F1: Macro variable (`%LET`) resolution → Python constants
- [ ] F1: Macro definition + call expansion
- [ ] F3: Row-level hash diff check
- [ ] F4: SAS log ingestion — parse log structure
- [ ] F4: LLM call for runtime logic reconstruction from log
- [ ] F10: Artefact versioning — group jobs by input_hash, expose version history per migration
- [ ] F11: Plain-language documentation — LLM-generated business-readable summary per job
- [ ] F15: Record-level reconciliation — row-by-row diff with configurable keys and tolerances
- [ ] F18: Refine conversion action — re-submit job with previous output + reconciliation report as context
- [ ] Reconciliation tests: PROC SORT, macro variables

---

## Phase 3 — Frontend Features
- [ ] F2: Code Explanation Assistant page
- [ ] F7: Side-by-side SAS vs Python diff view
- [ ] F12: Auto-generated technical docs + lineage metadata (backend data layer for F5)
- [ ] F13: Editable generated code in UI (Monaco/CodeMirror editor, triggers re-reconciliation)
- [ ] F16: Migration tracking dashboard (jobs table aggregate view)
- [ ] F17: End-to-end ETL pipeline view (step-level node graph within a job)
- [ ] F5: Lineage visibility UI
- [ ] F6: Dependency graph visualization

---

## Phase 4 — Advanced Features + Cloud
- [ ] F14: Authentication & SSO (SAML/OIDC, JWT, RBAC)
- [ ] `DatabricksBackend` (PySpark) (`src/worker/compute/databricks.py`)
- [ ] End-to-end test: CLOUD=true, Databricks connection
