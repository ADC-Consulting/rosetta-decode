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

**F2-improvements — Agentic pipeline overhaul (`docs/plans/F2-agentic-workflow-improvements.md`)**

- [x] S-A: Enrich models (BlockPlan, MigrationPlan, EnrichedLineage, confidence on GeneratedBlock)
- [x] S-B: MigrationPlannerAgent
- [x] S-C: LineageEnricherAgent
- [x] S-D: Improved system prompts for all 6 existing agents
- [x] S-E: _SimpleCopyHelper — bypass LLM for trivial SET+KEEP/DROP DATA steps
- [x] S-F: Two-phase refinement loop (replace while loop)
- [x] S-G: Wire new agents into JobOrchestrator._execute()
- [x] S-H: CodeGenerator multi-file output (dict[str, str])
- [x] S-I: DB columns: migration_plan + generated_files (Alembic migration)
- [x] S-J: API schemas + GET /jobs/{id}/plan route
- [x] S-K: Frontend types + getJobPlan API function
- [x] S-L: PlanTab component + tab reorder (Plan first)
- [x] S-M: Editor 1:1 SAS↔Python comparison (generated_files per-file view)
- [x] S-N: LineageGraph edge column-count labels
- [x] S-O: Unit tests for 2 new agents
- [x] S-P: agents/__init__.py exports
- [x] S-Q: make test + ruff + mypy full pass

**Post-MVP UI + Backend (active) — `docs/plans/F-UI-postmvp.md` + `docs/plans/F-backend-postmvp.md`**

- [X] F-backend-postmvp S-BE1: `GET /jobs/{id}/sources` endpoint (no migration)
- [X] F-backend-postmvp S-BE2: Zip bulk upload — `.sas`, `.sas7bdat`, `.csv`, `.log`, `.xlsx`, `.xls` (no migration)
- [X] F-backend-postmvp S-BE3: Lineage extraction + `GET /jobs/{id}/lineage` (migration 004)
- [X] F-backend-postmvp S-BE4: Doc generation + `GET /jobs/{id}/doc` (migration 004)
- [X] F-backend-postmvp S-BE5: Re-reconciliation `PUT /jobs/{id}/python_code` + `skip_llm` (migration 009)
- [X] F-backend-postmvp S-BE6: Refine action `POST /jobs/{id}/refine` + `parent_job_id` (migration 009)
- [X] F-UI-postmvp S-FE5/10/11: AppSidebar + routing + JobsPage refactor
- [X] F-UI-postmvp S-FE1: `MonacoDiffViewer` component (Monaco DiffEditor)
- [X] F-UI-postmvp S-FE2: `MonacoEditor` component (Monaco Editor)
- [X] F-UI-postmvp S-FE3: `TiptapEditor` component (rich text + code blocks)
- [X] F-UI-postmvp S-FE4: `LineageGraph` component (React Flow, colour-coded by status, hover-to-focus, undo/redo/reset toolbar, dagre LR layout)
- [X] F-UI-postmvp S-FE6: `JobDetailPage` (5 tabs: Plan / Editor / Report / Lineage / History)
- [X] F-UI-postmvp History tab: version timeline with agent/human icons, click-to-navigate
- [x] F5 S-13: `make test` pass + delete `src/frontend/@/` artefact + commit gate → see `docs/plans/F5-tab-versions.md`
- [ ] F-UI-postmvp S-FE7: `GlobalLineagePage`
- [ ] F-UI-postmvp S-FE8: `DocsPage`
- [ ] F-UI-postmvp S-FE9: `ExplainPage` stub
- [X] F-UI-postmvp S-FE12: Upload UX — unified drop-zone (.sas/.sas7bdat/.zip/.log/.csv/.xls/.xlsx), manifest view
- [X] F-UI-postmvp S-FE13: API client extensions (types + jobs.ts + migrate.ts)
- [X] UI polish: sonner toast for all errors, human-friendly error copy
- [X] UI polish: jobs table row disabled/non-clickable for non-done status
- [X] UI polish: TipTap text size fix, Report tab side-by-side layout
- [X] UI polish: LineageGraph node background light, lucide icon on Reset button
- [X] fix(backend): preserve zip directory structure in file tree (path as key, not basename)
- [X] UI polish: JobDetailPage header — name+status centered and larger, buttons inline with tab bar, standalone Save button removed
- [X] UI polish: Monaco editors use `defaultValue` + stable `key` + `pythonEditorRef` (fixes cursor repositioning root cause)
- [X] refactor(frontend): split JobDetailPage monolith into `src/components/JobDetail/` components; `constants.tsx` → `constants.ts` + `StatusBadge.tsx` to fix Vite HMR 404
- [X] fix(frontend): remove `asChild` from Base UI `TooltipTrigger` in EditorTab (nested button hydration error)
- [X] fix(frontend): `NODE_TYPES`/`EDGE_TYPES` module-scope constants in LineageGraph (React Flow warning #002)
- [X] fix(frontend): remove all `console.log` debug calls from VersionHistoryRail
- [ ] UI bug (unresolved): TipTap toolbar cursor jumps to bottom after one keystroke — multiple fixes attempted, none confirmed working
- [ ] UI bug (unresolved): version card not highlighted after saving — race condition fix attempted (await invalidateQueries), not confirmed
- [ ] UI bug (unresolved): Editor tab version restore always shows original code — null sentinel + {} override fix attempted, not confirmed
- [ ] UI bug (unresolved): tab heights not filling available space — `calc(100vh - 160px)` applied to all four tabs, not confirmed working

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
