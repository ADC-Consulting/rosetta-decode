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

**Active plan:** `docs/plans/F0-phase1-scaffold.md`

- [x] Set up Python project: `pyproject.toml`, `ruff`, `mypy`, `pytest`, `uv`, `pydantic-ai`
- [x] Create `Makefile` with dev targets: `make test`, `make lint`, `make format`, `make check`, `make dev`
- [x] Set up `pre-commit`: `.pre-commit-config.yaml` with ruff-format, ruff-lint, mypy hooks; run `pre-commit install`
- [x] Add GitHub Actions CI pipeline with uv caching and future job stubs
- [x] S01–S21: Docker / DB / Backend / Worker / Frontend scaffold → see `docs/plans/F0-phase1-scaffold.md`

**F1 — Pipeline generation** (`docs/plans/F1-pipeline-generation.md`)
- [x] F1 S00–S16: SASParser, LLMClient, CodeGenerator, ReconciliationService, API routes, full suite green

**Remaining MVP items**
- [x] F-LLM: Upgrade LLM system prompt + retry resilience + partial result accumulation (`feat/F-llm-resilience`)
- [x] F-sas7bdat: Wire `pyreadstat` into `LocalBackend` + `/migrate` upload + reconciliation routing (`feat/F-sas7bdat`)
- [x] F-UI: Upload & Results page — `.sas` / `.sas7bdat` / `.csv` / `.log` upload, job polling, results view, download (`feat/F-UI`)

---

## Phase 2 — Core Backend Extension (post-MVP)

**F1 extensions** (`docs/plans/F1-ext-proc-sort-macro.md`)
- [x] F1-ext: PROC SORT parser + translation → see `docs/plans/F1-ext-proc-sort-macro.md`
- [x] F1-ext: Macro variable (`%LET`) resolution → Python constants → see `docs/plans/F1-ext-proc-sort-macro.md`
- [x] Reconciliation tests: PROC SORT, macro variables → see `tests/reconciliation/test_proc_sort.py`

**Remaining Phase 2**
- [ ] F1-ext: Macro definition + call expansion (`%MACRO` / `%MEND`)
- [ ] F3-ext: Row-level hash diff check
- [ ] F4: SAS log ingestion — parse log structure
- [ ] F4: LLM call for runtime logic reconstruction from log
- [ ] F10: Artefact versioning — group jobs by input_hash, expose version history per migration
- [ ] F11: Plain-language documentation — LLM-generated business-readable summary per job
- [ ] F15: Record-level reconciliation — row-by-row diff with configurable keys and tolerances
- [ ] F18: Refine conversion action — re-submit with previous output + reconciliation report as context

---

## Phase 3 — Frontend Features (post-MVP)
- [ ] F2: Code Explanation Assistant page (chat UI — explain SAS/Python snippets)
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
