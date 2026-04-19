# Backlog

## Phase 0 — Foundation

- [X] Define user stories (`docs/user-stories.md`)
- [X] Define and expand features (`docs/features.md`)
- [X] Define MVP scope (`docs/mvp-scope.md`)
- [X] Document architecture (`docs/architecture.md`)
- [X] Document migration approaches (`docs/context/migration-approaches.md`)
- [X] Build SAS pattern catalog (`docs/context/sas-patterns.md`)
- [X] Write all skill SKILL.md files (session-start, session-end, plan-feature, feature-planner, backend-builder, frontend-builder, git-committer)
- [X] Update CLAUDE.md with skills table

---

## Phase 1 — Vertical Slice (MVP core, CLOUD=false)

**Active plan:** `docs/plans/F0-phase1-scaffold.md`

- [X] Set up Python project: `pyproject.toml`, `ruff`, `mypy`, `pytest`, `uv`, `pydantic-ai`
- [X] Create `Makefile` with dev targets: `make test`, `make lint`, `make format`, `make check`, `make dev`
- [X] Set up `pre-commit`: `.pre-commit-config.yaml` with ruff-format, ruff-lint, mypy hooks; run `pre-commit install`
- [X] Add GitHub Actions CI pipeline with uv caching and future job stubs
- [X] S01–S21: Docker / DB / Backend / Worker / Frontend scaffold → see `docs/plans/F0-phase1-scaffold.md`

**F1 — Pipeline generation** (`docs/plans/F1-pipeline-generation.md`)

- [X] F1 S00–S16: SASParser, LLMClient, CodeGenerator, ReconciliationService, API routes, full suite green

**Remaining MVP items**

- [X] F-LLM: Upgrade LLM system prompt + retry resilience + partial result accumulation (`feat/F-llm-resilience`)
- [X] F-sas7bdat: Wire `pyreadstat` into `LocalBackend` + `/migrate` upload + reconciliation routing (`feat/F-sas7bdat`)
- [X] F-UI: Upload & Results page — `.sas` / `.sas7bdat` / `.csv` / `.log` upload, job polling, results view, download (`feat/F-UI`)

---

## Phase 2 — Core Backend Extension (post-MVP)

**F1 extensions** (`docs/plans/F1-ext-proc-sort-macro.md`)

- [X] F1-ext: PROC SORT parser + translation → see `docs/plans/F1-ext-proc-sort-macro.md`
- [X] F1-ext: Macro variable (`%LET`) resolution → Python constants → see `docs/plans/F1-ext-proc-sort-macro.md`
- [X] Reconciliation tests: PROC SORT, macro variables → see `tests/reconciliation/test_proc_sort.py`

**Remaining Phase 2**

- [ ] F1-ext: Macro definition + call expansion (`%MACRO` / `%MEND`)
- [ ] F3-ext: Row-level hash diff check
- [ ] F4: SAS log ingestion — parse log structure
- [ ] F4: LLM call for runtime logic reconstruction from log
- [ ] F10: Artefact versioning — group jobs by input_hash, expose version history per migration
- [ ] F11: Plain-language documentation — LLM-generated business-readable summary per job → see `docs/plans/F-backend-postmvp.md` S-BE4
- [ ] F15: Record-level reconciliation — row-by-row diff with configurable keys and tolerances
- [ ] F18: Refine conversion action — re-submit with previous output + reconciliation report as context → see `docs/plans/F-backend-postmvp.md` S-BE6

**Post-MVP UI + Backend (active) — `docs/plans/F-UI-postmvp.md` + `docs/plans/F-backend-postmvp.md`**

- [X] F-backend-postmvp S-BE1: `GET /jobs/{id}/sources` endpoint (no migration)
- [X] F-backend-postmvp S-BE2: Zip bulk upload — `.sas`, `.sas7bdat`, `.csv`, `.log`, `.xlsx`, `.xls` (no migration)
- [X] F-backend-postmvp S-BE3: Lineage extraction + `GET /jobs/{id}/lineage` (migration 004)
- [X] F-backend-postmvp S-BE4: Doc generation + `GET /jobs/{id}/doc` (migration 004)
- [ ] F-backend-postmvp S-BE5: Re-reconciliation `PUT /jobs/{id}/python_code` + `skip_llm` (migration 003)
- [ ] F-backend-postmvp S-BE6: Refine action `POST /jobs/{id}/refine` + `parent_job_id` (migration 003)
- [X] F-UI-postmvp S-FE5/10/11: AppSidebar + routing + JobsPage refactor
- [X] F-UI-postmvp S-FE1: `MonacoDiffViewer` component (Monaco DiffEditor)
- [X] F-UI-postmvp S-FE2: `MonacoEditor` component (Monaco Editor)
- [X] F-UI-postmvp S-FE3: `TiptapEditor` component (rich text + code blocks)
- [X] F-UI-postmvp S-FE4: `LineageGraph` component (React Flow, colour-coded by status, hover-to-focus, undo/redo/reset toolbar, dagre LR layout)
- [X] F-UI-postmvp S-FE6: `JobDetailPage` (4 tabs: Comparison / Edit / Report / Lineage)
- [ ] F-UI-postmvp S-FE7: `GlobalLineagePage`
- [ ] F-UI-postmvp S-FE8: `DocsPage`
- [ ] F-UI-postmvp S-FE9: `ExplainPage` stub
- [X] F-UI-postmvp S-FE12: Upload UX — unified drop-zone (.sas/.sas7bdat/.zip/.log/.csv/.xls/.xlsx), manifest view
- [X] F-UI-postmvp S-FE13: API client extensions (types + jobs.ts + migrate.ts)
- [X] UI polish: sonner toast for all errors, human-friendly error copy
- [X] UI polish: jobs table row disabled/non-clickable for non-done status

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
