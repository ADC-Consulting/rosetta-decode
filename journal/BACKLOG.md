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

- [ ] F60: PROC FORMAT translation (user formats → when/otherwise) → see `docs/plans/latest/F60-proc-format-translation.md` (code complete + green, pending commit; end-to-end sandbox evidence still to capture per S-F)
  - [x] F60 S-A: format-catalog data model (`FormatDef`/`FormatEntry` + `format_catalog` on ParseResult/JobContext) → `src/worker/engine/models.py`
  - [x] F60 S-B: deterministic extractor (`extract_format_catalog` + `normalize_format_name`; line-bounded mapping regex) → `src/worker/engine/format_catalog.py`
  - [x] F60 S-C: unit tests for extractor → `tests/test_format_catalog.py`
  - [x] F60 S-D: wire extraction into parser (on `expanded_source`) + JobContext → `src/worker/engine/parser.py`, `src/worker/main.py`
  - [x] F60 S-E0: router guard — `is_simple()` allowlist so `put()` DATA steps route to `DataStepAgent`, not `_SimpleCopyHelper` → `src/worker/engine/router.py`
  - [x] F60 S-E: inject referenced formats into agent prompts + scoped `put()` rule (normalized name match, no built-in regression) → `agents/{shared,data_step,proc,generic_proc}.py`
  - [x] F60 S-F: tests for wiring + prompt injection (cross-file catalog, width/`$` refs, built-in negative case) → `tests/test_format_catalog.py`; router routing covered in `tests/test_translation_router.py`
  - [x] F60 S-G: `make test` exits 0 (all 7 gates green, coverage ≥90%)
- [x] F61: Type-aware schema contract — bake source-declared column types into delivered PySpark → see `docs/plans/latest/F61-declared-column-types.md`
  - [x] F61 S-A: `DataFileInfo.column_types` field → `src/worker/engine/models.py`
  - [x] F61 S-B: `_map_readstat_type` + `_sniff_file` 3-tuple + catalog wiring → `src/worker/main.py`
  - [x] F61 S-C: `inject_declared_casts` deterministic helper → `src/worker/engine/agents/shared.py`
  - [x] F61 S-D: wire injector into DataStepAgent, ProcAgent, GenericProcAgent → `agents/{data_step,proc,generic_proc}.py`
  - [x] F61 S-E: `detect_referenced_data_files` + `render_declared_types_section` → `src/worker/engine/agents/shared.py`
  - [x] F61 S-F: reconcile rules 1/5/8 with F61 (informational notes, no new cast rule) → `src/worker/engine/agents/shared.py`
  - [x] F61 S-G: wire declared-types section into all three prompt builders → `agents/{data_step,proc,generic_proc}.py`
  - [x] F61 S-H/S-I: unit + e2e tests → `tests/test_shared_inject_declared_casts.py`, `tests/test_worker_main*.py`, `tests/test_format_catalog.py`
  - [x] F61 S-J: `make test` exits 0 (all 7 gates green)
- [x] F61-followups (discovered + fixed during F61 sandbox verification, 2026-06-15):
  - [x] Recon dtype detection robust to pandas 3.0 `StringDtype` (`not is_numeric_dtype`) → `executor/recon.py`, `worker/validation/reconciliation.py`
  - [x] Executor result date serialization `date_format='iso'` (was epoch-millis) → `src/executor/runner.py`
  - [x] AMBIGUOUS_REFERENCE self-heal: §5 rule + bare→alias `F.col` rewrite in `_safe_exec` + executor bounded retry
  - [x] Corrected stale golden `adsl_expected.csv` TRTEDT/TRTDURD from current `ex_raw.csv`
- [ ] F61-debt: add a dedicated unit test for `_coerce_sas_date_columns` (validated manually this session; no committed regression test yet)
- [ ] Agentic full-pipeline retry (runtime crashes only): attribute traceback → block via `# SAS:` provenance, re-run that block's refine with the pipeline error as hint. Do NOT auto-fix parity mismatches (gaming-the-golden risk). Needs reproducibility bound. See F19 agentic-refine-loop.
- [ ] Date/datetime semantic typing (beyond char-vs-numeric): format-aware SAS date handling in delivered code (F61 out-of-scope item)
- [ ] F1-ext: Macro definition + call expansion (`%MACRO` / `%MEND`) — superseded by F57 (call expansion) + F59 (control flow); close once verified end-to-end
- [ ] F3-ext: Row-level hash diff check
- [ ] F4: SAS log ingestion — parse log structure
- [ ] F4: LLM call for runtime logic reconstruction from log
- [ ] F10: Artefact versioning — group jobs by input_hash, expose version history per migration
- [ ] F11: Plain-language documentation — LLM-generated business-readable summary per job → see `docs/plans/F-backend-postmvp.md` S-BE4
- [x] F15: Record-level reconciliation — row-by-row diff with configurable keys and tolerances (row_hash_diff + ReconConfig + LLM key resolution; `feat/F15-record-level-reconciliation`)
- [x] fix: preserve leading zeros by honoring SAS `LENGTH var $w` char declarations at CSV read time (`fix/csv-declared-char-zeros`)
- [ ] follow-up: add `dtype={col: str}` for declared-char columns in `stub_generator.py` `pd.read_csv` scaffold (untranslatable PROC IMPORT fallback path)
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
- [x] feat(planner): post-run risk+rationale enrichment — `_enrich_block_plan_post_run` in `main.py`; rule-based, no LLM call; writes new `migration_plan_post_run` column after `_persist_initial_revisions` (two-column; pre-run preserved) → see #56
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

**F34 — Token usage & BOM scoping summary (#25) → see `docs/plans/latest/F34-token-usage-scoping.md`**
- [x] F34 S-A: Alembic migration 018 + Job model column
- [x] F34 S-B: UsageTracker + contextvars module
- [x] F34 S-C: Tracker unit tests
- [x] F34 S-D: Instrument 12 LLM call sites
- [x] F34 S-E: Orchestrator activate/set_phase/persist
- [x] F34 S-F: Worker integration test
- [x] F34 S-G: Pricing module (LiteLLM fetch + static fallback)
- [x] F34 S-H: Pricing unit tests
- [x] F34 S-I: API schemas (PhaseTokens, TokenUsageStats, CostEstimate, BomSummary, ScopingSummaryResponse)
- [x] F34 S-J: Extract _build_trust_blocks() helper
- [x] F34 S-K: Markdown renderer + tests
- [x] F34 S-L: GET /jobs/{id}/scoping route
- [x] F34 S-M: Route tests
- [x] F34 S-N: Frontend API client types + getJobScopingSummary
- [x] F34 S-O: ScopingSummaryPanel component
- [x] F34 S-P: Wire panel into PlanTab
- [x] F34 S-Q: make test exits 0 + close-out

- [x] #43: Data Storage tab — schema browser, ERD, data flow, output catalog → `feat/F35-migration-output-catalog` (PR #102)
  - [x] Column metadata extraction from SAS/XPT/CSV files; semantic type mapping; GET /jobs/{id}/schema + PATCH
  - [x] DataStorageTab: source / migration output sidebar sections; column schema detail panel; DDL collapsible
  - [x] SchemaCanvas ERD (PK/FK badges, fit-to-view, scroll-to-selected); DataModelERD (output tables only)
  - [x] DataFlowDiagram: ReactFlow + dagre LR, step interactivity, tooltips, dataset name normalisation
  - [x] Right panel differentiated: source tables → SAS metadata read-only; output tables → proposed schema / diff view
- [x] #40: Chevron tab shell — delivered by F28, issue closed
- [x] #44: BI tab placeholder — empty state delivered in F28 S-C, issue closed
- [x] #45: AI tab placeholder — empty state delivered in F28 S-C, issue closed
- [ ] #46: Remove legacy tab components — blocked: depends on #41–45
- [ ] #47: Remove legacy standalone pages and routes — blocked: depends on #46
- [ ] #52: Revisit sidebar navigation — blocked on persona validation
- [x] fix(frontend): PlanTab review queue — removed `.slice(0, 10)` cap; all items now render sorted by criticality

**F35 — Remediation runbook (#19) → see plan at .claude/plans/generate-runbook-for-high-risk-expressive-kernighan.md**
- [x] F35 S-A: runbook_templates.py — rule-based remediation_outline() + why_risky()
- [x] F35 S-B: RunbookEntry + RunbookResponse schemas
- [x] F35 S-C: _build_runbook_entries() + _render_runbook_markdown() helpers
- [x] F35 S-D: GET /jobs/{id}/runbook route
- [x] F35 S-E: test_runbook_templates.py unit tests
- [x] F35 S-F: test_runbook_routes.py async route tests
- [x] F35 S-G: RunbookEntry / RunbookResponse TypeScript types + getJobRunbook()
- [x] F35 S-H: RunbookPanel component — collapsible, lazy-loaded, Copy-as-Markdown
- [x] F35 S-I: Wire RunbookPanel into PlanTab below ScopingSummaryPanel
- [x] F35 S-J: make test exits 0

**GitHub issue priority queue (unblocked — source of truth is GitHub)**
- [x] #19: Runbook for high-risk / non-convertible blocks → delivered by F35
- [x] #25: Token usage + bill-of-materials / scoping summary → delivered by F34
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
- [x] #56: Post-run risk + rationale enrichment (rule-based) — `_enrich_block_plan_post_run` + `migration_plan_post_run` column + `effective_migration_plan` accessor; branch `feat/F56-blockplan-risk-rationale`
- [ ] frontend: Plan-tab Strategy label vs `needs_attention` flag inconsistency for `translated_with_review` (fix B+) — issue text drafted 2026-06-15; surfaced during F56 verification
- [x] #57: Macro definition + call expansion (%MACRO/%MEND) → see `docs/plans/latest/F57-macro-call-expansion.md`
  - [x] F57 S-A: macro signature + call-arg parsing helpers → `src/worker/engine/macro_call_expander.py`
  - [x] F57 S-B: expandability guard (`_is_expandable`) → `src/worker/engine/macro_call_expander.py`
  - [x] F57 S-C: core `expand_macro_calls()` → `src/worker/engine/macro_call_expander.py`
  - [x] F57 S-D: two-pass expansion wired into `SASParser.parse` → `src/worker/engine/parser.py`
  - [x] F57 S-E: unit tests → `tests/test_macro_call_expander.py`
  - [x] F57 S-F: reconciliation/integration test → `tests/reconciliation/test_macro_expansion.py`
  - [x] F57 S-G: `make test` exits 0
- [x] F59: Macro control-flow & variable evaluation (%if/%do/%let/%global) → see `docs/plans/latest/F59-macro-control-flow.md`
  - [x] F59 S-A0: tokenizer (`_tokenize`, `Token`, `CannotResolveMacroLogic`) → `src/worker/engine/macro_logic.py`
  - [x] F59 S-A: macro condition evaluator (`evaluate_condition`) → `src/worker/engine/macro_logic.py`
  - [x] F59 S-B: macro body logic resolver (`resolve_macro_body`) → `src/worker/engine/macro_logic.py`
  - [x] F59 S-B2: iterative `%do %to` loop unrolling → `src/worker/engine/macro_logic.py`
  - [x] F59 S-C: unit tests for tokenizer + evaluator + resolver → `tests/test_macro_logic.py`
  - [x] F59 S-D: integrate logic resolution into `expand_macro_calls` → `src/worker/engine/macro_call_expander.py`
  - [x] F59 S-E: unit tests for integrated expansion → `tests/test_macro_call_expander.py`
  - [x] F59 S-F: reconciliation test through parser → `tests/reconciliation/test_macro_control_flow.py`
  - [x] F59 S-G: `make test` exits 0
- [x] #58: Record-level reconciliation (row-by-row diff) — row_hash_diff + ReconConfig + LLM key resolution
- [ ] #59: Artefact versioning — group jobs by input_hash
**F67 — ETL tab: Source / Target toggle (#67) → see `docs/plans/latest/F67-etl-source-target-toggle.md` — complete**
- [x] F67 S-A: `sasFileToPyFile` + `pyFileToSasFiles` utility → `src/frontend/src/lib/sas-python-file-map.ts`
- [x] F67 S-B: `TargetGraph` component — Python file nodes, remapped edges, trust-coloured, legend → `src/frontend/src/components/JobDetail/TargetGraph.tsx`
- [x] F67 S-C: Source / Target toggle in ETLTab + wire TargetGraph → `src/frontend/src/components/JobDetail/ETLTab.tsx`
- [x] F67 S-D: `make test` exits 0

**F68 — Post-acceptance workflow (#68) → see `docs/plans/latest/F68-post-acceptance-workflow.md` — complete**
- [x] F68 S-A: Alembic migration 020 — add `accepted_by` → `alembic/versions/020_add_accepted_by.py`
- [x] F68 S-B: Job model `accepted_by` column → `src/backend/db/models.py`
- [x] F68 S-C: Migration-package builder → `src/backend/api/packaging.py`
- [x] F68 S-D: Requirements inference helper → `src/backend/api/packaging.py`
- [x] F68 S-E: Rewrite `download_job` route → `src/backend/api/routes/jobs.py`
- [x] F68 S-F: Immutable acceptance (409 on re-accept) → `src/backend/api/routes/jobs.py`
- [x] F68 S-G: Backend tests (packaging, accept, download) → `tests/test_packaging.py`
- [x] F68 S-H: Frontend API client + types → `src/frontend/src/api/{jobs,types}.ts`
- [x] F68 S-I: Accepted-state header — locked badge + Download CTA → `JobDetailPage.tsx`
- [x] F68 S-J: Read-only editors in delivered mode → `EditorTab.tsx`
- [x] F68 S-K: Verdict strip accepted state → `PlanTab.tsx`
- [x] F68 S-L: `make test` exits 0
**F69 — Target view polish → see `docs/plans/latest/F69-target-view-polish.md` — complete**
- [x] F69 S-A: inspector header `.sas` → `.py` in Target view → `BlockInspectorPanel.tsx`, `ETLTab.tsx`
- [x] F69 S-B: hide handles on nodes with no edges in that direction → `FileNodeCard.tsx`, `TargetGraph.tsx`
- [x] F69 S-C: connection count — drop amber color, fix `⇔` → `↔` → `FileNodeCard.tsx`
- [x] F69 S-D: summary bar shows `modules: N` in Target view → `ETLTab.tsx`
- [x] F69 S-E: replace `PROGRAM` badge with `.py` badge on Target nodes → `FileNodeCard.tsx`, `TargetGraph.tsx`
- [x] F69 S-F: isolated row divider + "No data dependencies detected" label → `TargetGraph.tsx`
- [x] F69 S-G: node names include `.py` extension → `TargetGraph.tsx`
- [x] F69 S-H: legend swatches are rectangles, not circles → `TargetGraph.tsx`
- [x] F69 S-I: tooltip on Source/Target toggle buttons → `ETLTab.tsx`
- [x] F69 S-J: `make test` exits 0

**F70 — Target ETL sub-views: Steps / Modules / Blocks → see `docs/plans/latest/F70-target-etl-subviews.md` — complete**
- [x] F70 S-A: `Steps | Modules | Blocks` toggle in ETLTab summary bar (Target-only); `targetView` state
- [x] F70 S-B: TargetGraph `view` prop + layout switching; shared `rawEdges` derivation across branches
- [x] F70 S-C: Steps view — dagre TB layout, `PipelineStepNode` (filename, `.py` badge, trust bar, `deps: N → N`)
- [x] F70 S-D: Modules view — existing dagre LR graph gated behind `view === "modules"`
- [x] F70 S-E: Blocks view — expanded node cards in-place; heights computed from block count; `BlocksFileNode`
- [x] F70 S-F: `PythonModulePanel` component — tinted group headers for multi-source modules, `BlockRow` reuse
- [x] F70 S-G: ETLTab wiring — `selectedPyModule`, right-slot switching between `PythonModulePanel` / `BlockDetailPanel`
- [x] F70 S-H: `BlockDetailPanel` component — back link, strategy/confidence/recon, `ⓘ` rationale popover, "View Code"
- [x] F70 S-I: `make test` exits 0

**F71 — ETL Tab Polish** (`docs/plans/latest/F71-etl-tab-polish.md`)

- [x] F71 S01: Wire bridge step clicks to PipelineStepPanel → see `docs/plans/latest/F71-etl-tab-polish.md`
- [x] F71 S02: Step number badge on bridge step cards → see `docs/plans/latest/F71-etl-tab-polish.md`
- [x] F71 S03: Label trust stats "blocks:" in summary bar → see `docs/plans/latest/F71-etl-tab-polish.md`
- [x] F71 S04: Promote BlockDetailPanel back link to breadcrumb → see `docs/plans/latest/F71-etl-tab-polish.md`
- [x] F71 S05: `make test` exits 0

**F72 — Target Pipeline view overhaul**

- [x] F72: Replaced bridge view with TB module execution flow — `buildModulesGraph` gains `rankdir` param; Pipeline sub-view uses TB (top-to-bottom), Files stays LR; all bridge components removed.

**F73 — Target Pipeline sequential step cards**

- [x] F73: Replaced TB module dependency graph with `buildPipelineStepsGraph` — sequential step cards from `lineage.pipeline_steps`; each card shows step number, name, description, `.py` module badges; sequential edges, no dependency edges; fitView centering fixed via explicit node dimensions.

**Post-F73 fixes (2026-06-24, same branch)**

- [x] fix(data-tab): add `Number: "DOUBLE PRECISION"` to `SEMANTIC_TO_PG`; remove dead badge code; plain monospace type display
- [x] fix(etl-tab): Target Pipeline LR layout; `onPipelineStepClick` + `mode="target"` wired to `PipelineStepPanel`
- [x] feat(PipelineStepPanel): `mode` prop — target shows Python Modules section, reorders sections, hides SAS CODE, filters external DEPENDS ON
- [x] fix(target-legend): `TargetLegend` `view` prop — header/label change to "PIPELINE STEPS" vs "PYTHON MODULES"
- [x] fix(plan-tab): `isAccepted` derived from `job.status === "accepted"` not `Boolean(job.accepted_at)`; seed adds `accepted_at`
- [x] fix(target-etl-files-blocks): `buildPyFileToSasFilesMap` + `buildSasFileToPyFilesMap` parse provenance comments — fixes zero block counts and missing edges in Files/Blocks views; handles merge and split scenarios
- [x] fix(etl-tab): Source Pipeline card descriptions wrap to 2 lines (webkit clamp); `NODE_PIPELINE_H` 86→106
- [x] feat(etl-tab): `FileViewPopup` — full-file read-only Monaco popup for SAS and Python files; opened on file/module node click
- [x] feat(PipelineStepPanel): Python module names are clickable links opening `FileViewPopup`
- [x] fix(etl-tab): Pipeline → block back nav — Target mode routes through `handleTargetBlockClick` so `BlockDetailPanel` back link returns to correct Python module
- [x] feat(BlockDetailPanel): `parentPyFile` optional — hidden in Source mode; SAS source `file:line` reference is a clickable button opening SAS `FileViewPopup`; `onViewSourceFile` prop added
- [x] fix(etl-tab): Source Blocks click shows `BlockDetailPanel` first (not code popup); `showBlockDetail` covers both Source and Target mode
- [x] feat(etl-tab): Target Blocks redesign — compact graph nodes with segmented status bar; new `FileBlockListPanel` side panel with urgency-sorted blocks, rationale as primary label, `[SAS]` chip for traceability
- [x] docs: updated PR #106 description to cover all work on branch (F67–F73, ETL interaction fixes, Target Blocks redesign, Data/Plan tab fixes)

**F78 — Data Storage tab polish (`docs/plans/latest/F78-data-tab-polish.md`) — complete**
- [x] F78 S-A: fitView on DataFlowDiagram initial render → `DataFlowDiagram.tsx`
- [x] F78 S-B: step node label truncation fix + hover tooltip → `DataFlowDiagram.tsx`
- [x] F78 S-C: fitView on DataModelERD (SchemaCanvas) initial render → `SchemaCanvas.tsx`
- [x] F78 S-D: sidebar status dots distinguish migrated vs not-run → `DataStorageTab.tsx`
- [x] F78 S-E: replace "Not run" plain text with coloured badge → `DataStorageTab.tsx`
- [x] F78 S-F: `make test` exits 0

**F79 — Data table descriptions (`docs/plans/latest/F79-table-descriptions.md`) — complete**
- [x] F79 S-A: `derive_table_descriptions()` in schema_utils.py
- [x] F79 S-B: wire description into `TableSchema` + `build_job_schema()`
- [x] F79 S-C: DDL `COMMENT` clause in `generate_create_table()`
- [x] F79 S-D: pass description to DDL generator in `build_job_schema()`
- [x] F79 S-E: unit tests
- [x] F79 S-F: frontend — TS type + sidebar subtitle + header subtitle
- [x] F79 S-G: `make test` exits 0

**Post-F79 fixes (2026-06-25, feat/F67-etl-source-target-toggle)**

- [x] fix(F79): hide "Data model" and "Data flow" toggle buttons for source tables (`libname !== null`) → `DataStorageTab.tsx`
- [x] fix(backend): `_normalise_pipeline_step_names._resolve()` detect file extensions vs SAS `libname.table` — fixes "csv"/"xlsx" node labels → `src/backend/api/routes/jobs.py`
- [x] refactor(DataFlowDiagram): add `outputTableNames: string[]` prop; remove step/source nodes; show all ETL-produced tables with intermediate (amber) vs output (green) visual tiers → `DataFlowDiagram.tsx`, `DataStorageTab.tsx`
**F80 — Data Storage tab Source / Target sidebar toggle → see `docs/plans/latest/F80-intermediate-tables-as-artifacts.md` — complete**
- [x] F80 S-A: Source / Target toggle + sidebar restructure (label changed "Migration" → "Target" per ETL tab convention) → `DataStorageTab.tsx`
- [x] F80 S-B: DataFlow node click auto-switches to Target view; intermediate (amber) node clicks silently ignored → `DataStorageTab.tsx`
- [x] F80 S-C: `make test` exits 0

**Post-F80 (2026-06-29)**
- [x] feat(DataModelERD): always-visible status bar — output table count + inferred relationship count + legend copy → `DataModelERD.tsx`
- [x] feat(SchemaCanvas): PK/FK SVG icon prefix on column rows + bordered PK/FK badges (yellow/blue) → `SchemaCanvasNodesLayer.tsx`
- [x] fix(schema_utils): case-insensitive PK/FK match — `.lower()` on column name at all three comparison sites → `src/backend/api/schema_utils.py`
- [x] test(reconciliation): 6 new pharma sandbox regression tests — RETAIN+BY accumulator, NODUPKEY, PROC TRANSPOSE, PROC SQL HAVING, MERGE IN=, LENGTH truncation
- [x] feat(seed): `seed_finrep_job.py` — FINREP demo seed (5-step regulatory exposure pipeline, dec0de00-…-002)
- [x] feat(seed): `seed_kyc_job.py` — KYC/AML demo seed (6-step client screening pipeline, dec0de00-…-003)
- [x] feat(seed): `seed_all.py` — orchestrates all three demo seeds in sequence

**F85 — Plan tab UX overhaul (issue #85) — branch: `feat/F85-plan-tab-ux`**
- [x] feat(F85): verdict strip above metrics, attention-first collapsible, N/total stat cards, criticality row, scrollbar-gutter
- [x] fix(frontend): "Blocks"→"Steps" terminology across PlanTab, BlockPlanTable, TargetGraph, JobDetailPage, DocsPage
- [x] refactor(plan-tab): remove redundant sections; merge runbook inline into attention cards; 7 collapsibles → 2
- [x] feat(plan-tab): stat card affordance (hover ring, ChevronDown), ETL tab nav CTAs, accepted-job missing-deps callout past-tense
- [x] fix(F85): blank ETL tab — nested button in BlockDetailPanel → span role="button"
- [x] chore(seed): rename "Customer Revenue Pipeline" → "Monthly Revenue Pipeline"
- [x] fix(plan-tab): strip SAS libref prefix from Reads/Produces chips
- [x] feat(plan-tab): stat cards route to Needs Attention section with category filter (manual_todo / needs_review filter attention queue)
- [x] chore(seed): remove all stale "manual" references from PROC IML block — amber/review framing throughout
- [x] Open PR for `feat/F85-plan-tab-ux` → Closes #85 (PR #115, PR #125 merged 2026-07-07)

- [ ] #21: Consolidate lineage into a single primary view — `backlog` label
- [ ] #20: Rollback / versioning based on lineage — `backlog` label
- [ ] #32: Specify decision-ready reports (technical + PO) — `backlog` label, deferred
- [ ] #24: Implement decision-ready reports — `backlog` label, deferred

**Bug**
- [x] #100: Plan tab — strategy column label disagrees with attention flag for `translated_with_review` blocks → PR #128

**Cleanup / tech debt**
- [ ] #47: Remove legacy standalone pages and routes
- [ ] #46: Remove legacy tab components from JobDetailPage
- [ ] #52: UX — revisit sidebar navigation (align with confirmed user personas)
- [ ] #45: AI tab placeholder for AI side-effect data capture
- [ ] #44: BI tab placeholder for BI side-effect data capture

**Core product features**
- [ ] #69: Databricks / cloud deployment — DatabricksBackend, PySpark codegen, Workflow YAML export
- [ ] #79: Manual intervention workflow — track, assign, and reintegrate blocks requiring human coding
- [ ] #78: Client UAT view — simplified stakeholder view of migration evidence per engagement
- [ ] #77: Engagement workspace — tag jobs by client, cross-job progress view
- [ ] #59: Artefact versioning — group jobs by input hash, expose version history

**Go-to-market (added 2026-07-07, GitHub issues in Staging)**
- [ ] #116: Define data handling & security one-pager
- [ ] #117: Define ideal customer profile (ICP)
- [ ] #118: Define pricing model for migration engagements
- [ ] #119: Build ROI benchmark — manual migration vs. Rosetta
- [ ] #120: Define competitive positioning vs. SAS migration alternatives
- [ ] #121: Prepare standard legal templates (NDA + DPA)
- [ ] #122: Design pilot engagement — scope, deliverables, timeline
- [ ] #123: Write internal sales playbook for ADC consultants
- [ ] #124: Produce awareness content — why migrate from SAS in 2026

**F86 — "Before you accept" effort panel (#71) — PR #129 opened**
- [x] F86 S-A: `BeforeYouAcceptPanel` component → `src/frontend/src/components/JobDetail/BeforeYouAcceptPanel.tsx`
- [x] F86 S-B: Wire into PlanTab → `src/frontend/src/components/JobDetail/PlanTab.tsx`
- [x] F86 S-C: `make test` exits 0

**F87 — Design consistency pass: shared status/badge/card primitives → see `docs/plans/F87-design-consistency-shared-primitives.md` — PR #136 opened**
- [x] F87 S-A: shared status-color token module → `src/frontend/src/components/JobDetail/status-colors.ts`
- [x] F87 S-B: `StatusChip` shared component → `src/frontend/src/components/JobDetail/StatusChip.tsx`
- [x] F87 S-C: wire `StatusChip` into PlanTab AttentionCards + AttentionTable → `src/frontend/src/components/JobDetail/PlanTab.tsx`
- [x] F87 S-D: replace header confidence/risk bar hex colors → `src/frontend/src/components/JobDetail/PlanTab.tsx`
- [x] F87 S-E: wire `StatusChip` into BlockPlanTable risk/criticality/confidence chips → `src/frontend/src/components/JobDetail/BlockPlanTable.tsx`
- [x] F87 S-F: align StatusBadge job-status pill to shared chip convention → `src/frontend/src/components/JobDetail/StatusBadge.tsx`
- [x] F87 S-G: consolidate constants.ts risk/criticality maps → `src/frontend/src/components/JobDetail/constants.ts`
- [x] F87 S-H: normalize off-grid icon sizes (`size={13}`) → `PlanTab.tsx`, `BlockPlanTable.tsx`, `JobDetailPage.tsx`
- [x] F87 S-I: card primitive pass on Plan tab bordered containers → `src/frontend/src/components/JobDetail/PlanTab.tsx`
- [x] F87 S-J: manual smoke test (light + dark theme)
- [x] F87 S-K: `make tsc-check && make frontend-lint && make frontend-build && make test` exit 0

**F88 — "Manifest" design system: Plan tab + ETL block table → see `docs/plans/F88-manifest-design-system.md` — PR #137 opened (stacked on F87)**
- [x] F88 S-A: add `@fontsource/archivo` + `@fontsource/space-mono` → `src/frontend/package.json`
- [x] F88 S-B: scoped `.brand-manifest` theme tokens (fonts, teal accent, 6px radius) → `src/frontend/src/index.css`
- [x] F88 S-C: `status-colors.ts` → Manifest pill styling
- [x] F88 S-D: `StatusChip.tsx` → Manifest pill rendering
- [x] F88 S-E: `StatusBadge.tsx` → align to new pill convention
- [x] F88 S-F: `PlanTab.tsx` — apply brand scope to header (Archivo title, teal accent button/tabs) — caveat: title/tabs/Accept button live in `JobDetailPage.tsx` (shared header, out of subtask scope), see plan file note
- [x] F88 S-G: `PlanTab.tsx` — unified summary card restructure (top-edge color bar, one card)
- [x] F88 S-H: `BlockPlanTable.tsx` → Manifest conventions (Space Mono step ids, 6px radius)
- [x] F88 S-I: manual smoke test (light + dark, zero bleed into other tabs)
- [x] F88 S-J: `make tsc-check && make frontend-lint && make frontend-build && make test` exit 0

**F89 — Manifest color fidelity: muted palette + page background + tone cleanup → see `docs/plans/F89-manifest-color-fidelity.md` — PR #138 opened (stacked on F88)**
- [x] F89 S-A: scoped tone CSS custom properties (--tone-success/warning/danger/danger-strong + --brand-paper) → `src/frontend/src/index.css`
- [x] F89 S-B: apply `--brand-paper` as Plan tab page background → `PlanTab.tsx`
- [x] F89 S-C: `status-colors.ts` → reference new tone CSS variables
- [x] F89 S-D: merge `caution` tone into `warning` (drop orange, 5 tones total)
- [x] F89 S-E: fix `BeforeYouAcceptPanel.tsx` emerald/green inconsistency
- [x] F89 S-F: manual smoke test (light + dark, zero bleed outside Plan tab)
- [x] F89 S-G: `make tsc-check && make frontend-lint && make frontend-build && make test` exit 0
- [x] F89 post-commit: restore Plan tab content margin (25px → 40px, header+body stay aligned) + match `StatusBadge` job-status pills to the muted tone palette
- [x] F89 post-commit: fine-toothed-comb polish — header/body alignment bug, Table-view identifier truncation, Strategy filter-pill/chip shape parity, off-grid icon size, banner heading weight
- [x] F89 post-commit: widen content margin to 40px (final value) + "Needs attention" Cards view → 2-column grid matching the Manifest mockup
- [x] F89 post-commit: move Accept/Download button to the subtitle row (`JobDetailPage.tsx`, all 5 tabs) + lighten `--tone-warning` so "Needs Review" reads amber, not brown
- [x] F89 post-commit: add `--radius-xl` to `.brand-manifest` (unified card was missed by the earlier `--radius-lg/-md/-sm` fix) + route the PII accent strip through `--tone-danger-strong` instead of hardcoded `bg-red-500`
- [x] F89 post-commit: cap "Needs attention" cards at 3 (was 5 — matches the mockup's "+N more · Show all" grid slot)
- [x] Push `feat/F87-...`/`feat/F88-...`/`feat/F89-...` to origin and open stacked PRs #136 → #137 → #138

**F90 — Roll the Manifest design system out to the rest of the frontend → see `docs/plans/F90-manifest-rollout.md`**
- [x] F90 S-0: re-extract and commit the mockup source → `docs/design/Manifest.dc.html`
- [x] F90 S-A: global sidebar scoping → `src/frontend/src/components/AppSidebar.tsx`
- [x] F90 S-B: jobs list ("Migrations") scoping + status pill migration → `src/frontend/src/pages/JobsPage.tsx`
- [x] F90 S-C: ETL tab scoping (`ETLTab.tsx`, `TargetGraph.tsx`, `FileNodeCard.tsx`, nested popups/panels)
- [x] F90 S-D: Data tab scoping → `DataStorageTab.tsx`, `DataStorageERD.tsx`, `DataModelERD.tsx` (note: `DataStorageERD.tsx` is dead code, not imported anywhere — actual ERD is `DataModelERD.tsx`)
- [x] F90 S-E: Lineage scoping → `GlobalLineagePage.tsx`, `LineageGraph.tsx` (note: `LineageTab.tsx` is dead code, not wired into any route — flagged for future cleanup, not deleted here)
- [x] F90 S-F: Docs page scoping → `DocsPage.tsx`
- [x] F90 S-G: Explain page scoping → `ExplainPage.tsx`, `components/Explain/*`
- [x] F90 S-H: remove the `activeTab === "plan"` conditional in `JobDetailPage.tsx`, scope the shell unconditionally
- [x] F90 S-I: full manual smoke test, light + dark, all surfaces
- [x] F90 S-J: `make tsc-check && make frontend-lint && make frontend-build && make test` exit 0

**Manifest design system — follow-up (not yet scheduled)**
- [x] `BlockPlanTable.tsx`'s Strategy column chip colors unified with the tone system — the pill
  *shape* was already fixed in F89; this pass fixed the remaining hardcoded `manual`/
  `translated_with_review` colors (now `--tone-danger`/`--tone-warning`) plus the same duplication
  in the "Active stat filter chip." The `translated` branch's blue is a confirmed-deliberate
  exception (matches the approved mockup's Steps table) and was left untouched
- [x] Deleted `components/JobDetail/LineageTab.tsx` — confirmed dead code (no imports anywhere),
  the real Lineage surface is `GlobalLineagePage.tsx` → `LineageGraph.tsx`
- [x] `blockStatusHelpers.ts`'s `STATUS_CONFIG` hand-rolled colors — fixed as a follow-up to F90
  (see below)
- [x] Correction: `LineageGraph.tsx`'s `STATUS_STYLE`/`STATUS_SYMBOL` was previously described here
  as "no dark-mode handling at all" — wrong, checked live in the browser and the graph renders
  fine in dark mode (fixed-light node cards by design, same pattern `TargetGraph.tsx` already
  uses). The real bug, and it's in **both** files: `TargetGraph.tsx`'s `STATUS_COLOR_MAP` has the
  identical stock unmuted hex triad, missed during F90 S-C since that audit only grepped Tailwind
  classes, not inline hex in a JS `Record`. See F91 below for the actual fix.

**F91 — Close out the three remaining F90 design follow-ups → see `docs/plans/F91-design-followups.md`**
- [x] F91 S-A: strengthen the dark-mode card border → `PlanTab.tsx` (found and filed #144 along the
  way — Tailwind's `dark:` variant never worked with this app's theme toggle at all; routed around
  it via a plain `.dark` CSS selector, the same working pattern used elsewhere in this codebase)
- [x] F91 S-B: thread a `container` prop through the shared `Dialog` wrapper → `ui/dialog.tsx`
- [x] F91 S-C: apply `container` at the four dialog usage sites (`BlockCodePopup.tsx`,
  `FileViewPopup.tsx`, `ExplainPage.tsx`, `PlanTab.tsx`) via a shared hook
  (`useBrandManifestContainer`, new file in `lib/`)
- [x] F91 S-D: fix `TargetGraph.tsx`'s hardcoded status colors (`STATUS_COLOR_MAP`, the
  progress-bar fill colors, and the `FILE_STATUS_ENTRIES` legend — three occurrences)
- [x] F91 S-E: fix `LineageGraph.tsx`'s hardcoded status colors (`STATUS_STYLE`/`STATUS_SYMBOL`,
  plus a third duplicate in the `STATUS_ENTRIES` legend found via live verification)
- [x] F91 S-F: full manual smoke test, light + dark — verified live against a real job (summary
  card border, all four dialogs, both graph components); no regressions found
- [x] F91 S-G: `make tsc-check && make frontend-lint && make frontend-build && make test` exit 0

**F92 — Fix the migration upload flow → see `docs/plans/F92-migration-upload-flow-fixes.md`
(tracks issue #148's concrete, ready-to-build half; the welcome-page/sidebar half of #148 needs
its own design pass first)**
- [x] F92 S-A: delete dead `UploadPage.tsx` (unrouted since the 2026-04-23 Upload→Dialog decision,
  never removed)
- [x] F92 S-B: stop requiring a reconciliation target to enable Migrate — `submitDisabled`
  incorrectly requires `refTargetPath`, though the backend treats it as optional
- [x] F92 S-C: clarify reconciliation-target UX copy (optional; zip uploads need the reference
  file bundled inside the zip) — also added a live warning for the silent-failure case (target set
  on a file outside the zip)
- [x] F92 S-D: apply Manifest design system styling to the dialog — found and fixed a real
  container-resolution timing bug along the way (`useBrandManifestContainer()`'s approach doesn't
  work when called at the same component's top level as its own `.brand-manifest` div; fixed with
  a callback-ref-via-state pattern instead)
- [ ] F92 S-E: full manual smoke test
- [ ] F92 S-F: `make tsc-check && make frontend-lint && make frontend-build && make test` exit 0

**Plan tab effort estimate looks off (found during demo prep, not yet investigated)**
- [ ] The "Before you accept" panel's "Estimated effort: ~Xh" figure looked wrong on the
  Biometrics Demo (SDTM→ADaM) job — needs investigation into where it's actually computed. Traced
  so far: `migration_planner.py`'s `AnalysisAgent` only assigns a coarse per-block
  `estimated_effort: "low"|"medium"|"high"` label (see ~line 106, 137, 334) — the aggregate hour
  figure shown in the UI must be computed by mapping/summing these bands somewhere else (not yet
  located; check `docs/plans/latest/` for the F86 estimation-model plan, and search the frontend
  and `src/backend/api/` for where `estimated_effort` bands get turned into a number of hours).
  Confirm the mapping/formula is reasonable before trusting this number in front of stakeholders.

**Running-migration UX (found during demo prep, not yet scoped into a plan)**
- [ ] While a job is `queued`/`running`, the Migrations list only shows a plain-text status label
  (no progress, phase, or ETA) and there's nothing to look at on the job detail page in the
  meantime — a submitter has no feedback beyond "wait and refresh." Needs its own design pass:
  candidates include a phase indicator (parse → translate → reconcile, mirroring the trace/phase
  events the worker already emits — see `_active_phase`/`tracer.emit("phase_start"/"phase_done")`
  in `src/worker/main.py`), a progress bar, or a live-updating step count. Should reuse the
  existing trace/SSE stream (`GET /jobs/{id}/trace/stream`) if it already carries this data rather
  than inventing a new signal.

**Compute backend correctness (existing GitHub issues)**
- [ ] #139: README misstates both compute backends — `CLOUD=true` claims Databricks/PySpark but
  `factory.py` raises `NotImplementedError` (no `databricks.py`); `CLOUD=false` claims
  pandas/PostgreSQL but `local.py` uses in-memory `sqlite3`
- [ ] #140: `CLOUD=true` accepted at worker startup, only fails after a job is marked running
  (`main.py:369` → `main.py:1253`) — should be rejected in `worker_settings` validation instead

**Service delivery documentation (existing GitHub issues)**
- [ ] #109: Define ADC SAS migration delivery kit
- [ ] #75: Define knowledge transfer guide
- [ ] #73: Define acceptance criteria spec
- [ ] #72: Define statement of work template
- [x] #71: Define estimation model — scoping report → consultant effort → delivered as F86 (PR #129)
- [ ] #70: Define discovery questionnaire — pre-engagement client intake

**Business development (existing GitHub issues)**
- [ ] #54: Create a representative SAS project for end-to-end testing (assigned: felix-adc)
- [ ] #83: Presentation at private AI/BI network in FS
- [ ] #82: Find a real life client
- [ ] #80: Vision deck — lead presentation for SAS-to-Python migration service

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

- [x] F74: Databricks deployment guide + DLT handoff bundle — `databricks.yml`, `transformations/*_dlt.py`, `DEPLOYMENT_GUIDE.md` in every accepted job's zip; canonical guide at `docs/service-delivery/`
- [ ] F75: Accept-time deployment questionnaire + cloud-aware bundle — popup on Accept asks cloud provider (Azure/AWS/GCP) + ingestion approach + compute mode; answers persist in `user_overrides` and parameterise the F74 bundle (replaces hardcoded Azure `abfss://`). See `docs/plans/latest/F75-deployment-target-questionnaire.md`
- [x] fix(bundle): fold same-table writer chains — multiple blocks writing the same dataset (build + in-place proc sort / data-step rewrite) now fold into one `@dlt.table` / one Spark Job task; eliminates duplicate decorators and last-writer-wins module overwrite
- [x] feat(bundle): modularize DLT pipeline — one `transformations/<source_stem>_dlt.py` per SAS source file; `libraries` in `databricks.yml` lists all files sorted
- [x] feat(bundle): group Spark Job modules by source-file subfolder — `jobs/<source_stem>/<table>.py`; YAML `python_file` paths updated to match
- [x] feat(bundle): YAML readability — shared `_format_yaml` helper inserts blank lines between top-level sections in both YAML renderers
- [ ] F14: Authentication & SSO (SAML/OIDC, JWT, RBAC)
- [ ] `DatabricksBackend` (PySpark) (`src/worker/compute/databricks.py`)
- [ ] End-to-end test: CLOUD=true, Databricks connection
- [ ] MS SQL Server DDL dialect in Data tab — add `dialect` param to `generate_create_table()` in `src/worker/engine/ddl_generator.py` (NVARCHAR(MAX), FLOAT, DATETIME2, BIT, dbo schema prefix), expose as second DDL field in schema response, add dropdown in `DataStorageTab.tsx`. Gate behind MS SQL compute backend being available.
