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
- [x] chore: `make docker-build` needed — picks up executor log4j2 Spark warning suppression, executor volume mount, backend trigger fix, generated_files sync, agent router changes (still need one more build for today's fixes)
- [x] fix(backend): output variable NameError — root cause was (1) block topo sort placing PROC_IML before its producer, (2) GenericProcAgent prompt using wrong `libname_table` form for inter-block inputs; fixed via Kahn's sort tiebreaker + prompt/renamer fixes across all agents
- [ ] UI bug (unresolved): TipTap toolbar cursor jumps to bottom after one keystroke — multiple fixes attempted, none confirmed working
- [ ] UI bug (unresolved): tab heights not filling available space — `calc(100vh - 160px)` applied to all four tabs, not confirmed working
- [ ] fix(backend): `translate_best_effort` strategy — add to migration planner prompt OR remove enum; currently dead (LLM never assigns it)
- [x] fix(backend): `manual_ingestion` StubGenerator — now emits `pd.read_csv(disk_path)` scaffold with `is_untranslatable=False`, `confidence_score=0.7`; block_plan strategy passed to router via `block_plan_map` in `_translate_blocks()`
- [x] fix(executor): data_dir routing — uploaded files saved to `/uploads/<job_id>/<basename>`; executor rewrites `/workspace/data/` → `data_dir/` at run time; `data_dir` threaded through all recon call sites
- [x] fix(executor): xlsx support — openpyxl added to Dockerfile; `_fix_excel_spark_reads()` guard rewrites bad Spark xlsx reads; prompt updated with pandas bridge pattern
- [x] fix(backend): PROC IMPORT output_var naming — removed `_file_io_types` exclusion from `all_block_outputs`; `normalise_output_var` + `normalise_output_var_in_code` shared utilities in `agents/shared.py`
- [x] fix(backend): file_count off-by-one — counts per-path `__ref_*__` sentinels; excludes canonical aliases and `__refine_context__`
- [ ] refactor(backend): consolidate job statuses — backend statuses (queued/running/proposed/under_review/accepted/done/failed) should be reduced; proposed and under_review are internal pipeline concepts that leak into the UI; frontend currently maps them to "Processing" and "Needs Review" as a workaround; backend statuses should be simplified when safe to do so without breaking DB queries or worker logic
- [ ] fix(backend): `auto_verified` trust report counter always 0 — derive from `reconciliation_status == "pass" AND confidence in (high, medium)` instead
- [ ] fix(backend): `needs_attention` too strict — widen to: strategy in manual/skip OR recon fail OR confidence in (low, very_low, unknown)
- [x] fix(tests): coverage raised from 86% → 95% — comprehensive test additions across all agent factories, router, reconciliation, worker/main, jobs routes, explain routes, codegen, macro_expander
- [x] feat(backend): folder-aware agent context — `DataFileInfo` + `data_files` + `libname_map` on `JobContext`; `_sniff_file()` helper; `build_context_section()` shared utility; all 4 agents prepend context section
- [x] UX: history pane ordering — v1 at top, descending to latest; "Latest" badge on last entry (`VersionHistoryRail` + `EditorTab`)
- [x] UX: Plan tab block table collapsed by default; chevron toggle on "Blocks" heading
- [x] UX: Rationale column merged into Actions as Info icon (tooltip + popover)
- [x] fix: saveBlockPython invalidates `["job", jobId, "versions"]` so new saves appear in history rail immediately
- [x] UX: UploadPage navigates directly to /jobs on submit success; Phase 2 result card removed
- [x] feat(backend): DATA_FILE lineage nodes — `_inject_data_file_nodes()` appends DATA_FILE nodes + inferred edges linking blocks to real uploaded data files
- [x] feat(backend): macro file content in windowed prompts — `windowed_context()` includes `macros/` and `autoexec.sas` so translation agents see macro definitions
- [x] feat(backend): always-attempt instruction added to all 4 agents — agents must emit best-effort code, never empty stubs for translate/translate_with_review
- [x] fix(frontend): TipTap table rendering — named imports for Table/TableCell/TableHeader/TableRow; toolbar always visible (dimmed in readonly); table CSS styles added
- [x] feat(frontend): Report tab — VersionHistoryRail restored; always-visible header; Edit/Save inline buttons; Save Changes hidden from top bar in report tab
- [x] feat(frontend): Lineage DATA_FILE nodes — blue dashed border, extension badge, filename + column preview
- [x] feat(frontend): EditorTab explorer panel max width 50% (was 30%)
- [x] feat(frontend): EditorTab history tab — v{n} version labels; clicking loads block's Python revision via model.setValue(); no longer changes selected SAS file; theme-aware highlight
- [x] feat(frontend): full-page editor — EditorFullPage at /jobs/:id/editor; Maximize2/Minimize2 toggle; URL ?tab= routing on return
- [x] feat(frontend): inline/side-by-side diff toggle in BlockRevisionModal — segmented button, inline default
- [x] feat(frontend): Plan summary card — text full-width top, stats centered bottom, py-2 compact padding
- [x] feat(frontend): block table groupBy defaults to "file"
- [x] feat(frontend): save hash guard — skips saveVersionMutation if content unchanged
- [x] feat(frontend): copyable errors in ExecutionOutputPanel — Copy button + select-all pre
- [x] feat(backend): PATCH /blocks/{block_id}/python now updates job.generated_files[py_key] so EditorTab stays in sync
- [x] feat(backend): block refine trigger changed from "human-refine" to "agent" — history pane now correctly shows 🤖
- [x] feat(backend): _BestEffortAgentAdapter in router — manual/manual_ingestion routed to agents; StubGenerator fallback on exception only
- [x] feat(backend): stub_generator fallback path → /workspace/data/{dataset_name}.csv
- [x] feat(backend): agent prompts enforce /workspace/data/<name>.csv file path convention
- [x] feat(infra): executor docker-compose volume mount uploads:/workspace/data:ro + WORKSPACE_DATA_DIR env var
- [ ] verify: Log/Output tabs in EditorTab bottom panel — may still not load; user to confirm after `make docker-build`
- [ ] verify: history pane click loads correct Python code in editor with multiple block revisions (needs docker-build first)
- [x] fix(worker): cancel check in `_translate_blocks` — open fresh session via `session_factory` instead of `session.refresh()` on outer session (fixes "not persistent within this Session" crash)
- [x] F20 Stream A: JobTrace model + Alembic 016, TraceEmitter, POST /cancel, GET /trace/stream SSE, LiveTraceDialog (timeline rail, shadcn tokens), trace button in JobsPage → see `docs/plans/latest/F20-live-trace-popup.md`
- [ ] F20 Stream B: ExecutionOutputPanel improvements (elapsed label, stderr split, recon cards) + Trust tab in EditorTab → see `docs/plans/latest/F20-live-trace-popup.md`
- [x] LiveTraceDialog UX overhaul — block colour states, pipeline:full banner, human-friendly check labels, user-toggleable expand, shimmer keyframe fixed → see `docs/plans/latest/F20-live-trace-popup.md`
- [x] feat(executor): per-block DataFrame session cache (Parquet) — `session_dir` threaded executor→recon→block_executor→main; prior block outputs pre-loaded; cleanup after loop
- [x] feat(worker): `pipeline:full` final recon run after all blocks — emits block_start/recon_result/block_done SSE events; displayed as summary banner in popup
- [x] fix(recon): `_build_recon_groups` fallback removed — per-block recon only fires for specifically-matched data files; job-level ref used only in pipeline:full run
- [x] fix(recon): column names normalized to lowercase in `recon.py` before all three checks (defensive; guards against SAS UPPERCASE ref headers)
- [x] fix(prompt): Rule 2 in `SHARED_TRANSLATION_RULES` strengthened — mandatory `toDF(*[c.lower() for c in df.columns])` after every file read; removes SAS uppercase/Python lowercase mismatch at source
- [x] fix(prompt): unified join key normalisation — save type before join, regexp_replace+cast, restore original type after join; single section replaces two conflicting ones
- [x] fix(prompt): generic schema-mismatch cast hint — per-column "output is X but ref expects Y — cast to match" in retry hint
- [x] fix(prompt): near-zero aggregate parity hint — floating point drift advisory injected when ref_sum < 1e-3
- [x] fix(worker): job status written immediately after recon (step 10a) — UI reflects proposed/under_review without waiting for doc/lineage LLM calls
- [x] fix(worker): `exec_ok` field on `GeneratedBlock`; threaded into `_persist_initial_revisions` to write baseline recon status (pass/fail) for every translated block
- [x] fix(worker): `_reconcile_initial_blocks` skip guard — only skips blocks with ref-based checks, allowing execution-only passes to be upgraded
- [x] feat(planner): `confidence_score` asked from MigrationPlannerAgent LLM; `BlockPlan` defaults changed (1.0→0.5, "high"→"unknown")
- [x] feat(backend): `effective_confidence_band` computed post-recon in trust report; added to `TrustReportBlock` schema
- [x] feat(backend): `end_line` threaded from `SASBlock` → `BlockPlan` → API
- [x] feat(frontend): derived strategy badge — "Translated" (green on pass, blue on no-recon), "Review Needed" (amber on fail), "Manual" (red always)
- [x] feat(frontend): SAS highlight uses actual `end_line` instead of hardcoded `startLine + 20`
- [x] feat(frontend): Activity button pulses (animate-pulse text-primary) when job is running/queued
- [x] fix(tests): deleted stale `tests/test_reconciliation_coerce.py` (imported removed `_coerce_sas_dates`)
- [x] fix(frontend): no-recon blocks now show green (not amber) in LiveTraceDialog — amber was misleading for execution-only pass
- [x] fix(recon): `_build_recon_groups` — strip libname prefix from output_datasets before stem match (`outdir.revenue_summary` → `revenue_summary`)
- [x] fix(block_executor): empty checks + ref present → synthetic `execution: fail` so retry loop fires on crash (was silently treating as pass)
- [x] fix(worker): translation exception now injects error as risk_flag and `continue`s to next attempt (was `break` on attempt 1)
- [x] fix(worker): `_reconcile_initial_blocks` (step 11) disabled — was running job-level ref against all intermediate blocks with wrong schema
- [x] fix(executor): session cache uses PySpark `spark.read/write.parquet` (was pandas); Spark init always included when session_dir set; load snippet runs after Spark init
- [x] fix(executor): session cache path changed to `/tmp/rosetta_cache/...` — `/workspace/data` is mounted read-only
- [x] fix(frontend): LiveTraceDialog — every completed block has chevron + expandable panel; no-ref blocks show "Executed — no reference file matched"
- [x] feat(frontend): Plan tab recon column — CheckCircle2/XCircle icons instead of Pass/Fail badges; manual strategy always shows `—`
- [x] feat(parser): MacroDef model, filename_map, PROC IML/FORMAT extractors, DROP/KEEP/WHERE/OUTPUT/ARRAY fields on SASBlock
- [x] feat(prompt): SHARED_TRANSLATION_RULES — explicit "always PySpark, never pandas" + "never cast to match ref schema" rules
- [x] feat(recon): DEBUG logs showing ref/actual rows, columns, dtypes before each check run
- [x] fix(worker): cumulative code execution — prior-block NameErrors fixed; Parquet session cache removed; `result = <output_var>` injected for correct recon capture
- [x] fix(prompt): `.schema[col]` introspection on inter-block DataFrames suppressed via `SHARED_TRANSLATION_RULES`
- [x] fix(planner): `block_type` authoritative from parser; PROC_IML no longer shows as UNTRANSLATABLE
- [ ] feat(planner): post-run risk+rationale enrichment — `_enrich_block_plan_post_run` in `main.py`; rule-based, no LLM call; re-persists `job.migration_plan` after `_persist_initial_revisions`
- [ ] F20 Stream B: ExecutionOutputPanel improvements + Trust tab in EditorTab → see `docs/plans/latest/F20-live-trace-popup.md`

---

**F21 — Pre-Migration Assessment (`docs/plans/latest/F21-pre-migration-assessment.md`) — COMPLETE**

- [x] F21 S-A: Alembic migration 018 — `notes TEXT` + `assessment JSON` columns on jobs table
- [x] F21 S-B: `Job` ORM model — add `notes` and `assessment` mapped columns
- [x] F21 S-C: `AnalyseResponse` Pydantic schemas (`AssessedBlock`, `OutputCoverage`, `PreviewStats`, etc.)
- [x] F21 S-D: `POST /analyse` route — synchronous parser + lightweight LLM description + full assessment response
- [x] F21 S-E: Extend `POST /migrate` — accept `notes`, `importance_overrides`, `assessment_json`; store on job
- [x] F21 S-F: Backend tests — `test_analyse_route.py` + updated migrate tests
- [x] F21 S-G: Frontend TypeScript types — `AnalyseResponse` and all nested interfaces
- [x] F21 S-H: Frontend API functions — `analyseMigration` + updated `submitMigration`
- [x] F21 S-I: `MigrationPreviewPage` component — full assessment page, all seven sections
- [x] F21 S-J: Route registration + upload dialog wiring (`App.tsx`, `JobsPage.tsx`)
- [x] F21 S-K: `make test` exits 0

**F22 — Pre-Migration Assessment UX improvements (`docs/plans/latest/F22-assessment-ux.md`) — COMPLETE**

- [x] F22 S-A: Headline verdict card — RED/AMBER/GREEN + effort + critical issue callout → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-B: PII alert banner above the fold → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-C: Manager-friendly tier label copy → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-D: Blast radius on 🟡 blocks + sort blocks within tiers by blast radius → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-E: "What you need to do" summary — pre/post split, grouped by importance_reason → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-F: Section reorder — lineage after risk, full order, fileRiskTiers prop wired → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-G: PreviewLineageGraph risk-tier colouring (SAS file node borders) → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-H: Collapse configuration values and validation coverage by default → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-I: `make test` exits 0
- [x] F22 S-J: Deduplicate missing dependencies by name → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-K: Improve missing dep path display (basename + referenced-by count) → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-L: Fix headline recommendation sentence when missing deps present → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-M: Missing deps acknowledgment checkbox + gate fix → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-N: Remove "+N more" truncation from action summary datasets → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-O: Validation/Config section count labels → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-P: Lineage graph fitView padding → see `docs/plans/latest/F22-assessment-ux.md`
- [x] F22 S-Q: `make test` exits 0 (post bug-fix pass)
- [x] F22 S-R: Navigate to `/jobs/{id}` after submit (was `navigate("/jobs")`)
- [x] F22 S-S: Persist full `AnalyseResponse` in assessment snapshot; `GET /jobs/{id}/assessment` endpoint; `AssessmentPanel` in PlanTab
- [x] F22 S-T: AssessmentPanel UX polish — effort floor, inline tier counts, remove tile grid, hide toggle when empty, temporal subtitles, blocks hint
- [x] F22 S-U: Remove misleading "actual results after run" subtitle from Migration plan label
- [x] F22 S-V: Plan tab 7 UX fixes — blocker dedup, label always shown, left-align stats, chevron toggle, no dep truncation, hide confidence until loaded, blocks in card
- [x] F22 S-W: Collapse AssessmentPanel — replace with slim AssessmentCallouts row (missing deps + PII only) inside plan card
- [x] F22 S-X: Restore effort estimate + circular dep warning dropped during S-W
- [x] F22 S-Y: PM-facing AttentionBlocksSummary — one card per attention block with rationale, status badge, confidence %; Blocks toggle labelled "developer detail"
- [x] F22 S-Z: Layout polish — grammar fix (n() helper), red-outline "Accept anyway" button, hide zero stats, two-line block card, tighter spacing, remove "developer detail" qualifier
- [x] F22 post-S-Z: Trust-aware `TrustBadge` in page header; recommendation strip icon+bold verdict+muted detail; 12-issue design review (bars w-28, strip spacing, attention heading, badge→location gap)
- [x] F22 post-S-Z: Plan tab layout — Blocks inside card, auto-expand green state, effort to card header, in-card Accept/Accept-anyway button for all trust states
- [x] F22 post-S-Z: Accept CTA consolidated to Plan tab only — removed from page header for all trust states

**F23 — Plan tab PM-readability pass (`docs/plans/latest/F23-plan-tab-pm-readability.md`) — COMPLETE**

- [x] F23 S-A: Rename "Risk" → "Complexity" in stats row; add tooltips to both Confidence and Complexity bars
- [x] F23 S-B: Rewrite recommendation strip detail texts for all three states (green/amber/red)
- [x] F23 S-C: Add "Produces" output scope row to plan card
- [x] F23 S-D: Revert Blocks auto-expand — collapse by default in all states
- [x] F23 S-E: `make test` exits 0
- [x] F23 S-F: Scope summary line in card header (SAS files · blocks · output datasets)
- [x] F23 S-G: Accept button moved to standalone bottom card row; accepted state shows confirmation text
- [x] F23 S-H: Stats row moved above assessment callouts
- [x] F23 S-I: "Reads" input sources row alongside "Produces"
- [x] F23 S-J: Attention block cards show "Affects: X, Y" from AssessedBlock.output_datasets
- [x] F23 S-K: Missing-deps warning elevated to distinct amber bordered card
- [x] F23 S-L: `make test` exits 0

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
