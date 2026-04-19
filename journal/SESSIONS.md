# Session Journal

Most recent session on top. Each entry should answer:

- What did we do?

---

## 2026-04-19 — F2 agentic workflow planning + TensorZero design

**Duration:** ~2h | **Focus:** Architecture design, no code

### Done

- Designed full agentic pipeline to replace the stateless single-prompt LLM loop
- Defined 6 LLM agents: `AnalysisAgent`, `MacroResolverAgent`, `DataStepAgent`, `ProcAgent`, `FailureInterpreterAgent`, `DocumentationAgent`
- Defined non-LLM components: `MacroExpander`, `TranslationRouter`, `StubGenerator`, `RefinementLoop`
- Established deterministic routing rule: `match block.block_type → agent`, never an LLM decision
- Designed `JobContext` as shared typed object flowing through all agents (windowed for translation agents)
- Integrated TensorZero gateway as 5th Docker service for cost/rate control, replacing in-process counters
- Chose Postgres-only TensorZero backend (no ClickHouse needed for rate limiting)
- Per-job circuit breaker: 40 LLM calls/job via TensorZero `model_inferences_per_hour` rule scoped by `job_id` tag
- Defined `StubGenerator` for explicit untranslatable stubs with `human_review_required` flag
- Wrote formal plan `docs/plans/F2-agentic-workflow.md` with 12 subtasks across 4 phases
- Updated `journal/BACKLOG.md` with all F2 subtasks

### Decisions

- **Agentic pipeline replaces single LLM loop:** 6 specialist LLM agents + deterministic non-LLM components replace the generic `LLMClient.translate()` loop; improves quality via shared context and specialization · revisit never
- **TensorZero gateway for cost controls:** budget enforcement externalized to TensorZero container; no in-process counters in worker; circuit breaker = TensorZero 429 caught by worker · revisit if TensorZero adds overhead
- **Postgres-only TensorZero backend:** ClickHouse deferred; Postgres sufficient for rate limiting and basic cost tracking in MVP · revisit when full observability UI is needed
- **TranslationRouter is deterministic:** routing is `match block.block_type`, never an LLM call; prevents latency/cost/failure-mode creep · revisit never
- **StubGenerator makes failure explicit:** untranslatable blocks produce `# SAS-UNTRANSLATABLE + # TODO` stub with `human_review_required=True`; silent failures removed · revisit never
- **JobContext windowed for translation agents:** specialists receive only their block + relevant macro/dependency slice; `AnalysisAgent` and `DocumentationAgent` get full source · revisit if context window costs change significantly

### Open Questions

- none

### Next Session — Start Here

1. Implement F2 Phase A: `git checkout -b feat/F2-agentic-workflow` then S00 (TensorZero infra), S01 (`JobContext` model), S02 (`MacroExpander`), S03 (`AnalysisAgent`)
2. Reference `docs/plans/F2-agentic-workflow.md` for exact file paths and acceptance criteria

### Files Touched

- `docs/plans/F2-agentic-workflow.md` (new — full feature plan)
- `journal/BACKLOG.md` (F2 subtasks added under Phase 2)
- `journal/SESSIONS.md` (this entry)
- `journal/DECISIONS.md` (architectural decisions appended)

---

## 2026-04-19 — LineageGraph UX overhaul, sonner toasts, file_count fix, undo/redo

**Duration:** ~3h | **Focus:** LineageGraph interactivity, error UX, backend bug fixes

### Done

- **LineageGraph hover-to-focus**: replaced click-to-focus with `onNodeMouseEnter`/`onNodeMouseLeave`; 80ms debounce prevents flicker; pane click clears
- **Undo/Redo toolbar**: `onNodeDragStop` snapshots `{id→{x,y}}` position maps (deep-copied to avoid mutation); Undo/Redo restore via `setNodes` (controlled-mode setter — `rfSetNodes` was clobbered by React Flow's controlled-mode render loop); Reset restores initial dagre layout + `fitView`
- **Opacity transition**: `transition: "opacity 0.18s ease"` on all nodes for smooth hover-dim effect
- **Legend → top-right, toolbar → top-left**: repositioned overlays
- **Untranslatable status bug fixed**: `parser.py` was checking `"# SAS-UNTRANSLATABLE" in block.raw_sas` (always false); fixed to `block.block_type == BlockType.UNTRANSLATABLE`
- **file_count fixed**: was counting only non-sentinel keys (`.sas` only); now `len(j.files or {})` counts all accepted files (SAS + CSV/log/xlsx reference sentinels)
- **Jobs table row disabled for non-done**: running/queued/failed rows are `cursor-default opacity-70`, non-clickable; only `done` rows navigate to detail page
- **Sonner toast for all errors**: shadcn sonner component installed; `<Toaster>` added to App root; all `onError` callbacks and failed-job status wired to `toast.error()`; removed all inline red text error displays
- **Human-friendly error copy**: generic fallbacks rewritten ("Your changes could not be saved. Please try again."), raw technical strings never shown to user; `extractApiError` continues to pass through clean FastAPI messages verbatim

### Decisions

- Controlled-mode `setNodes` is the only correct setter for position restores in React Flow — `rfSetNodes` (instance) gets clobbered by the nodes prop on re-render
- `file_count` now counts all keys including reference sentinels (they are user-uploaded files)
- Sonner hardcoded to `theme="light"` — no `next-themes` in this Vite SPA

### Open Questions

- None

### Next Session — Start Here

1. Apply pending Alembic migrations if not yet done: `docker compose exec backend uv run alembic upgrade head`
2. S-BE5: `PUT /jobs/{id}/python_code` re-reconciliation + `skip_llm` worker branch
3. S-BE6: `POST /jobs/{id}/refine` + `parent_job_id`
4. S-FE7/8/9: GlobalLineagePage, DocsPage, ExplainPage stub

### Files Touched

- `src/frontend/src/components/LineageGraph.tsx` (hover-to-focus, undo/redo/reset, smooth opacity, layout repositioning)
- `src/frontend/src/components/ui/sonner.tsx` (new — fixed generated file, no next-themes)
- `src/frontend/src/components/JobResult.tsx` (human-friendly error copy)
- `src/frontend/src/pages/UploadPage.tsx` (useEffect toast for failed job, mutation onError, remove inline errors)
- `src/frontend/src/pages/JobDetailPage.tsx` (mutation onError toasts, lineage error toast, remove inline errors)
- `src/frontend/src/pages/JobsPage.tsx` (non-done rows non-clickable)
- `src/frontend/src/App.tsx` (Toaster added)
- `src/worker/engine/parser.py` (untranslatable status bug fix)
- `src/backend/api/routes/jobs.py` (file_count counts all keys)

---

## 2026-04-19 — UI polish: mandatory name, merged editor, lineage DAG upgrade

**Duration:** ~3h | **Focus:** JobDetailPage UX, LineageGraph dagre rewrite, UploadPage, JobsPage, backend fixes

### Done

- **Mandatory migration name**: `submitDisabled` blocks on empty name; `(optional)` label removed; `required` attr on input
- **cursor-pointer audit**: added throughout UploadPage, JobDetailPage, tabs.tsx, AppSidebar
- **Merged Editor tab**: Comparison + Edit collapsed into one "Editor" tab — SAS read-only Monaco left, editable Python Monaco right, save/refine below
- **JobDetailPage header**: shows `job.name` as primary label, short ID as mono sub-line; `name` added to `JobStatusResponse` schema and `GET /jobs/{id}`
- **JobsPage**: column renamed "Migration" → "Name"; cell shows name only; `file_count` renders via `!= null` guard
- **UploadPage result card**: accepted/rejected file lists removed (cleaner post-submit UX)
- **Zip filter**: `._` macOS resource fork files and `__MACOSX/` entries silently skipped in `_unpack_zip`
- **LineageGraph dagre rewrite**: `dagre` + `@types/dagre` installed; LR layout (nodesep 40, ranksep 80); `useNodesState`/`useEdgesState` with `useEffect` seeding; click-to-focus dims unrelated nodes (ancestor+descendant closure); legend overlay (semi-transparent + backdrop blur); MiniMap only >15 nodes; `Position` enum for sourcePosition/targetPosition; no TS errors
- **Makefile fix**: `frontend-lint` and `frontend-build` targets no longer pass `NPM_FLAGS` to ESLint/Vite CLIs (ESLint v9 flat config and Vite reject `--silent`)
- **vite.config.ts**: `chunkSizeWarningLimit: 1000` to suppress Monaco chunk size warning

### Decisions

- Editor tab merges comparison + edit: single tab is cleaner — users naturally want to see SAS while editing Python
- `._` files skipped silently (not rejected) — macOS OS artefacts, not user files
- `file_count` sentinel pattern: count keys not matching `__…__` (SAS files only); legacy jobs show "—" gracefully

### Open Questions

- DB migrations (004/005 for name, lineage, doc columns) not yet applied to running Postgres — API returns no `name`/`file_count` for existing jobs; needs `alembic upgrade head` on next deploy

### Next Session — Start Here

1. Apply pending Alembic migrations: `docker compose exec backend uv run alembic upgrade head`
2. Implement S-BE5 (`PUT /jobs/{id}/python_code` re-reconciliation + `skip_llm`)
3. Implement S-BE6 (`POST /jobs/{id}/refine` + `parent_job_id`)
4. Implement S-FE7 `GlobalLineagePage`, S-FE8 `DocsPage`, S-FE9 `ExplainPage` stub

### Files Touched

- `src/frontend/src/pages/UploadPage.tsx` (mandatory name, removed accepted/rejected lists)
- `src/frontend/src/pages/JobDetailPage.tsx` (merged Editor tab, name in header)
- `src/frontend/src/pages/JobsPage.tsx` (column rename, name cell, file_count guard)
- `src/frontend/src/components/LineageGraph.tsx` (full dagre rewrite)
- `src/frontend/src/components/ui/tabs.tsx` (cursor-pointer)
- `src/frontend/src/api/types.ts` (name on JobStatus)
- `src/frontend/src/api/jobs.ts` (updateJobPythonCode, refineJob, downloadJob stubs)
- `src/backend/api/schemas.py` (name on JobStatusResponse)
- `src/backend/api/routes/jobs.py` (name in get_job, file_count sentinel fix)
- `src/backend/api/routes/migrate.py` (._/MACOSX zip filter)
- `src/frontend/package.json` + `package-lock.json` (dagre, @types/dagre)
- `src/frontend/vite.config.ts` (chunkSizeWarningLimit)
- `Makefile` (frontend-lint/build no longer pass NPM_FLAGS to CLI)

---

## 2026-04-18 — JobDetailPage + UploadPage workspace + name/file_count + markdown doc

**Duration:** ~3h | **Focus:** S-FE1–4, S-FE6, S-BE3, S-BE4, upload UX fixes, name field

### Done

- **S-FE1–4**: `MonacoDiffViewer`, `MonacoEditor`, `TiptapEditor`, `LineageGraph` components created; npm packages installed (`@monaco-editor/react`, `@tiptap/*`, `lowlight`, `reactflow`, `jszip`)
- **S-FE6**: `JobDetailPage` — 4 tabs (Comparison/Edit/Report/Lineage), live status polling, Monaco editors, `marked`-rendered doc summary; hand-rolled `Tabs` component (replaced broken shadcn `base-nova` tabs with circular import)
- **S-BE3**: `GET /jobs/{id}/lineage` endpoint + `extract_lineage()` wired into worker; migration 004 adds `lineage JSON` column
- **S-BE4**: `GET /jobs/{id}/doc` endpoint + `DocGenerator` wired into worker post-reconciliation; migration 004 adds `doc TEXT` column
- **UploadPage persistent workspace**: state lifted to `UploadStateProvider`; survives navigation; zip tree client-side parsed (jszip), `__MACOSX` filtered, per-file/folder remove; "Start another" vs "Accept & clear" actions; "Open full details" only when done
- **Migration name**: text input on upload form; stored on `Job` (migration 005); shown in result card and jobs table
- **JobsPage**: "Migration" column shows name + mono ID sub-line; "Files" column shows `file_count`
- **Markdown summary**: LLM doc rendered via `marked` + Tailwind `prose` instead of Tiptap
- 110 tests green, 90.23% coverage

### Decisions

- UploadPage state lifted to context so navigation doesn't reset it
- Tabs hand-rolled (shadcn base-nova depends on uninstalled `@base-ui-components/react`)
- Markdown doc via `marked` + prose (not Tiptap) — simpler, no editor overhead for read-only
- `file_count` derived at query time, not stored
- `name` optional form field on `POST /migrate`, stored as nullable TEXT

### Open Questions

- none

### Next Session — Start Here

1. Implement S-BE5 (`PUT /jobs/{id}/python_code` re-reconciliation pathway + migration 003)
2. Implement S-BE6 (`POST /jobs/{id}/refine` + `parent_job_id` + migration 003)
3. Implement S-FE7 `GlobalLineagePage`, S-FE8 `DocsPage`, S-FE9 `ExplainPage`
4. See `docs/plans/F-UI-postmvp.md` + `docs/plans/F-backend-postmvp.md`

### Files Touched

- `src/frontend/src/components/MonacoDiffViewer.tsx` (new)
- `src/frontend/src/components/MonacoEditor.tsx` (new)
- `src/frontend/src/components/TiptapEditor.tsx` (new)
- `src/frontend/src/components/LineageGraph.tsx` (new)
- `src/frontend/src/components/ui/tabs.tsx` (replaced broken shadcn tabs)
- `src/frontend/src/pages/JobDetailPage.tsx` (full impl)
- `src/frontend/src/pages/UploadPage.tsx` (persistent workspace, name input)
- `src/frontend/src/pages/JobsPage.tsx` (name column, file_count column)
- `src/frontend/src/context/UploadStateContext.tsx` (new — lifted state)
- `src/frontend/src/api/types.ts`, `jobs.ts`, `migrate.ts` (extended)
- `src/frontend/package.json` (new packages)
- `src/backend/db/models.py` (name column)
- `src/backend/api/schemas.py` (name, file_count on JobSummary)
- `src/backend/api/routes/jobs.py` (lineage + doc + file_count endpoints)
- `src/backend/api/routes/migrate.py` (name form field)
- `src/worker/engine/doc_generator.py` (new)
- `src/worker/main.py` (lineage + doc wired)
- `alembic/versions/004_add_lineage_doc_columns.py` (new)
- `alembic/versions/005_add_job_name.py` (new)
- `tests/test_lineage_endpoint.py`, `test_doc_endpoint.py`, `test_doc_generator.py` (new)
- `tests/test_worker_main.py` (extended)

---

## 2026-04-18 — UI polish: JobDetailPage status, sidebar tooltips, cursor, icon stability

**Duration:** ~30min | **Focus:** UI bug fixes on sidebar and job detail page

### Done

- `JobDetailPage`: status badge now fetches real job status via `useQuery` with live polling (queued/running → 3s refetch); uses same black pill style as jobs table
- `AppSidebar` tooltips: replaced native `title` (slow browser delay) with instant CSS opacity tooltip (`duration-100`) appearing to the right of the sidebar
- `AppSidebar` icons: fixed icon drift on expand/collapse — icons now pinned at fixed `left` offset (`ICON_COL=56px`); labels fade via `width`+`opacity`+`margin` transition instead of `max-width` (smoother)
- `AppSidebar` overflow: removed `overflow-hidden` from `<aside>` (was clipping tooltips); moved clip to individual row elements
- `cursor-pointer` added to `Button` base class and sidebar nav/toggle links

### Decisions

- none

### Open Questions

- none

### Next Session — Start Here

1. Install npm packages: `@monaco-editor/react`, `@tiptap/react`, `@tiptap/starter-kit`, `@tiptap/extension-code-block-lowlight`, `lowlight`, `reactflow`
2. Implement S-FE1 (`MonacoDiffViewer`), S-FE2 (`MonacoEditor`), S-FE3 (`TiptapEditor`), S-FE4 (`LineageGraph`)
3. Wire into S-FE6 `JobDetailPage` (replace stub tabs with real data + editor components)
4. In parallel: S-BE3 (lineage + migration 002) + S-BE4 (doc generation)
5. See `docs/plans/F-UI-postmvp.md` + `docs/plans/F-backend-postmvp.md`

### Files Touched

- `src/frontend/src/pages/JobDetailPage.tsx` (real status fetch)
- `src/frontend/src/components/AppSidebar.tsx` (tooltip, icon stability, smooth text transition)
- `src/frontend/src/components/ui/button.tsx` (cursor-pointer)

---

## 2026-04-18 — Post-MVP nav scaffold, backend sources/zip endpoints, unified upload UX

**Duration:** ~2h | **Focus:** S-BE1, S-BE2, S-FE5/10/11/12/13 implementation + bugfixes

### Done

- Branched `feat/F-UI-postmvp` off latest main (rebased after merge of F-UI PR)
- **S-BE1:** `GET /jobs/{id}/sources` — returns job source files, strips `__sentinel__` keys; 6 new tests
- **S-BE2:** Zip bulk upload on `POST /migrate` — `_unpack_zip` helper, 500MB limit, `FileRejection` schema, `accepted`/`rejected` in `MigrateResponse`; tests for all edge cases
- **Bugfix:** `sas_files` changed to `File(default=[])` so FastAPI accepts requests with only `zip_file` (was returning 422 missing field)
- **S-FE5:** `AppSidebar` — collapsible left sidebar with localStorage persistence, 5 nav items, lucide icons
- **S-FE10:** `App.tsx` — replaced top nav with sidebar layout, lazy-loaded routes for all new pages
- **S-FE11:** `JobsPage` — rows navigate to `/jobs/:id`, removed inline expansion
- **S-FE13:** API client extended — new types + `getJobSources`, `getJobLineage`, `getJobDoc`, `updateJobPythonCode`, `refineJob`; `submitMigration` supports zip
- **S-FE12:** `UploadPage` — unified drop-zone accepting all 7 file types, file-type badges, manifest view post-submit; removed conflict check (zip + individual files allowed together)
- Stub pages created: `JobDetailPage` (4-tab layout), `GlobalLineagePage`, `DocsPage`, `ExplainPage`
- 93 tests passing, 91% coverage

### Decisions

- `UploadPage` accepts `.sas`, `.sas7bdat`, `.zip`, `.log`, `.csv`, `.xls`, `.xlsx` in one input — no mode toggle, no conflict restriction between zip and individual files
- Supporting files (`.log/.csv/.xls/.xlsx`) without a zip are accepted by the UI but will be ignored by backend individual-file path (only processed inside zips); frontend shows "Supporting file" amber badge

### Open Questions

- none

### Next Session — Start Here

1. Install npm packages: `@monaco-editor/react`, `@tiptap/react`, `@tiptap/starter-kit`, `@tiptap/extension-code-block-lowlight`, `lowlight`, `reactflow`
2. Implement S-FE1 (`MonacoDiffViewer`), S-FE2 (`MonacoEditor`), S-FE3 (`TiptapEditor`), S-FE4 (`LineageGraph`) — editor component layer
3. Wire into S-FE6 `JobDetailPage` (replace stubs with real tabs + data fetching)
4. In parallel: S-BE3 (lineage extraction + migration 002) + S-BE4 (doc generation)
5. All work in `docs/plans/F-UI-postmvp.md` + `docs/plans/F-backend-postmvp.md`

### Files Touched

- `src/backend/api/schemas.py` (FileRejection, MigrateResponse extended, JobSourcesResponse)
- `src/backend/api/routes/jobs.py` (GET /sources)
- `src/backend/api/routes/migrate.py` (zip support, File(default=[]) fix)
- `src/backend/core/config.py` (max_zip_bytes)
- `tests/test_sources_endpoint.py` (new)
- `tests/test_zip_upload.py` (new)
- `src/frontend/src/api/types.ts` (new types)
- `src/frontend/src/api/jobs.ts` (new functions)
- `src/frontend/src/api/migrate.ts` (zip support)
- `src/frontend/src/components/AppSidebar.tsx` (new)
- `src/frontend/src/App.tsx` (sidebar layout, new routes)
- `src/frontend/src/pages/JobsPage.tsx` (navigate to /jobs/:id)
- `src/frontend/src/pages/UploadPage.tsx` (unified drop-zone)
- `src/frontend/src/pages/JobDetailPage.tsx` (stub, new)
- `src/frontend/src/pages/GlobalLineagePage.tsx` (stub, new)
- `src/frontend/src/pages/DocsPage.tsx` (stub, new)
- `src/frontend/src/pages/ExplainPage.tsx` (stub, new)
- `docs/plans/F-UI-postmvp.md` (subtasks marked done)
- `docs/plans/F-backend-postmvp.md` (subtasks marked done)
- `journal/BACKLOG.md` (items checked off)

---

## 2026-04-18 — Post-MVP UI + backend planning; zone-based architecture designed

**Duration:** ~1.5h | **Focus:** Planning session — no code written

### Done

- Reviewed all user stories (US1, US2), features (F2, F5–F7, F11, F13, F15, F18), and MVP scope docs
- Explored full frontend codebase (all components, pages, API client, package.json) and backend API surface
- Ran fullstack-planner analysis: identified all API gaps for post-MVP features (sources endpoint, lineage column, doc column, re-reconciliation, refine action, zip upload)
- Designed zone-based editor architecture: right tool per content zone (Monaco DiffEditor / Monaco Editor / Tiptap / React Flow)
- Decided full app page structure with sidebar nav: `/upload`, `/jobs`, `/jobs/:id`, `/lineage`, `/docs`, `/explain`
- Wrote `docs/plans/F-UI-postmvp.md` (13 frontend subtasks, Status: in-progress)
- Wrote `docs/plans/F-backend-postmvp.md` (6 backend subtasks across 3 DB migration waves, Status: in-progress)
- Updated `journal/BACKLOG.md` with 19 new actionable items cross-linked to plan files

### Decisions

- Zone-based editor: Monaco DiffEditor (diff), Monaco Editor (edit), Tiptap (notes/reports), React Flow (lineage)
- Sidebar nav (collapsible) replaces current top nav
- `/jobs/:id` full page with 4 tabs replaces inline expansion
- Zip upload: partial acceptance (no file count limit); rejected files returned in manifest, not as 400
- Accepted zip extensions: `.sas`, `.sas7bdat`, `.csv`, `.log`, `.xlsx`, `.xls`
- Lineage serialised to `job.lineage` JSON column at parse time (not on-demand)
- `skip_llm` boolean flag for re-reconciliation pathway (cleaner than new status value)

### Open Questions

- none

### Next Session — Start Here

1. Two parallel tracks to start immediately:
   - **Backend track:** implement S-BE1 (`GET /sources`) and S-BE2 (zip upload) in `src/backend/` — no migrations required, unblocks frontend Monaco work
   - **Frontend nav track:** implement S-FE5 (`AppSidebar`) + S-FE10 (routing) + S-FE11 (JobsPage refactor) — no backend deps
2. Full subtask list in `docs/plans/F-UI-postmvp.md` and `docs/plans/F-backend-postmvp.md`
3. Branch: `feat/F-UI-postmvp`

### Files Touched

- `docs/plans/F-UI-postmvp.md` (created)
- `docs/plans/F-backend-postmvp.md` (created)
- `journal/BACKLOG.md` (19 new items added)
- `journal/DECISIONS.md` (9 decisions appended)
- `journal/SESSIONS.md` (this entry)

---

## 2026-04-18 — F-UI complete; MVP shipped; Azure OpenAI + Docker fixes

**Duration:** ~4h | **Focus:** F-UI React frontend, docker-compose runtime fixes, Azure OpenAI wiring

### Done

- **F-UI — backend:** `GET /jobs` list endpoint + `JobSummary`/`JobListResponse` schemas; `CORSMiddleware` with env-driven `CORS_ORIGINS`; `cors_origins` as split-string property to handle `CORS_ORIGINS=*` from env
- **F-UI — frontend:** typed API client (`src/api/`), `UploadPage`, `JobsPage`, `JobResult` component with React Query polling; react-router-dom routing; `@tanstack/react-query` server state
- **Docker runtime fixes:** `entrypoint.sh` runs `alembic upgrade head` before uvicorn; migration 001 fixed (`postgresql.UUID` → `String(36)` to match ORM); frontend volume mount for Vite HMR live reload
- **Azure OpenAI:** `AzureProvider` wired in `_make_agent()` when `AZURE_OPENAI_ENDPOINT` is set; provider prefix stripped from `LLM_MODEL` to get bare deployment name; new worker settings: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `OPENAI_API_VERSION`
- **`.env.example`:** full documentation of all env vars with comments; both `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` included
- **UI polish:** status labels renamed (Queued/Running/Completed/Failed); shimmer text effect (3.5s, black pill) for active statuses; no colour-coding
- **Verified end-to-end:** Azure gpt-5.4 deployment returned 200 OK; job completed successfully in Docker Compose

### Decisions

- **`CORS_ORIGINS` as plain string, split internally:** `list[str]` pydantic-settings field fails when env var is `*`; switched to `str` field with `@property` that splits on comma — avoids JSON bracket requirement in `.env` · revisit never
- **Migration 001 id column as String(36):** ORM uses `String(36)` for cross-dialect SQLite/PostgreSQL compatibility in tests; migration was incorrectly using `postgresql.UUID` causing type mismatch on INSERT · revisit never
- **Backend entrypoint runs migrations on startup:** `alembic upgrade head` in `entrypoint.sh` before uvicorn ensures schema is always current without a separate migration step · revisit if migration time becomes a startup concern
- **Azure deployment name stripped of provider prefix:** `LLM_MODEL=openai:gpt-5.4` → deployment name `gpt-5.4`; `split(":", 1)[-1]` handles both bare and prefixed values · revisit never
- **Frontend volume mount for HMR:** `./src/frontend:/app` + `/app/node_modules` anonymous volume in docker-compose; Vite picks up file changes without container rebuild · revisit never

### Open Questions

- none

### Next Session — Start Here

1. MVP is complete — all Phase 1 items done. Consider opening PRs for `feat/F-UI` → main
2. Phase 2 candidates: `%MACRO`/`%MEND` expansion, row-level hash diff, SAS log ingestion
3. Run `/plan-feature` for whichever Phase 2 item to tackle next

### Files Touched

- `src/backend/main.py`
- `src/backend/core/config.py`
- `src/backend/api/routes/jobs.py`
- `src/backend/api/schemas.py`
- `src/backend/Dockerfile`
- `src/backend/entrypoint.sh` (created)
- `src/worker/core/config.py`
- `src/worker/engine/llm_client.py`
- `alembic/versions/001_create_jobs_table.py`
- `docker-compose.yml`
- `src/frontend/package.json`
- `src/frontend/package-lock.json`
- `src/frontend/src/main.tsx`
- `src/frontend/src/App.tsx`
- `src/frontend/src/api/types.ts` (created)
- `src/frontend/src/api/migrate.ts` (created)
- `src/frontend/src/api/jobs.ts` (created)
- `src/frontend/src/pages/UploadPage.tsx` (created)
- `src/frontend/src/pages/JobsPage.tsx` (created)
- `src/frontend/src/components/JobResult.tsx` (created)
- `docs/plans/F-UI.md` (created)
- `journal/BACKLOG.md`

## 2026-04-18 — F-LLM + F-sas7bdat complete; git-branch-setup skill; make test hardened

**Duration:** ~3h | **Focus:** two remaining backend MVP items + tooling improvements

### Done

- **git-branch-setup skill:** new `.claude/skills/git-branch-setup/SKILL.md` — checks local + remote for feature branch, pulls main, creates branch if missing, confirms checkout before any implementation is delegated; wired into orchestrator feature planning (step 6 after plan approval)
- **F-LLM — system prompt upgrade:** expanded `_SYSTEM_PROMPT` in `src/worker/engine/llm_client.py` with full SAS construct coverage (DATA step, PROC SQL, PROC SORT, %LET), PySpark idiom rules, and PROC SORT → `sort_values()` mapping
- **F-LLM — retry + resilience:** `LLMTranslationError` exception with `is_transient` flag; 3-attempt exponential retry (2/4/8s) in `LLMClient.translate()`; transient vs permanent error classification; partial result accumulation in `_process_job()` with early return and structured `error_detail` JSON persisted to the job row
- **F-LLM — DB:** `error_detail: Mapped[dict[str, Any] | None]` JSON column added to `Job` model; Alembic migration `003_add_error_detail_to_jobs.py`
- **F-sas7bdat — ComputeBackend:** abstract `read_sas7bdat()` added to `src/worker/compute/base.py`; implemented in `src/worker/compute/local.py` via `pyreadstat.read_sas7bdat()`
- **F-sas7bdat — /migrate route:** accepts optional `ref_dataset: UploadFile | None`; validates `.sas7bdat` extension; saves binary to `upload_dir` on disk; stores path under `__ref_sas7bdat__` in `job.files`; `upload_dir` setting added to `src/backend/core/config.py`
- **F-sas7bdat — pipeline:** worker extracts `__ref_sas7bdat__` from `job.files`; `ReconciliationService.run()` always executes the pipeline, then skips comparison checks if no reference supplied; sas7bdat takes priority over csv
- **make test hardened:** mypy now runs inside `make test` (was only in `make check` and pre-commit); `make test-file FILE=<path>` target added for single-file runs; `pyreadstat` + `src.worker.compute.local` mypy overrides added to `pyproject.toml`
- **Tests:** 3 new LLM retry tests, 1 sas7bdat backend test, 2 migrate route tests — **86 tests total, 91.64% coverage**

### Decisions

- **`make test` now includes mypy:** discovered that mypy failures were only caught at pre-commit time, not during the test cycle; added to `make test` to surface errors earlier · revisit never
- **git-branch-setup always pulls main before branching:** ensures new feature branches start from the latest main, not from a stale local HEAD · revisit never
- **No Co-Authored-By attribution in commits:** user preference; removed from all commit messages and memory · revisit never

### Open Questions

- none

### Next Session — Start Here

1. F-UI is the last remaining MVP item — Upload & Results page (React frontend)
2. Run `/plan-feature` for F-UI, then delegate to `frontend-builder`
3. Both F-LLM (`feat/F-llm-resilience`) and F-sas7bdat (`feat/F-sas7bdat`) branches are ready to open PRs — consider merging before starting F-UI to keep main up to date

### Files Touched

- `.claude/skills/git-branch-setup/SKILL.md` (created)
- `.claude/agents/orchestrator.md`
- `CLAUDE.md`
- `Makefile`
- `pyproject.toml`
- `src/worker/engine/llm_client.py`
- `src/worker/main.py`
- `src/backend/db/models.py`
- `alembic/versions/003_add_error_detail_to_jobs.py` (created)
- `src/worker/compute/base.py`
- `src/worker/compute/local.py`
- `src/backend/api/routes/migrate.py`
- `src/backend/core/config.py`
- `src/worker/validation/reconciliation.py`
- `tests/test_llm_client.py`
- `tests/test_local_backend.py`
- `tests/test_migrate_route.py` (created)

---

## 2026-04-18 — F1-ext complete: PROC SORT + %LET, MVP scope alignment

**Duration:** ~2h | **Focus:** F1 engine extension + structural doc cleanup

### Done

- **F1-ext — PROC SORT parser:** `BlockType.PROC_SORT`, `_extract_proc_sort()` with `DATA=`/`OUT=` resolution, covered-span logic so PROC SORT no longer hits UNTRANSLATABLE
- **F1-ext — %LET macro vars:** `MacroVar` + `ParseResult` models, `_extract_macro_vars()`, `SASParser.parse()` return type changed to `ParseResult(blocks, macro_vars)`, `CodeGenerator.assemble()` accepts `macro_vars` and prepends constants section
- **Sample files:** `samples/proc_sort_example.sas`, `samples/proc_sort_expected.csv`
- **Tests:** 9 new parser unit tests, 2 codegen tests, 1 reconciliation test — 78 total, 93.5% coverage
- **Doc alignment:** renamed `docs/plans/F2-proc-sort.md` → `F1-ext-proc-sort-macro.md` (PROC SORT is an F1 extension, not a new feature; F2 is reserved for Code Explanation UI)
- **MVP scope expanded:** added F-LLM (system prompt upgrade + graceful degradation), F-sas7bdat (wire pyreadstat), F-UI (Upload & Results page) as required MVP items to `docs/mvp-scope.md` and `journal/BACKLOG.md`
- **git-pr-summary skill:** new skill at `.claude/skills/git-pr-summary/SKILL.md` — generates copy-paste ready PR Markdown; wired into orchestrator only
- **README updated:** parser description, reconciliation test listing, worker pipeline signature updated to reflect F1-ext changes

### Decisions

- **F-number collision resolved:** PROC SORT + %LET are F1 extensions (Phase 2 post-MVP backend). F2 remains the Code Explanation Assistant UI (Phase 3 frontend) per `docs/features.md` · revisit never
- **MVP requires a frontend:** Upload & Results page added to MVP scope — product is not shippable without UI
- **MVP requires LLM system prompt upgrade:** current prompt only mentions pandas; must establish agent as SAS migration expert targeting Python/PySpark · LLM remains the primary translation engine, not optional
- **MVP requires sas7bdat reading:** `pyreadstat` already in `pyproject.toml` but never wired; must be connected to `LocalBackend` before MVP is done
- **LLM resilience is MVP scope:** worker must not crash if API unreachable — graceful job failure, not process crash · this is error handling, not a fallback translation path
- **make test is the only allowed test invocation:** `uv run pytest` is forbidden everywhere including agent verification steps — all tests via make targets only · enforced in memory

### Open Questions

- none

### Next Session — Start Here

1. Implement the three remaining MVP items in order:
   - F-LLM: upgrade `_SYSTEM_PROMPT` in `src/worker/engine/llm_client.py` + lazy-init resilience → plan and delegate to `backend-builder`
   - F-sas7bdat: wire `pyreadstat` into `src/worker/compute/local.py` + `base.py` + worker routing → plan and delegate to `backend-builder`
   - F-UI: Upload & Results page → plan and delegate to `frontend-builder`
2. F-LLM and F-sas7bdat can be planned and built in parallel
3. F-UI follows after both backend items are green

### Files Touched

- `src/worker/engine/models.py`, `src/worker/engine/parser.py`, `src/worker/engine/codegen.py`
- `src/worker/main.py`
- `tests/test_parser.py`, `tests/test_codegen.py`, `tests/reconciliation/test_proc_sort.py`
- `samples/proc_sort_example.sas`, `samples/proc_sort_expected.csv`
- `docs/plans/F1-ext-proc-sort-macro.md` (created), `docs/plans/F2-proc-sort.md` (deleted)
- `docs/mvp-scope.md`, `journal/BACKLOG.md`, `journal/DECISIONS.md`, `journal/SESSIONS.md`
- `.claude/skills/git-pr-summary/SKILL.md` (created), `.claude/agents/orchestrator.md`, `CLAUDE.md`
- `README.md`

---

## 2026-04-18 — CI hardening: Tailwind v4 migration, action bumps, Docker cache

**Duration:** ~3h | **Focus:** CI green across all jobs; tooling correctness

### Done

- **Tailwind v3 → v4:** switched to `@tailwindcss/vite` plugin, removed `postcss.config.js` and `tailwind.config.js`, moved theme into `@theme` block in `index.css`; fixed `border-border` / `outline-ring/50` errors caused by shadcn v4 generating v4 CSS against v3
- **tsconfig fix:** removed `baseUrl` from root `tsconfig.json` (redundant in project-references setup); kept `baseUrl` + `ignoreDeprecations: "6.0"` in `tsconfig.app.json` as required anchor for `paths` in `tsc --noEmit` mode
- **Build script:** changed `tsc -b` → `tsc --noEmit` in `package.json` build script and CI — `tsc -b` (project references build mode) doesn't resolve `paths` without `composite: true`, which conflicts with `noEmit: true`
- **no-commit-to-branch hook:** added `pre-commit-hooks` `no-commit-to-branch` for `main` to `.pre-commit-config.yaml`
- **make test extended:** now runs `tsc --noEmit`, `npm run lint`, and `npm run build` — frontend errors caught locally
- **CI action bumps:** all actions bumped to Node 24 compatible versions; `astral-sh/setup-uv` pinned to `v8.1.0` (no floating major tag)
- **CI structure:** docker job made independent (no longer gated on `test`); reconciliation coverage scoped to `src/worker/validation` with 80% gate via `.coveragerc-reconciliation`; ESLint step added to frontend CI job
- **.dockerignore:** added to reduce build context for backend/worker images and improve GHA layer cache hit rate

### Decisions

- `tsc --noEmit` is the correct type-check command for this project — `tsc -b` requires `composite: true` which conflicts with `noEmit: true`
- `baseUrl` + `ignoreDeprecations: "6.0"` required in `tsconfig.app.json` — `pathsBasePath` is not propagated when loaded as a referenced project
- Docker build job runs independently of Python test jobs — Dockerfile correctness is unrelated to Python logic
- Reconciliation coverage gated separately at 80% on `src/worker/validation` only; main test suite gate remains 90% on all of `src`

### Open Questions

- none

### Next Session — Start Here

1. Phase 2 features — run `/session-start` → confirm backlog → `/plan-feature` for PROC SORT parser or `%LET` macro resolution

### Files Touched

- `.pre-commit-config.yaml`, `Makefile`, `.github/workflows/ci.yml`
- `.dockerignore`, `.coveragerc-reconciliation`
- `src/frontend/package.json`, `src/frontend/package-lock.json`
- `src/frontend/vite.config.ts`, `src/frontend/src/index.css`
- `src/frontend/tsconfig.json`, `src/frontend/tsconfig.app.json`
- `src/frontend/src/components/ui/button.tsx`
- `scripts/check_npm_lockfile.sh`
- `journal/SESSIONS.md`, `journal/DECISIONS.md`

---

## 2026-04-18 — F1 complete: S10–S16 + multi-agent setup + tooling hardening

**Duration:** ~4h | **Focus:** F1 pipeline generation — wiring, API endpoints, coverage, agents

### Done

- **S10:** Alembic migration `002_add_llm_model.py` + `Job.llm_model` ORM field
- **S11:** `_process_job` in `src/worker/main.py` — full engine pipeline (SASParser → LLMClient → CodeGenerator → ReconciliationService), `asyncio.to_thread` for sync calls, persists `status=done/failed`
- **S12:** `AuditResponse` Pydantic schema added to `src/backend/api/schemas.py`
- **S13:** `GET /jobs/{id}/audit` endpoint in `src/backend/api/routes/jobs.py`
- **S14:** `GET /jobs/{id}/download` endpoint — StreamingResponse zip with `pipeline.py`, `reconciliation_report.json`, `audit.json`
- **S15:** `tests/test_api_routes.py` — 12 async route tests (audit + download + get_job, all paths)
- **S16:** Coverage raised from 40% → 94.3%; `fail_under = 90`; `concurrency = ["thread", "greenlet"]` for async tracing
- **Agents:** 5 agent files created in `.claude/agents/` (orchestrator, backend-builder, frontend-builder, fullstack-planner, tester)
- **test-runner skill:** `.claude/skills/test-runner/SKILL.md` + CLAUDE.md table updated
- **Tooling:** Makefile PYTEST_FLAGS/NPM_FLAGS/DOCKER_BUILD_FLAGS; `--quiet` everywhere; mypy `tests.*` exemption removed
- **mypy clean:** jinja2 stubs added to ignore list, `no-any-return` fixed in codegen, N806 naming in test mocks fixed
- **5 atomic commits** — all hooks passed

### Decisions

- Multi-agent architecture adopted; orchestrator delegation via Agent tool is mandatory
- `coverage concurrency = ["thread", "greenlet"]` required for async route tracing
- mypy `tests.*` blanket exemption removed — tests now checked under strict mode
- Makefile output globally suppressed via flag variables

### Open Questions

- none

### Next Session — Start Here

1. F1 is complete. Start Phase 2 from `journal/BACKLOG.md`:
   - PROC SORT parser + translation
   - Macro variable (`%LET`) resolution → Python constants
   - Row-level hash diff check (F15 precursor)
2. Run `/session-start` → confirm backlog → `/plan-feature` for next feature

### Files Touched

- `CLAUDE.md`, `Makefile`, `pyproject.toml`
- `.claude/agents/` (5 new files), `.claude/skills/test-runner/SKILL.md`
- `alembic/versions/002_add_llm_model.py`
- `src/backend/db/models.py`, `src/backend/api/schemas.py`, `src/backend/api/routes/jobs.py`
- `src/worker/main.py`, `src/worker/engine/codegen.py`
- `tests/test_api_routes.py`, `tests/test_codegen.py`, `tests/test_factory.py`
- `tests/test_llm_client.py`, `tests/test_local_backend.py`, `tests/test_session.py`, `tests/test_worker_main.py`
- `tests/reconciliation/test_data_step.py`
- `journal/SESSIONS.md`, `journal/BACKLOG.md`, `journal/DECISIONS.md`
- `docs/plans/F1-pipeline-generation.md`

---

## 2026-04-18 — F1 Engine S00–S09: parser, LLM client, codegen, reconciliation

**Duration:** ~3h | **Focus:** F1 pipeline generation — engine layer implementation

### Done

- **S00:** Added `pydantic-ai[anthropic]>=0.0.36` to `pyproject.toml`; `uv.lock` updated
- **S01:** Created `samples/basic_etl.sas` (DATA step + PROC SQL, no macros), `samples/employees_raw.csv` (8-row input), `samples/basic_etl_ref.csv` (3-row dept summary reference)
- **S02:** `src/worker/engine/models.py` — `SASBlock` and `GeneratedBlock` Pydantic models
- **S03:** `src/worker/engine/parser.py` — `SASParser.parse()` with regex extraction, networkx dependency ordering, unsupported PROC flagging as UNTRANSLATABLE
- **S04:** `tests/test_parser.py` — 10 unit tests, all pass
- **S05:** `src/worker/engine/llm_client.py` — `LLMClient.translate()` via Pydantic AI agent; short-circuits on UNTRANSLATABLE blocks
- **S06:** `src/worker/engine/codegen.py` — `CodeGenerator.assemble()` with Jinja2 template; provenance headers and untranslatable boxing
- **S07:** `src/worker/compute/local.py` — full `LocalBackend` implementation (read_csv/run_sql via sqlite3/write_parquet/to_pandas)
- **S08:** `src/worker/validation/reconciliation.py` — `ReconciliationService` with schema parity, row count, aggregate parity checks
- **S09:** `tests/reconciliation/test_data_step.py` — 4 reconciliation tests (happy path + 3 failure cases); all pass
- **Docker fix:** Both Dockerfiles now copy `README.md` before `uv sync` (hatchling validation fix)
- **Makefile:** Added `make docker-build` target
- **CLAUDE.md:** Added two Critical Rules — `make test` only (no `uv run pytest`), `make docker-build` required on Dockerfile changes
- **backend-builder compliance pass:** Fixed 14 ruff violations (import sort, E501, UP042, D107, RUF100) and 5 mypy errors across all new engine files; `BlockType` migrated to `StrEnum`; pydantic-ai `result_type→output_type` and `.data→.output` API migration; mypy override added for `llm_client.py` (pydantic-ai overload limitation); `CodeGenerator` refactored to pre-compute block headers in Python (avoids long Jinja2 template lines)
- `make check` passes (ruff + mypy clean); `make test`: 20/20 pass, 64% coverage

### Decisions

- **LocalBackend.run_sql:** stdlib sqlite3 (not PostgreSQL, not pandasql) — zero dep, self-contained, correct for reconciliation
- **make test is a Critical Rule:** added to CLAUDE.md so it applies in all contexts, not just when a skill is active
- **make docker-build:** new mandatory step for Dockerfile commits; added to Makefile and CLAUDE.md

### Open Questions

- none

### Next Session — Start Here

1. Continue F1 from S10 in `docs/plans/F1-pipeline-generation.md`:
   - S10: Alembic migration — add `llm_model` column to `jobs` table + update ORM model
   - S11: Wire engine into worker poll loop (`src/worker/main.py`)
   - S12: Audit + download API schemas (`src/backend/api/schemas.py`)
   - S13: `GET /jobs/{id}/audit` endpoint
   - S14: `GET /jobs/{id}/download` endpoint (zip)
   - S15: API route tests
   - S16: Raise `fail_under` to 90, confirm `make test` green

### Files Touched

- `pyproject.toml`, `uv.lock`
- `CLAUDE.md`, `Makefile`
- `src/backend/Dockerfile`, `src/worker/Dockerfile`
- `src/worker/engine/models.py` (new)
- `src/worker/engine/parser.py` (new)
- `src/worker/engine/llm_client.py` (new)
- `src/worker/engine/codegen.py` (new)
- `src/worker/compute/local.py` (updated — full implementation)
- `src/worker/validation/reconciliation.py` (new)
- `samples/basic_etl.sas`, `samples/employees_raw.csv`, `samples/basic_etl_ref.csv` (new)
- `tests/test_parser.py` (new)
- `tests/reconciliation/__init__.py`, `tests/reconciliation/test_data_step.py` (new)
- `docs/plans/F1-pipeline-generation.md` (new)
- `journal/BACKLOG.md`, `journal/DECISIONS.md`, `journal/SESSIONS.md`

---

## 2026-04-17 — Phase 1 Scaffold, Databricks Strategy & Workflow Hardening

**Duration:** ~3h | **Focus:** Full four-service skeleton, design decisions, session tooling

### Done

- Reasoned through three Databricks output targets (PySpark, Databricks SQL, DLT) — locked in PySpark-only for `DatabricksBackend`; Databricks SQL and DLT deferred. Logged in `journal/DECISIONS.md` and `docs/architecture.md`
- Created `feat/phase1-scaffold` branch
- Planned and executed all 21 subtasks of `docs/plans/F0-phase1-scaffold.md` without stopping:
  - `docker-compose.yml`: 4 services (postgres, backend, worker, frontend) on `rosetta-net`
  - `src/backend/`: FastAPI app, `POST /migrate`, `GET /jobs/{id}`, SQLAlchemy async, pydantic-settings
  - `src/worker/`: async poll loop (queued→running→failed:not-implemented), `ComputeBackend` ABC, `LocalBackend` stub, `BackendFactory`
  - `src/frontend/`: Vite + React + TS + Tailwind + shadcn/ui placeholder
  - `alembic/` + `jobs` table migration (`001_create_jobs_table`)
  - `tests/test_api_smoke.py`: 6 smoke tests via in-memory SQLite — 6/6 pass
  - `pyproject.toml`: added SQLAlchemy[asyncio], Alembic, asyncpg, pytest-asyncio, aiosqlite, pandas-stubs
  - CI: reconciliation job with Postgres service + Alembic step; frontend build and Docker build jobs active
- Rewrote `README.md` with full session workflow guide (`/session-start`, `/session-end`, `/plan-feature`, `/git-committer`) and `make test` as the canonical test command
- Updated `Makefile`: fixed `coverage` path (`--cov=src`), fixed `run-backend` entrypoint (`src.backend.main:app`), removed stale `frontend-test`
- Hardened skills: `git-committer` now mandates `make test` at step 1 before staging code; `backend-builder` and `CLAUDE.md` explicitly forbid raw `uv run pytest`

### Decisions

- **DatabricksBackend = PySpark only:** SQL cannot handle DATA steps; DLT breaks local/cloud symmetry. See `journal/DECISIONS.md` session 5 entry.
- **Codegen constraint:** `CodeGenerator` must not emit pandas-only idioms — use parameterised DataFrame ops so `LocalBackend` and `DatabricksBackend` swap APIs without changing structure
- **Tests via `make test` only:** `uv run pytest` and bare `pytest` are forbidden in skills, CLAUDE.md, and README
- **SQLite for smoke tests:** `aiosqlite` in-memory DB avoids a real Postgres dependency in unit/smoke tests; Alembic migration runs against real Postgres in CI reconciliation job only

### Open Questions

- none

### Next Session — Start Here

1. Run `/plan-feature` for **F1** (SAS parser → LLM client → codegen). The plan should cover: `src/worker/engine/parser.py` (DATA step + PROC SQL block extraction, multi-file dependency ordering), `src/worker/engine/llm_client.py` (Pydantic AI agent, `LLM_MODEL` env var), `src/worker/engine/codegen.py` (provenance comments, `# SAS: <file>:<line>`)
2. Before planning F1, add sample SAS files to `samples/` — the parser needs real input to test against

### Files Touched

- `docker-compose.yml`
- `pyproject.toml`, `uv.lock`
- `.env.example`
- `alembic.ini`, `alembic/env.py`, `alembic/versions/001_create_jobs_table.py`
- `src/backend/` (all files — new)
- `src/worker/` (all files — new)
- `src/frontend/` (full scaffold — new)
- `tests/test_api_smoke.py` (new)
- `.github/workflows/ci.yml`
- `docs/plans/F0-phase1-scaffold.md` (new, status: done)
- `docs/architecture.md`
- `journal/BACKLOG.md`, `journal/DECISIONS.md`
- `README.md`, `Makefile`, `CLAUDE.md`
- `.claude/skills/git-committer/SKILL.md`, `.claude/skills/backend-builder/SKILL.md`

---

## 2026-04-17 — DuckDB Removal, Skill Hardening & Feature Catalogue

**Duration:** ~2h | **Focus:** Local backend swap, skill quality, feature catalogue

### Done

- Replaced DuckDB with PostgreSQL as the local `ComputeBackend` — removed `duckdb>=0.10` from `pyproject.toml`, updated all docs, README, CLAUDE.md, backlog, and decisions log
- Audited all skills and commands for hard-coded file paths — found offenders in `backend-builder`, `frontend-builder`, and `plan-feature`; replaced with instructions to derive paths from `docs/architecture.md`
- Added F8–F18 to `docs/features.md` (13 new features); bumped F8 (Compliance & Audit Traceability) and F9 (Downloadable Migration Output) to MVP scope
- Updated `docs/mvp-scope.md` and `journal/BACKLOG.md` accordingly

### Decisions

- DuckDB removed: PostgreSQL is already in Docker Compose for job state — one less engine, logged in DECISIONS.md
- Skills must not hard-code file paths: derive from `docs/architecture.md` — logged in DECISIONS.md

### Open Questions

- none

### Next Session — Start Here

1. Run `/plan-feature` for Phase 1 scaffold (Docker Compose revision, `src/backend/`, `src/worker/`, `src/frontend/` structure, jobs table Alembic migration)
2. Run `uv sync` to drop DuckDB from the lock file after the scaffold is in place

### Files Touched

- `pyproject.toml`
- `docs/architecture.md`, `docs/features.md`, `docs/mvp-scope.md`, `docs/user-stories.md`
- `CLAUDE.md`, `README.md`
- `journal/BACKLOG.md`, `journal/DECISIONS.md`
- `.claude/skills/backend-builder/SKILL.md`
- `.claude/skills/frontend-builder/SKILL.md`
- `.claude/skills/plan-feature/SKILL.md`
- `.claude/commands/plan-feature.md`

---

## 2026-04-17 — Architecture Revision, Feature Expansion & Tooling Overhaul

**Duration:** ~3h | **Focus:** Architecture, features, skills/commands, CI

### Done

- Confirmed context: CI fixes defer to when `src/` is created; multi-file upload is MVP; frontend confirmed React+Vite; Databricks paused
- Revised `docs/architecture.md` — full rewrite: 4-service microservices (backend, worker, frontend, postgres), async job flow (POST→job_id→poll), reconciliation inline in worker, provider-agnostic LLM via `LLM_MODEL` env var, PostgreSQL jobs table schema, updated directory structure
- Updated `docs/mvp-scope.md` — multi-file input now in MVP scope; post-MVP phases restructured
- Updated `.github/workflows/ci.yml` — reconciliation job gets postgres service + Alembic step; worker image added to Docker build job; frontend comment corrected to Phase 1; `LLM_MODEL` dummy env var added
- Added F8–F18 to `docs/features.md` — 13 new features catalogued across phases
- Bumped F8 (Compliance & Audit Traceability) and F9 (Downloadable Migration Output) to MVP
- Updated `journal/BACKLOG.md` — Phase 1 rewritten for 4-service scaffold; F8/F9 tasks added; Phase 2–4 expanded with new features
- Updated `journal/DECISIONS.md` — session 3 decisions logged
- Overhauled `plan-feature`, `session-start`, `session-end` skills and commands — plan-feature now writes `docs/plans/F<N>-<slug>.md` with subtasks, dependencies, acceptance criteria; session-start reads `docs/plans/`; session-end updates plan file before journal
- Updated `CLAUDE.md` — architecture summary, key docs table, session continuity steps, skills table

### Decisions

- All logged in `journal/DECISIONS.md` under "session 3 — architecture revision"
- Key: 4-service microservices, async jobs in Postgres, reconciliation inline, LLM_MODEL env var, multi-file in MVP, F8/F9 bumped to MVP, Databricks paused to Phase 4

### Open Questions

- none

### Next Session — Start Here

1. Run `/plan-feature` for Phase 1 scaffold (Docker Compose revision, `src/backend/`, `src/worker/`, `src/frontend/` structure, jobs table Alembic migration)
2. Work through F1 vertical slice subtasks in order per the generated plan file

### Files Touched

- `docs/architecture.md`
- `docs/features.md`
- `docs/mvp-scope.md`
- `journal/BACKLOG.md`
- `journal/DECISIONS.md`
- `.github/workflows/ci.yml`
- `.claude/commands/plan-feature.md`
- `.claude/commands/session-start.md`
- `.claude/commands/session-end.md`
- `.claude/skills/plan-feature/SKILL.md`
- `.claude/skills/session-start/SKILL.md`
- `.claude/skills/session-end/SKILL.md`
- `CLAUDE.md`

---

## 2026-04-17 — Claude Setup Hardening & Dev Scaffolding
- What decisions did we make?
- What's blocked or open?
- What's the very next thing to do?

---

## 2026-04-17 — Claude Setup Hardening & Dev Scaffolding

**Duration:** ~3h | **Focus:** Claude Code setup audit, dev tooling, CI pipeline

### Done

- Audited and fixed Claude Code setup: created 3 missing skills (`session-start`, `session-end`, `plan-feature`)
- Fixed CLAUDE.md skill table — clarified user-invoked vs Claude-invoked skills
- Improved all skills with `Use for` / `Do NOT use for` sections
- Updated `backend-builder` skill with comprehensive rules (layer placement, Pydantic AI, guardrails, output contract)
- Updated `frontend-builder` skill with design philosophy from external source
- Updated `git-committer` skill with atomic commit definition and examples
- Cleaned `pyproject.toml`: removed `sas-kernel`, moved `antlr4` to optional `[parsers]` group
- Pinned Python to 3.12 via `uv python pin`, rebuilt venv
- Created `Makefile` with all dev targets including Docker (`make dev`, `make dev-down`, `make dev-logs`)
- Created `.pre-commit-config.yaml` with ruff + mypy hooks, installed hooks
- Created `.env.example`
- Created `docker-compose.yml` pointing to per-service Dockerfiles (to be added in Phase 1 and 3)
- Moved `specs/mvp-scope.md` → `docs/mvp-scope.md`, deleted `specs/` folder, updated all references
- Aligned line-length standard to 100 chars across `coding-standards.md` and `pyproject.toml`
- Rewrote `README.md`: Docker-first setup, Claude Code workflow, committing guidelines, philosophy section
- Added GitHub Actions CI pipeline (`.github/workflows/ci.yml`) with uv caching, two active jobs (lint+types, tests), four commented-out future jobs (reconciliation, frontend, Docker, cloud)
- Raised coverage gate to 90% in `pyproject.toml`
- Fixed CI to skip ruff/mypy/pytest gracefully when `src/` and `tests/` don't exist yet

### Decisions

- Docker Compose is the standard dev runtime; Dockerfiles live alongside source (`src/backend/`, `src/frontend/`)
- `specs/` folder removed — MVP scope lives in `docs/mvp-scope.md`
- No `Co-Authored-By` Claude attribution in any commit message
- `structlog` not added — stdlib `logging` used instead (not in pyproject.toml)
- No Spec-Driven Development for now — behaviour tables per SAS construct handler when Phase 1 starts
- No subagents yet — journal + skills handle context; revisit at Phase 2-3

### Open Questions

- Which SAS sample file will be the first migration target?
- Do we have access to a Databricks workspace for CLOUD=true testing?
- Frontend framework confirmed as React + Vite (not Streamlit)?

### Next Session — Start Here

1. Fix CI test job to skip gracefully when `tests/` doesn't exist (interrupted mid-fix)
2. Start Phase 1: scaffold `src/sas_migrator/` package structure
3. Run `/plan-feature` for F1 vertical slice

### Files Touched

- `.claude/skills/*` (all updated)
- `.claude/settings.json`
- `CLAUDE.md`
- `pyproject.toml`
- `Makefile`
- `.pre-commit-config.yaml`
- `.env.example`
- `.python-version`
- `docker-compose.yml`
- `docs/mvp-scope.md` (moved from `specs/`)
- `docs/coding-standards.md`
- `README.md`
- `.gitignore`
- `.github/workflows/ci.yml`
- `journal/BACKLOG.md`
- `journal/DECISIONS.md`
- `uv.lock`

---

## 2026-04-17 — Project Kickoff

**Participants:** Mattia + Claude
**Duration:** ~1h
**Focus:** Setting up project scaffolding and Claude Code configuration

### Done

- Defined two user stories (tech user + non-tech user)
- Expanded 7 features across backend/frontend
- Created CLAUDE.md, skills, commands, and journal structure
- Locked in MVP constraints: CLOUD flag in .env, local + Databricks support

### Decisions

- See `journal/DECISIONS.md` entries dated 2026-04-17

### Open Questions

- Frontend framework: Streamlit for MVP, confirmed?
- Which SAS sample files will we use as the first migration target?
- Do we have access to a Databricks workspace for testing CLOUD=true path?

### Next Session — Start Here

1. Pick the first SAS sample file (smallest, self-contained)
2. Plan the vertical slice: ingest → translate → execute → reconcile (CLOUD=false)
3. Scaffold the `ComputeBackend` interface
4. Write the first reconciliation test

### Files Touched

- CLAUDE.md (created)
- .claude/skills/\* (created)
- .claude/commands/\* (created)
- journal/\* (created)
- docs/\* (created)
- specs/mvp-scope.md (created)
```
