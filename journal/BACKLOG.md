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
**Active plan:** `docs/plans/F0-phase1-scaffold.md`

- [x] S01: docker-compose.yml — 4-service revision → see `docs/plans/F0-phase1-scaffold.md`
- [x] S02: pyproject.toml — add SQLAlchemy async + Alembic + asyncpg → see `docs/plans/F0-phase1-scaffold.md`
- [x] S03: backend core — settings + logging → see `docs/plans/F0-phase1-scaffold.md`
- [x] S04: database layer — SQLAlchemy async engine + session factory → see `docs/plans/F0-phase1-scaffold.md`
- [x] S05: Alembic init + jobs table migration → see `docs/plans/F0-phase1-scaffold.md`
- [x] S06: SQLAlchemy Job model → see `docs/plans/F0-phase1-scaffold.md`
- [x] S07: backend API — request/response schemas → see `docs/plans/F0-phase1-scaffold.md`
- [x] S08: backend API — POST /migrate route → see `docs/plans/F0-phase1-scaffold.md`
- [x] S09: backend API — GET /jobs/{id} route → see `docs/plans/F0-phase1-scaffold.md`
- [x] S10: backend Dockerfile + FastAPI app entrypoint → see `docs/plans/F0-phase1-scaffold.md`
- [x] S11: ComputeBackend ABC → see `docs/plans/F0-phase1-scaffold.md`
- [x] S12: LocalBackend stub → see `docs/plans/F0-phase1-scaffold.md`
- [x] S13: BackendFactory → see `docs/plans/F0-phase1-scaffold.md`
- [x] S14: worker core — settings → see `docs/plans/F0-phase1-scaffold.md`
- [x] S15: worker poll loop → see `docs/plans/F0-phase1-scaffold.md`
- [x] S16: worker Dockerfile → see `docs/plans/F0-phase1-scaffold.md`
- [x] S17: frontend scaffold — Vite + React + TS + Tailwind + shadcn/ui → see `docs/plans/F0-phase1-scaffold.md`
- [x] S18: frontend Dockerfile → see `docs/plans/F0-phase1-scaffold.md`
- [x] S19: .env.example → see `docs/plans/F0-phase1-scaffold.md`
- [x] S20: smoke test — POST /migrate + GET /jobs/{id} → see `docs/plans/F0-phase1-scaffold.md`
- [x] S21: CI — fix graceful skip + add Alembic step → see `docs/plans/F0-phase1-scaffold.md`

**Remaining Phase 1 — active plan: `docs/plans/F1-pipeline-generation.md`**
- [x] F1 S00: add pydantic-ai dependency (`pyproject.toml`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S01: sample SAS files (`samples/`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S02: SASBlock + GeneratedBlock models (`src/worker/engine/models.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S03: SASParser — DATA step + PROC SQL extraction (`src/worker/engine/parser.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S04: parser unit tests (`tests/test_parser.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S05: LLMClient — Pydantic AI agent (`src/worker/engine/llm_client.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S06: CodeGenerator — assemble pipeline.py (`src/worker/engine/codegen.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S07: LocalBackend — full implementation (`src/worker/compute/local.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S08: ReconciliationService (`src/worker/validation/reconciliation.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S09: reconciliation pytest test — DATA step (`tests/reconciliation/test_data_step.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S10: Alembic migration — add llm_model column (`alembic/versions/002_add_llm_model.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S11: wire engine into worker poll loop (`src/worker/main.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S12: audit + download API schemas (`src/backend/api/schemas.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S13: audit endpoint `GET /jobs/{id}/audit` (`src/backend/api/routes/jobs.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S14: download endpoint `GET /jobs/{id}/download` (`src/backend/api/routes/jobs.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S15: API route tests — audit + download (`tests/test_api_routes.py`) → see `docs/plans/F1-pipeline-generation.md`
- [x] F1 S16: `make test` — full suite green, coverage ≥ 90% → see `docs/plans/F1-pipeline-generation.md`

---

## Phase 2 — Core Backend Extension
- [x] F2: PROC SORT parser + translation → see `docs/plans/F2-proc-sort.md`
- [x] F2: Macro variable (`%LET`) resolution → Python constants → see `docs/plans/F2-proc-sort.md`
- [x] Reconciliation tests: PROC SORT, macro variables → see `tests/reconciliation/test_proc_sort.py`
- [ ] F1: Macro definition + call expansion
- [ ] F3: Row-level hash diff check
- [ ] F4: SAS log ingestion — parse log structure
- [ ] F4: LLM call for runtime logic reconstruction from log
- [ ] F10: Artefact versioning — group jobs by input_hash, expose version history per migration
- [ ] F11: Plain-language documentation — LLM-generated business-readable summary per job
- [ ] F15: Record-level reconciliation — row-by-row diff with configurable keys and tolerances
- [ ] F18: Refine conversion action — re-submit job with previous output + reconciliation report as context

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
