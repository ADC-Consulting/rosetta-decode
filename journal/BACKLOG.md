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
- [ ] Fix CI: skip ruff/mypy/pytest gracefully when `src/` and `tests/` don't exist (interrupted)
- [ ] Define `ComputeBackend` abstract interface (`src/backend/compute/base.py`)
- [ ] Implement `LocalBackend` (pandas + DuckDB) (`src/backend/compute/local.py`)
- [ ] Implement `BackendFactory` — reads `CLOUD` from env, returns correct backend
- [ ] F1: SAS parser — extract DATA step blocks from a single SAS file
- [ ] F1: LLM client — call hosted API with SAS block + pattern context, return Python
- [ ] F1: Code generator — assemble full pipeline file with provenance comments
- [ ] F1: FastAPI endpoint `POST /migrate` — accepts SAS file, returns generated Python
- [ ] F3: Reconciliation service — schema parity + row count + aggregate parity checks
- [ ] F3: FastAPI endpoint `POST /reconcile` — accepts SAS CSV + Python output, returns report
- [ ] Reconciliation test: DATA step → DataFrame (pytest, CLOUD=false)
- [ ] Sample SAS script in `samples/` + corresponding SAS output CSV

---

## Phase 2 — Core Backend Extension
- [ ] F1: PROC SQL parser + translation
- [ ] F1: PROC SORT parser + translation
- [ ] F1: Macro variable (`%LET`) resolution → Python constants
- [ ] F3: Row-level hash diff check
- [ ] F4: SAS log ingestion — parse log structure
- [ ] F4: LLM call for runtime logic reconstruction from log
- [ ] Reconciliation tests: PROC SQL, PROC SORT, macro variables

---

## Phase 3 — Frontend Shell
- [ ] Set up frontend project: Vite + React + TypeScript + Tailwind + shadcn/ui
- [ ] API client layer (`src/frontend/src/api/`)
- [ ] F2: Code Explanation Assistant page
- [ ] F7: Side-by-side SAS vs Python diff view

---

## Phase 4 — Advanced Features + Cloud
- [ ] F5: Lineage visibility UI
- [ ] F6: Dependency graph visualization
- [ ] `DatabricksBackend` (PySpark) (`src/backend/compute/databricks.py`)
- [ ] End-to-end test: CLOUD=true, Databricks connection
- [ ] Multi-file SAS input with dependency resolution
