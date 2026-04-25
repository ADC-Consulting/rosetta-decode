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
- [x] feat(lineage): extend LineageEnricherAgent with FileNode, FileEdge, PipelineStep, BlockStatus, LogLink; multi-level view toggle (Blocks/Files/Pipeline) in LineageGraph (`feat/S-lineage-enricher-pipeline-levels`)
- [x] F4: Graded confidence-aware translation + per-block refine loop + change history → see `docs/plans/F4-confidence-refine-history.md` (complete)
- [x] UX fix: overall confidence bar now uses average LLM `confidence_score` (not reconciliation ratio); `overall_confidence_score: float` added to `TrustReportResponse`; bar width reflects exact %
- [x] F-UI-postmvp S-FE7: `GlobalLineagePage` — Pipeline tab: migration multi-select + Connect → merged ReactFlow graph (`src/frontend/src/lib/lineage-merge.ts`); Datasets + Columns tabs stubbed/disabled (future)
- [x] F-UI-postmvp S-FE8: `DocsPage` — migration cards (proposed/accepted), confidence/risk badges, read-only file tree, TiptapEditor popup with Plain English / Technical tabs; Rationale tooltip removed; ReportTab always-visible grey header + Modify button for both tabs
- [x] F-UI-postmvp S-FE9: `ExplainPage` — full implementation: file upload Q&A + migration context Q&A, chat UI, migration panel, Monaco code blocks; backend POST /explain + POST /explain/job + GET /jobs?status= filter
- [x] UI polish: ExplainPage full-height layout fix; Upload page promoted to inline Dialog on JobsPage; "Upload" nav item removed
- [x] UI polish: BlockPlanTable — default groupBy=folder, chevron leftmost in group header, History icon (counter-clockwise clock), "Filter by" label, basename-only file names in rows
- [x] UI polish: View Code dialog in Plan table — SAS (left) + Python (right) panels, Edit/Lock/Save, Sun/Moon theme toggle, parallel data fetch with loading state
- [x] feat(backend): PATCH /jobs/{id}/blocks/{block_id}/python — human edit recorded as BlockRevision (creates rev 1 if none exists); unified diff stored
- [x] feat(backend): improved LLM guardrails in explain_agent.py (scope boundary, no hallucination, structured fallback)
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
- [x] fix(frontend): block API calls (refine/revisions/restore/python) — replace `encodeURIComponent` with `blockId.replace(/:/g, '%3A')` to preserve path separators for FastAPI `block_id:path`
- [x] fix(frontend): View Code dialog SAS panel — exact key lookup first, then fuzzy fallback; `language="sas"` + `beforeMount={registerSasLanguage}` restores syntax highlighting
- [x] fix(frontend): View Code dialog Python panel — falls back to `generatedFiles[*.py]` then `jobPythonCode` (no longer shows full concatenated output when no revision exists); `generatedFiles` prop wired JobDetailPage → PlanTab → BlockPlanTable
- [x] fix(frontend): save handler invalidates `["block-revisions"]` query so History popup reflects new revision immediately
- [x] UX: View Code dialog — SAS/Python SVG logos in panel headers; button order resequenced (theme → edit/lock → save)
- [x] UX: History button highlights with primary ring when a human edit exists for that block (`humanEditedBlocks` set updated on save)
- [x] UX: BlockRevisionDrawer replaced with Monaco DiffEditor (`MonacoDiffViewer`) — each revision shows `previousCode` (rev n-1) vs `python_code` (rev n) side-by-side; latest revision auto-expanded; older revisions collapsed
- [x] UX: RightSidebar — `subtitle` prop for per-item secondary text; `sidebarKey` prop for independent per-page collapse state
- [x] UX: GlobalLineagePage sidebar — job items show `status · date` subtitle; Connect button shows selected count, disabled when empty; helper text when nothing selected; `sidebarKey="lineage-sidebar-collapsed"`
- [x] UX: ExplainPage sidebar — job items show status subtitle; `sidebarKey="explain-sidebar-collapsed"`
- [x] fix(backend): PlainEnglishAgent system prompt — field name corrected from `"markdown"` to `"non_technical_doc"` to match Pydantic output model; contradictory bullet/prose rule removed
- [x] feat(backend): PlainEnglishAgent prompt restructured — 5 sections (Purpose, Source Data, How It Works, Outputs, Migration Status) with explicit bullet/numbered list formatting per section; token limit raised to 1800
- [x] feat(frontend): Plan tab full UX overhaul — single Card summary, inline metrics ribbon, 8-col table, rationale icon+popover, Pass/Fail badges, stat pill tooltips, shadcn primitives throughout
- [x] fix(frontend): View Code dialog alignment — unified full-width toolbar + matching panel headers; both Monaco editors start at identical vertical offset
- [x] fix(backend): confidence 100% bug for manual/skip/untranslatable blocks — StubGenerator + migration_planner now emit confidence_score=0.0/band=very_low for non-translated blocks
- [x] feat(explain): two chat modes (Migration Chat + SAS General), 3-layer LLM prompt composition, react-markdown renderer, session restore fix, mode tabs, sidebar polish — migration 013
- [x] feat(explain): mode×audience suggestion chips (4 sets), SAS General always-open input, send bug fix, Monaco syntax highlighting with language map, RightSidebar header slot
- [x] feat(frontend): SAS EG–style editor — Code|Log|Output sub-tab bar, LogView (NOTE/WARNING/ERROR coloring), OutputView (CSV data grid), block tree sidebar with expandable DATA/PROC nodes, Run ▶ button
- [x] feat(backend): GET /jobs/{id}/attachments + GET /jobs/{id}/attachments/{path_key} — list and stream non-SAS uploaded files by category (log/output/other)
- [x] feat(executor): new Python sandbox microservice (src/executor/, port 8001, subprocess + tempfile isolation); POST /execute endpoint; ReconciliationService logic self-contained
- [x] feat(backend): POST /jobs/{id}/execute — proxy endpoint to executor; block_id optional; 404/503/502 error handling
- [x] feat(worker): RemoteReconciliationService — delegates recon to executor over HTTP with graceful fallback; _reconcile_initial_blocks() sets per-block reconciliation_status after initial migration run
- [x] refactor(frontend): SAS Studio layout — persistent vertical split, bottom panel (Code|Log|Output|History tabs), Run ▶ first in toolbar, history moved to bottom panel tab
- [x] fix(executor): per-run temp file for result JSON (avoids concurrent-run collisions at /tmp/rosetta_result.json)
- [x] fix(frontend): stdout always shown even on error (logs up to crash point no longer dropped)
- [ ] chore: `make docker-build` needed — picks up migration 013, executor service, new worker context code (shared_context.py, data_files, libname_map), frontend changes; also resolves PATCH /blocks/{block_id}/python 404 in production
- [ ] UI bug (unresolved): TipTap toolbar cursor jumps to bottom after one keystroke — multiple fixes attempted, none confirmed working
- [ ] UI bug (unresolved): version card not highlighted after saving — race condition fix attempted (await invalidateQueries), not confirmed
- [ ] UI bug (unresolved): Editor tab version restore always shows original code — null sentinel + {} override fix attempted, not confirmed
- [ ] UI bug (unresolved): tab heights not filling available space — `calc(100vh - 160px)` applied to all four tabs, not confirmed working
- [ ] fix(backend): `translate_best_effort` strategy — add to migration planner prompt OR remove enum; currently dead (LLM never assigns it)
- [x] fix(backend): `manual_ingestion` StubGenerator — now emits `pd.read_csv(disk_path)` scaffold with `is_untranslatable=False`, `confidence_score=0.7`; block_plan strategy passed to router via `block_plan_map` in `_translate_blocks()`
- [ ] fix(backend): `auto_verified` trust report counter always 0 — `verified_confidence` never written; derive from `reconciliation_status == "pass" AND confidence in (high, medium)` instead
- [ ] fix(backend): `needs_attention` too strict — requires recon failure; widen to: strategy in manual/skip OR recon fail OR confidence in (low, very_low, unknown)
- [ ] fix(tests): coverage at 87%, below 88% threshold — add tests for `_sniff_file`, `_inject_data_file_nodes`, or `build_context_section`
- [x] feat(backend): folder-aware agent context — `DataFileInfo` + `data_files` + `libname_map` on `JobContext`; `_sniff_file()` helper; `build_context_section()` shared utility; all 4 agents prepend context section
- [x] feat(backend): DATA_FILE lineage nodes — `_inject_data_file_nodes()` appends DATA_FILE nodes + inferred edges linking blocks to real uploaded data files
- [x] feat(backend): macro file content in windowed prompts — `windowed_context()` includes `macros/` and `autoexec.sas` so translation agents see macro definitions
- [x] feat(backend): always-attempt instruction added to all 4 agents — agents must emit best-effort code, never empty stubs for translate/translate_with_review
- [x] fix(frontend): TipTap table rendering — named imports for Table/TableCell/TableHeader/TableRow; toolbar always visible (dimmed in readonly); table CSS styles added
- [x] feat(frontend): Report tab — VersionHistoryRail restored; always-visible header; Edit/Save inline buttons; Save Changes hidden from top bar in report tab
- [x] feat(frontend): Lineage DATA_FILE nodes — blue dashed border, extension badge, filename + column preview
- [x] feat(frontend): EditorTab explorer panel max width 50% (was 30%)
- [x] feat(frontend): EditorTab history tab — Latest badge, filename-only labels, click navigates Monaco to block start line
- [ ] verify: Log/Output tabs in EditorTab bottom panel — may still not load; user to confirm after `make docker-build`

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
