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
- [ ] fix(backend): `translate_best_effort` strategy — removed in F27 S-C/S-D → see `docs/plans/latest/F27-trust-report-bug-fixes.md`
- [x] fix(backend): `manual_ingestion` StubGenerator — now emits `pd.read_csv(disk_path)` scaffold with `is_untranslatable=False`, `confidence_score=0.7`; block_plan strategy passed to router via `block_plan_map` in `_translate_blocks()`
- [x] fix(executor): data_dir routing — uploaded files saved to `/uploads/<job_id>/<basename>`; executor rewrites `/workspace/data/` → `data_dir/` at run time; `data_dir` threaded through all recon call sites
- [x] fix(executor): xlsx support — openpyxl added to Dockerfile; `_fix_excel_spark_reads()` guard rewrites bad Spark xlsx reads; prompt updated with pandas bridge pattern
- [x] fix(backend): PROC IMPORT output_var naming — removed `_file_io_types` exclusion from `all_block_outputs`; `normalise_output_var` + `normalise_output_var_in_code` shared utilities in `agents/shared.py`
- [x] fix(backend): file_count off-by-one — counts per-path `__ref_*__` sentinels; excludes canonical aliases and `__refine_context__`
- [ ] refactor(backend): consolidate job statuses — backend statuses (queued/running/proposed/under_review/accepted/done/failed) should be reduced; proposed and under_review are internal pipeline concepts that leak into the UI; frontend currently maps them to "Processing" and "Needs Review" as a workaround; backend statuses should be simplified when safe to do so without breaking DB queries or worker logic
**F27 — Trust report bug fixes (`docs/plans/latest/F27-trust-report-bug-fixes.md`) — complete**
- [x] F27 S-A: Fix `auto_verified` counter — `reconciliation_status != "fail"` instead of `== "pass"` → see `docs/plans/latest/F27-trust-report-bug-fixes.md`
- [x] F27 S-B: Fix `needs_attention` — add `translated_with_review` to condition → see `docs/plans/latest/F27-trust-report-bug-fixes.md`
- [x] F27 S-C: Remove `translate_best_effort` from backend enum + schemas → see `docs/plans/latest/F27-trust-report-bug-fixes.md`
- [x] F27 S-D: Remove `translate_best_effort` from frontend label map → see `docs/plans/latest/F27-trust-report-bug-fixes.md`
- [x] F27 S-E: Update trust report tests → see `docs/plans/latest/F27-trust-report-bug-fixes.md`
- [x] F27 S-F: `make test` exits 0 → see `docs/plans/latest/F27-trust-report-bug-fixes.md`
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

## Phase 3 — Frontend Features (post-MVP)

**F24 — SAS Editor Fidelity (`docs/plans/latest/F24-sas-editor-fidelity.md`) — complete**
- [x] F24 S-A: Tokenizer improvements — functions token, missing keywords, `* text;` comment fix → see `docs/plans/latest/F24-sas-editor-fidelity.md`
- [x] F24 S-B: Theme brightness — sas-light keyword blue + keyword.function colour both themes → see `docs/plans/latest/F24-sas-editor-fidelity.md`
- [x] F24 S-C: Code folding for DATA/PROC/DO blocks → see `docs/plans/latest/F24-sas-editor-fidelity.md`
- [x] F24 S-D: `make test` exits 0 → see `docs/plans/latest/F24-sas-editor-fidelity.md`
- [x] F24 post-plan: Monaco global theme override fix — Python editor was resetting theme to `vs`; unified both editors to `sas-light`/`sas-dark`
- [x] F24 post-plan: macroKeywords expansion — 21 missing tokens (`%LOCAL`, `%SYSFUNC`, `%SYMEXIST`, etc.) now purple
- [x] F24 post-plan: function color = keyword color — aligned to SAS Studio (no teal distinction)
- [x] F24 post-plan: PROC option keywords — `NOPRINT`, `NODUPKEY`, `NWAY`, `NLEVELS`, `DATAFILE`, `DBMS`, `REPLACE`, `NOCENTER`, `LINESIZE`, `PAGESIZE` + 15 others added to keywords
- [x] F24 post-plan: sasFunctions lookahead — `(?=\s*\()` prevents `n`, `sum`, `mean`, `min`, `max` etc. highlighting blue as variable names

**Doc/spec tasks (GitHub issues — quick wins)**
- [x] #26: Update `docs/mvp-scope.md` with supported/out-of-scope table + add short UI scope note → PR #37
- [x] #30 (part): Write `docs/personas.md` persona-to-view mapping (tech lead vs PO); file separate issue for UX implementation → PR #37
- [ ] #32: Write `docs/reports-spec.md` before implementing F25 — ideally after #23 (Danske Bank review) delivers findings
- [x] #33 (part): Document input prerequisites in `docs/input-prerequisites.md` → PR #37
- [x] #18: Write `docs/confidence-metric.md` — what the confidence score means and how it is computed → PR #38 (tooltip link pending #17)
- [ ] #35: Parked — answered on issue; revisit after current milestones

**F25 — Evaluation Tab (`docs/plans/latest/F25-evaluation-tab.md`) — complete**
- [x] F25 S-A: Add `criticality` + `human_review_required` to `TrustReportBlock` schema → `src/backend/api/schemas.py`
- [x] F25 S-B: Fix `_blast_radius_map` (source_file → source_block_id bug) + compute criticality → `src/backend/api/routes/jobs.py`
- [x] F25 S-C: Tests for criticality computation → `tests/test_changelog_trust_report.py`
- [x] F25 S-D: Update frontend `TrustReportBlock` type → `src/frontend/src/api/types.ts`
- [x] F25 S-E: Build `EvaluationTab` component → `src/frontend/src/components/JobDetail/EvaluationTab.tsx`
- [x] F25 S-F: Wire Evaluation tab into `JobDetailPage` → `src/frontend/src/pages/JobDetailPage.tsx`
- [x] F25 S-G: `make test` exits 0

**F26 — Criticality column on Plan tab block table (`docs/plans/latest/F26-criticality-plan-tab.md`) — complete**
- [x] F26 S-A: Add Criticality column to `BlockPlanTable` → `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- [x] F26 S-B: `make test` exits 0

**5-tab chevron restructure (issues #39–47) — see DECISIONS.md 2026-06-02**
- [x] #39: Audit SAS metadata extraction — audit complete; gaps documented below; issue to be closed once gap items are filed or triaged

  **#39 findings — SAS metadata extraction gaps**

  *Tier 1 — Critical (affects translation correctness)*
  - [ ] `.sas7bdat` column types, labels, formats, lengths — `pyreadstat` exposes `meta.column_labels`, `meta.column_formats`, `meta.readstat_variable_types`, `meta.column_lengths`; none currently extracted or surfaced
  - [ ] `PROC FORMAT` value-to-label mappings — block is detected but inner `VALUE`/`INVALUE` pairs are not parsed; losing format definitions breaks any downstream BI semantic layer
  - [ ] `INFILE`/`INPUT` column definitions — fixed-column and delimited layouts not extracted; column names/types are inferred from the LLM, not from the source declaration
  - [ ] `CALL SYMPUT`/`CALL SYMPUTX` — runtime macro variable assignment not captured; dynamic values unresolvable without this

  *Tier 2 — Data model completeness*
  - [ ] `PROC SQL CREATE TABLE` column definitions — column names and types declared inline not extracted into the block model
  - [ ] `LIBNAME` engine type — `ENGINE=` option not stored; needed to distinguish SAS/SHARE, Hadoop, ODBC, etc. for Data Storage tab mapping
  - [ ] Variable-level `FORMAT` and `INFORMAT` statements — per-variable display/read formats not captured from `DATA` step
  - [ ] `.sas7bdat` row counts — `meta.row_count` available via pyreadstat; not currently read or stored

  *Tier 3 — BI / reporting layer*
  - [ ] `PROC TABULATE` — falls to `PROC_UNKNOWN`; most OLAP-like native SAS proc; should be recognised for BI tab
  - [ ] `PROC FORMAT` block content — block node exists, inner pairs unparsed (duplicate of Tier 1 but specifically for the BI semantic layer use-case)
  - [ ] `PROC CONTENTS` output dataset target — output `OUT=` dataset not captured
  - [ ] `PROC EXPORT` output file path — `OUTFILE=` not captured; needed to trace data lineage to downstream consumers
**F28 — 5-tab chevron shell (`docs/plans/latest/F28-chevron-tab-shell.md`) — complete**
- [x] F28 S-A: URL-synced routing + new tab keys in JobDetailPage → see `docs/plans/latest/F28-chevron-tab-shell.md`
- [x] F28 S-B: ChevronTabBar component (chevron shape via CSS clip-path) → see `docs/plans/latest/F28-chevron-tab-shell.md`
- [x] F28 S-C: Wire existing components into new tab slots → see `docs/plans/latest/F28-chevron-tab-shell.md`
- [x] F28 S-D: `make test` exits 0 → see `docs/plans/latest/F28-chevron-tab-shell.md`
- [x] fix(F28): EvaluationTab removed from Plan tab; failed-reconciliation pill + collapsible review queue added to PlanTab
- [x] fix(F28): LineageGraph crash on undefined nodes guarded in LineageTab
- [x] fix(F28): LineageTab toast.error removed — silent inline message instead
**F29 — Plan tab refinement (#41) → see `docs/plans/latest/F29-plan-tab-refinement.md`**
- [x] F29 S-A: Fix review queue expanded by default
- [x] F29 S-B: Replace stat pills with clickable summary cards + stat filter (auto-expands Blocks)
- [x] F29 S-C: Upgrade review queue to full columns (source file, confidence, recon, blast radius)
- [x] F29 S-D: Add confidence info dialog
- [x] F29 S-E: Add lineage unavailable notice
- [x] F29 S-F: Add per-file breakdown section
- [x] F29 S-G: Bulk re-translate button (moves into Needs attention header)
- [x] F29 S-H: Restore doc state in JobDetailPage + Report collapsible panel
- [x] F29 S-I: Migration history collapsible panel
- [x] F29 S-J: Verdict strip (3-state, derived from trustReport)
- [x] F29 S-K: Scope summary in page header subtitle
- [x] F29 S-L: Merge attention cards + review queue → single section with Cards/Table toggle
- [x] F29 S-M: Description text as free-standing prose (separate from metrics card)
- [x] F29 S-N: Sticky accept footer (verdict summary + Accept button)
- [x] F29 S-O: make test exits 0
**F33 — ETL tab (#42) → see `docs/plans/latest/F33-etl-tab.md`**
- [x] F33 S-A: Backend Option A+ — add trigger field to BlockPythonEditRequest
- [x] F33 S-B: Extend LineageGraph with onFileNodeClick + trustFiles status
- [x] F33 S-C: Update saveBlockPython to accept trigger
- [x] F33 S-D: Build BlockInspectorPanel component
- [x] F33 S-E: Build BlockCodePopup component
- [x] F33 S-F: Build ETLTab orchestrating component
- [x] F33 S-G: Wire ETLTab into JobDetailPage
- [x] F33 S-H: make test exits 0
- [ ] #43: Data Storage tab — SAS table inventory, DW mapping — wireframe pending
- [x] #40: Chevron tab shell — delivered by F28, issue closed
- [x] #44: BI tab placeholder — empty state delivered in F28 S-C, issue closed
- [x] #45: AI tab placeholder — empty state delivered in F28 S-C, issue closed
- [ ] #46: Remove legacy tab components — blocked: depends on #41–45
- [ ] #47: Remove legacy standalone pages and routes — blocked: depends on #46
- [ ] #52: Revisit sidebar navigation — blocked on persona validation
- [x] fix(frontend): PlanTab review queue — removed `.slice(0, 10)` cap; all items now render sorted by criticality

**GitHub issue priority queue (unblocked — source of truth is GitHub)**
- [ ] #19: Runbook for high-risk / non-convertible blocks → generate per-block remediation view
- [ ] #25: Token usage + bill-of-materials / scoping summary
**F30 — Reads/Produces row (#60) → see `docs/plans/latest/F30-reads-produces-row.md`**
- [x] F30 S-A: Add input/output_datasets to BlockPlan model
- [x] F30 S-B: Populate in _build_migration_plan()
- [x] F30 S-C: Add to BlockPlanResponse schema
- [x] F30 S-D: Update BlockPlan TypeScript type
- [x] F30 S-E: Render Reads/Produces row on Plan tab
- [x] F30 S-F: make test exits 0

**F31 — Missing dependencies callout (#61) → see `docs/plans/latest/F31-missing-dependencies-callout.md`**
- [x] F31 S-A: Add macro invocation extraction to parser
- [x] F31 S-B: Create dependency_checker module
- [x] F31 S-C: Add missing_dependencies to MigrationPlan model
- [x] F31 S-D: Call dependency checker in worker pipeline
- [x] F31 S-E: Add to JobPlanResponse schema
- [x] F31 S-F: Update TypeScript type
- [x] F31 S-G: Render amber callout on Plan tab
- [x] F31 S-H: make test exits 0

**F32 — PII warning (#62) → see `docs/plans/latest/F32-pii-sensitive-data-warning.md`**
- [x] F32 S-A: Create pii_scanner.py
- [x] F32 S-B: Add sensitive_data_findings to MigrationPlan model
- [x] F32 S-C: Call PII scanner in worker pipeline
- [x] F32 S-D: Add to JobPlanResponse schema
- [x] F32 S-E: Update TypeScript type
- [x] F32 S-F: Render warning banner on Plan tab
- [x] F32 S-G: make test exits 0
- [ ] #56: Post-run risk + rationale enrichment (rule-based, already designed)
- [ ] #57: Macro definition + call expansion (%MACRO/%MEND)
- [ ] #58: Record-level reconciliation (row-by-row diff)
- [ ] #59: Artefact versioning — group jobs by input_hash
- [ ] #21: Consolidate lineage into a single primary view — `backlog` label
- [ ] #20: Rollback / versioning based on lineage — `backlog` label
- [ ] #32: Specify decision-ready reports (technical + PO) — `backlog` label, deferred
- [ ] #24: Implement decision-ready reports — `backlog` label, deferred

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
