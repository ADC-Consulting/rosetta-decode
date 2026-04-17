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

**Remaining Phase 1 (after scaffold — F1/F3/F8/F9 logic):**
- [ ] F1: SAS parser — extract DATA step + PROC SQL blocks from N SAS files, order by dependency (`src/worker/engine/parser.py`)
- [ ] F1: LLM client — Pydantic AI agent, model from `LLM_MODEL` env var, structured output (`src/worker/engine/llm_client.py`)
- [ ] F1: Code generator — assemble full pipeline file with `# SAS: <file>:<line>` provenance (`src/worker/engine/codegen.py`)
- [ ] F3: Reconciliation service — schema parity + row count + aggregate parity, runs inline in worker (`src/worker/validation/reconciliation.py`)
- [ ] F8: Audit traceability — expose `GET /jobs/{id}/audit` returning immutable record
- [ ] F9: Downloadable output — `GET /jobs/{id}/download` returns zip
- [ ] Reconciliation test: DATA step → DataFrame (pytest, CLOUD=false)
- [x] Sample SAS files in `samples/` + corresponding reference output CSVs

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
