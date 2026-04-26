```markdown
# Decisions Log

Append-only. For larger decisions, also create a full ADR in `docs/adr/`.
Format: date · decision · rationale · revisit?

---

## 2026-04-26 (session — Codegen/executor fixes)

- **Output variable naming convention:** output dataset variables use TABLE STEM ONLY (no libname prefix) — `DATA outdir.foo` → Python var `foo`; input datasets keep full `libname_table` form since they are pre-loaded. Rationale: prevents agents from referencing the output as if it were an input. · revisit never
- **`build_context_section()` removed:** was dead code (never called by any agent); log context now injected inline in each agent's `_build_prompt()` · revisit never
- **`result` as canonical executor output variable:** `assemble_flat()` appends `result = <output_var>` so the executor result-capture snippet can find it reliably via `globals().get('result')` · revisit never

---

## 2026-04-25 (session — Agentic pipeline context + Editor UX polish)

- **`manual_ingestion` is not untranslatable:** PROC IMPORT and similar I/O blocks have clear Python equivalents (`pd.read_csv`); they get `is_untranslatable=False`, `confidence_score=0.7`, and a `# TODO: verify delimiter and encoding` comment · revisit never
- **Absolute disk path in `manual_ingestion` stub:** the uploaded file's absolute path (sentinel `disk_path`) is used so the generated code is immediately runnable locally; relative project path is a post-migration concern · revisit when executor sandbox path mapping is clarified
- **`build_context_section()` shared utility:** a single function in `shared_context.py` renders the project context prompt section from `JobContext.data_files` and `libname_map`; all agents call it identically; adding a new context field requires changing only this one function · revisit never
- **DATA_FILE lineage nodes use `inferred: True` edges:** consistent with existing cross-file inferred-edge convention; frontend uses the `inferred` flag to style edges differently · revisit never
- **`_translate_blocks()` must pass `block_plan` per block:** migration planner strategy was being computed but discarded — root cause of PROC IMPORT staying UNTRANSLATABLE despite correct plan; fixed via `block_plan_map` dict keyed on `"{source_file}:{start_line}"` · revisit never

---

## 2026-04-24 (session — SAS EG editor UX + executor microservice)

- **`executor` microservice (new Docker service, port 8001):** generated Python runs in a subprocess sandbox inside a separate container rather than `exec()` in-process; isolates execution, enables cloud scaling, and exposes a `POST /execute` HTTP endpoint reusable by worker and backend · revisit when adding SAS execution support
- **Shared `uploads` volume between `backend` and `executor`:** reference files (.csv, .sas7bdat) uploaded by the user must be readable by the executor at the same absolute path; named Docker volume `uploads` mounted at `/uploads` in both services · revisit never
- **`RemoteReconciliationService` with graceful fallback:** worker delegates recon to executor over HTTP; `ConnectError`/`TimeoutException` return `{"checks": []}` and log a warning rather than failing the job — executor unavailability is non-fatal · revisit never
- **Bottom panel always-visible split (SAS Studio layout):** execution output, log, output data, and history are shown in a persistent resizable bottom panel (vertical `ResizablePanelGroup`) instead of a slide-in overlay; matches SAS Studio UX familiar to SAS users · revisit never
- **`translate_best_effort` strategy is dead:** defined in the enum but absent from the migration planner prompt — LLM never assigns it; needs to be either added to the prompt with a definition or removed · revisit next session
- **`manual_ingestion` stub is identical to `manual`:** `StubGenerator` ignores strategy — both produce `# SAS-UNTRANSLATABLE`; `manual_ingestion` was supposed to emit a `pd.read_csv()` scaffold · fix next session
- **`auto_verified` counter always 0:** `verified_confidence` field is never written by any agent; `auto_verified` should derive from `reconciliation_status == "pass" AND confidence in (high, medium)` · fix next session

## 2026-04-24 (session — Explain overhaul)

- **ExplainAgent 3-layer prompt composition:** base + mode-specific + audience-specific sections composed at construction time into a 4-agent cache; adding a new mode or audience requires only a new dict entry — revisit never
- **`_persist_messages` must own its own DB session:** FastAPI SSE request-scoped sessions are closed before `asyncio.create_task` fire-and-forget tasks complete; all future background persistence tasks must open their own `AsyncSessionLocal()` — revisit never
- **Worktree agents must not be used for implementation on branches with uncommitted work:** worktree agents clone a clean HEAD, losing all uncommitted changes in the working tree; always commit staged work before delegating to a worktree agent, or use the main tree agent with explicit file paths — revisit never (process change)
- **`mode='sas_general'` replaces `'upload'`:** "upload" described the mechanism, not the intent; migration 013 backfills all existing rows; frontend and backend literals updated atomically — revisit never

---

## 2026-04-19 (session 18 — F3 proposed/accepted, S-BE5/BE6, UI fixes)

- **`jobs_status_check` constraint expanded to include `proposed`/`accepted`:** migration 008 drops and recreates the constraint to allow new statuses before running the UPDATE · revisit never
- **`done` rows migrate to `proposed` (not `accepted`):** `done` was implicit acceptance but with no review performed; landing in `proposed` gives the user a chance to explicitly accept or refine · revisit if historical data needs different treatment
- **`"done"` kept as a frontend legacy `JobStatusValue`:** old worker images still write `"done"` between deploys; frontend maps it to amber "Under Review" and treats it as clickable/navigable · revisit when all environments rebuild
- **ReconciliationService skips execution when no reference data supplied:** running generated code in a sandbox with no input data was always failing and reporting a false `execution: fail` check · revisit never
- **`skip_llm` flag + `trigger` column for versioning:** `PUT /python_code` sets `skip_llm=True` and `trigger="human-rereconcile"`; `POST /refine` spawns a child job with `trigger="human-refine"`; allows the History tab to distinguish agent vs human changes · revisit never
- **History tab walks `parent_job_id` chain:** linear parent chain enables full version history without a separate events table; siblings (branches) are collected via a second query on parent IDs · revisit if branching history is needed
- **Refine context injected as `__refine_context__` sentinel in `job.files`:** avoids adding more DB columns while keeping prior code and hint available to the worker prompt; sentinel is stripped from sources display · revisit never

---

## 2026-04-23 (session 23 — Plan tab UX overhaul)

- **View Code dialog layout:** unified full-width toolbar row + identical-height panel header row (grid-cols-2) above the editors — eliminates SAS/Python vertical misalignment without JS measurement; `border-border` used throughout for theme-agnostic separators · revisit never
- **Confidence default fix location:** applied at StubGenerator and migration_planner (the two write paths) rather than at the API read/serialisation layer — ensures DB values are correct for all new jobs from the point of the fix · revisit never

---

## 2026-04-22 (session 21 — F4 confidence-refine-history)

- **`TranslationStrategy.TRANSLATE_BEST_EFFORT` added to StrEnum:** was referenced in F4 plan but missing from the model; added alongside TRANSLATE, TRANSLATE_WITH_REVIEW, MANUAL_INGESTION, MANUAL, SKIP · revisit never
- **block_id format normalised to basename-only (`"file.sas:12"`):** avoids URL path encoding issues with directory separators; client always `encodeURIComponent()` before URL interpolation · revisit never
- **Block revisions created only on explicit refine (not on job completion):** initial agent output is already captured by `job_versions[tab=editor]`; first refine inserts revision 1 (prior) + revision 2 (new) · revisit never
- **Trust report returns 200 with partial data when lineage unavailable:** `blast_radius: null` per block + `lineage_available: false` flag; no 202 polling — degrades gracefully · revisit never
- **409 Conflict on refine when job is accepted:** both whole-job (`POST /jobs/{id}/refine`) and block-level (`POST /jobs/{id}/blocks/{block_id}/refine`) return 409 when `accepted_at IS NOT NULL` · revisit never
- **`diff_vs_previous` computed in FastAPI route handler:** both old and new code available at insert time; uses `difflib.unified_diff`; worker has no access to prior revision · revisit never
- **`verified_confidence` stored under `job.lineage["block_confidence"]`:** piggybacks on existing schemaless JSON column; no DB migration needed; backward-compatible (old jobs lack the key) · revisit never
- **Refine dialog: user notes are primary input, injected first into LLM context:** user-authored instructions take precedence over auto-generated hints; injected as leading `risk_flags` entry · revisit never

---

## 2026-04-23 (session 22 — UI polish, View Code dialog, Upload→Dialog, PATCH /python)

- **Upload page promoted to Dialog on JobsPage:** reduces nav clutter; upload is a sub-action of "Migrations", not a top-level destination · revisit never
- **`PATCH /jobs/{id}/blocks/{block_id:path}/python` creates revision 1 when no prior revision exists:** uses defaults (`strategy="translate"`, `confidence="medium"`) rather than 404; any block is editable regardless of agent history · revisit never
- **SAS source in View Code dialog via `getJobSources`:** reuses existing endpoint mapping `source_file` → full SAS content; no new DB columns · revisit never
- **`revisions[0]` is the latest revision (backend returns `revision_number DESC`):** fixed bug where code was reading `revisions[length-1]` (oldest) instead of `revisions[0]` (newest) · revisit never

---

## 2026-04-22 (session 22 — FE9 ExplainPage)

- **ExplainPage backend is stateless:** frontend owns the accumulated `messages` array and sends it on each request; avoids session storage for an ephemeral chat feature · revisit if multi-turn context management becomes complex
- **LLM called inline in backend process (not worker queue):** explain questions need to feel synchronous; worker queue polling latency is inappropriate for chat; backend already imports worker agents · revisit if LLM calls become slow enough to time out the HTTP request
- **Separate `/explain` and `/explain/job` endpoints (not one unified endpoint):** multipart form data and JSON body cannot be cleanly unified; different validation and auth requirements; keeps route logic simple · revisit never
- **Code blocks in chat rendered as read-only Monaco editors:** user preference over styled `<pre>` blocks; consistent with editor components used elsewhere in the app · revisit never

---

## 2026-04-21 (session 20 — LineageEnricher pipeline-level extension)

- **`LineageEnricherAgent` max_tokens raised 8k → 16k:** 9-field JSON output (5 new fields) can exceed 8k for multi-file SAS projects; conservative doubling; revisit if latency becomes a concern
- **New lineage fields stored in existing schemaless JSON column — no migration:** `Job.lineage` is PostgreSQL JSON (nullable); new fields merge in via `{**lineage_data, **enriched.model_dump()}`; backward-compatible (old jobs simply lack the new keys) · revisit never
- **React Flow `NODE_TYPES` must be module-level constant:** if defined inside a component, React Flow remounts all nodes on every parent re-render; all custom node type registrations are at module scope · revisit never

---

## 2026-04-21 (session 19 — F5 bug-fix sweep)

- **TipTap switches to native HTML mode, `tiptap-markdown` dropped:** `@tailwindcss/typography` is absent so `prose` classes did nothing; extension's `html: false` mode mangled headings. Native HTML + `marked` for load + `getHTML()` for save is simpler and fully functional. Stored `content.doc` in versions saved after this session will be HTML, not raw markdown · revisit if markdown round-trip fidelity becomes a requirement.
- **`Tabs` component now supports controlled mode (`value`/`onValueChange`):** the original component was uncontrolled-only; `JobDetailPage` was passing controlled props that were silently ignored, disconnecting `activeTab` state from the visible tab entirely · revisit never.
- **Shadcn `Select` (Base UI variant) replaces native `<select>`:** `@base-ui/react/select` is already in the dependency tree; provides consistent styling and accessible keyboard behaviour · revisit never.

---

## 2026-04-19 (session 17 — F2-improvements backend: models, agents, codegen, API)

- **Two-phase refinement replaces `_MAX_RETRIES` while-loop:** explicit two phases (translate all → reconcile → if fail: re-translate affected block only) is predictable and equivalent to the old max-2-retry limit; easier to reason about and test · revisit never
- **`MigrationPlannerAgent` and `LineageEnricherAgent` are best-effort:** wrapped in try/except in orchestrator; failure logs warning but does not abort the job. Core migration correctness must not depend on enrichment agents · revisit never
- **`CodeGenerator.assemble()` returns `dict[str, str]`; `assemble_flat()` returns str:** multi-file output needed for S-M (1:1 SAS↔Python editor); flat string still needed for reconciliation execution and `python_code` DB column · revisit never

---

## 2026-04-19 (session 16 — UI polish, zip folder tree, lineage node styling)

- **Zip upload stores full relative path as key:** `os.path.basename` was stripping directory structure; full path required for VSCode-style file tree; path traversal guard updated to check `".." in path.split("/")` instead of basename equality · revisit never

---

## 2026-04-19 (session 15 — LineageGraph UX, toasts, file_count, undo/redo)

- **LineageGraph hover-to-focus replaces click-to-focus:** hover is more discoverable and natural for a graph; 80ms debounce prevents flicker when crossing node boundaries · revisit never
- **Undo/Redo history stores `{id→{x,y}}` position snapshots, not full Node objects:** full Node refs are mutated in place by ReactFlow; deep-copying only x/y is safe and minimal · revisit never
- **Undo/Redo uses `setNodes` from `useNodesState` (controlled-mode setter):** ReactFlow in controlled mode overwrites its internal store from the nodes prop on every render; `rfSetNodes` (instance method) gets clobbered; controlled setter is the only correct path · revisit never
- **`file_count` counts all keys in `job.files` (not just non-sentinel):** reference files (CSV/log/xlsx) stored as `__ref_*__` sentinels are still user-uploaded files; count should reflect total accepted files · revisit never
- **Sonner (shadcn) used for all error toasts:** shadcn's official toast recommendation; no `next-themes` dependency — hardcoded `theme="light"` since project is Vite SPA with no theme switching · revisit if dark mode is added
- **Human-readable error copy everywhere:** raw `{detail: ...}` JSON never shown to user; `extractApiError` strips FastAPI envelope; fallback strings written for humans not developers · revisit never

---

## 2026-04-19 (session 14 — UI polish, lineage DAG, Makefile fixes)

- **Editor tab merges Comparison + Edit:** single tab with SAS read-only left, editable Python right; users naturally want the source visible while editing; avoids context-switching between tabs · revisit never
- **`._` zip entries skipped silently:** macOS resource fork files are OS artefacts, not user content; no rejection entry added · revisit never
- **`file_count` counts non-sentinel keys:** keys matching `__…__` pattern are internal sentinels (reference files); plain keys are SAS sources; count reflects user-uploaded SAS files only · revisit if supporting file count needs to be shown separately
- **Makefile: NPM_FLAGS not passed to ESLint/Vite:** ESLint v9 flat config and Vite CLI reject `--silent`; lint and build targets now invoke `npm run lint` / `npm run build` without extra flags · revisit never

---

## 2026-04-18 (session 13 — JobDetailPage, UploadPage workspace, name/file_count)

- **UploadPage as persistent workspace:** state lifted into `UploadStateProvider` (React context at App root) so it survives sidebar navigation; never auto-navigates away; "Start another" keeps result visible, "Accept & clear" is the explicit reset · revisit never
- **Zip preview client-side with jszip:** zip contents parsed in browser on drop, filtered of `__MACOSX`/hidden entries, displayed as a tree; full zip still sent to server unchanged (server handles extraction) · revisit never
- **Tabs component hand-rolled:** shadcn `base-nova` style tabs depend on `@base-ui-components/react` which is not installed and had a circular import; replaced with a self-contained React state-based tabs component · revisit if `@base-ui-components/react` is installed project-wide
- **Markdown doc rendered via `marked` + prose:** `TiptapEditor` receives HTML but LLM doc is raw Markdown; using `marked.parse()` + `dangerouslySetInnerHTML` + Tailwind `prose` class instead of a Tiptap instance · revisit never
- **`name` field on Job:** optional human-readable label submitted as a form field on `POST /migrate`; stored in `jobs.name` (migration 005); surfaced in `GET /jobs` list and result card · revisit never
- **`file_count` derived at query time:** computed in `list_jobs` as count of non-`__`-prefixed keys in `job.files`; not stored as a column · revisit if query performance degrades at scale

---

## 2026-04-18 (session 12 — post-MVP UI planning)

- **Zone-based editor architecture:** each UI content type gets the right primitive — Monaco DiffEditor for SAS vs Python diff, Monaco Editor for inline editing, Tiptap for rich-text notes/reports, React Flow for lineage graph · revisit never
- **Sidebar nav replaces top nav:** persistent collapsible sidebar scales to 6+ pages; top nav does not · revisit never
- **JobDetailPage at /jobs/:id (full page, 4 tabs):** replaces inline expansion in JobsPage; Comparison / Edit / Report / Lineage tabs; deep-linkable · revisit never
- **Zip upload: partial acceptance, no file count limit:** unknown extensions collected into rejection manifest rather than hard 400; caller sees accepted + rejected list · revisit never
- **Zip accepted extensions:** `.sas`, `.sas7bdat`, `.csv`, `.log`, `.xlsx`, `.xls` — covers SAS source, binary datasets, reference data, execution logs, and Excel inputs · revisit if new SAS-adjacent formats surface
- **Lineage serialised to `job.lineage` JSON column at parse time:** worker writes lineage after parse step; not computed on demand at API request time · revisit never
- **DocGenerator does not crash worker on LLM failure:** catch exception, log warning, leave `job.doc = None`; doc is optional enrichment, not a required pipeline step · revisit never
- **`skip_llm` boolean column for re-reconciliation:** cleaner than adding a new status value to the FSM; worker branches on flag, skips parser+LLM, runs ReconciliationService only · revisit never
- **`parent_job_id` FK on Job for refine action:** enables UI to show refinement history without a separate table · revisit never

---

## 2026-04-18 (session 11 — F-UI + Docker runtime + Azure OpenAI)

- **`CORS_ORIGINS` as plain string, split internally:** `list[str]` pydantic-settings field fails when env var is `*`; switched to `str` field with `@property` that splits on comma · revisit never
- **Migration 001 id column as String(36):** ORM uses `String(36)` for cross-dialect compatibility; migration was incorrectly using `postgresql.UUID` causing type mismatch on INSERT · revisit never
- **Backend entrypoint runs migrations on startup:** `alembic upgrade head` in `entrypoint.sh` before uvicorn ensures schema is always current · revisit if migration time becomes a startup concern
- **Azure deployment name stripped of provider prefix:** `LLM_MODEL=openai:gpt-5.4` → deployment `gpt-5.4` via `split(":", 1)[-1]`; handles both bare and prefixed values · revisit never
- **Frontend volume mount for HMR:** `./src/frontend:/app` + `/app/node_modules` anonymous volume; Vite picks up file changes without container rebuild · revisit never

---

## 2026-04-18 (session 10 — F-LLM + F-sas7bdat + tooling)

- **`make test` now includes mypy:** mypy was only running in `make check` and pre-commit; added to `make test` so type errors surface before commit time · revisit never
- **git-branch-setup always pulls main before branching:** new feature branches start from latest main, not stale local HEAD · revisit never
- **No Co-Authored-By attribution in commits:** user preference; removed from all commit messages · revisit never
- **LLMTranslationError classifies transient vs permanent:** HTTP 429 / 5xx / network errors are transient (retry); 4xx / validation errors are permanent (fail immediately); partial codegen results are saved on failure with `error_detail.resumable=true` for transient cases · revisit if retry policy needs tuning

---

## 2026-04-18 (session 9 — F1-ext + MVP scope alignment)

- **F-number collision resolved:** PROC SORT + %LET are F1 extensions (Phase 2), not a new feature. `docs/plans/F2-proc-sort.md` renamed to `F1-ext-proc-sort-macro.md`. F2 is reserved for the Code Explanation Assistant UI (Phase 3 frontend) per `docs/features.md` · revisit never
- **MVP requires a frontend:** Upload & Results page (F-UI) added to MVP scope — product cannot be demoed or handed to a user without UI · revisit never
- **LLM is the primary and mandatory translation engine:** no rule-based fallback path. LLM system prompt must be upgraded to establish agent as SAS migration expert targeting Python/PySpark. Worker resilience (graceful job failure on API unreachable) is error handling only, not a translation fallback · revisit never
- **sas7bdat reading is MVP-required:** `pyreadstat` already declared in `pyproject.toml` but never wired. `LocalBackend` must implement `read_sas7bdat()` before MVP is complete · revisit never
- **make test is the only allowed test invocation:** `uv run pytest` forbidden everywhere including agent verification steps — all test runs go through make targets. Enforced in memory and CLAUDE.md · revisit never

---

## 2026-04-17

- **Language & runtime:** Python 3.11+ · modern typing, match statements, broad lib support · revisit if Databricks default changes
- **Execution backends:** pandas/PostgreSQL (local) and PySpark (Databricks), toggled by `CLOUD` env var · keeps MVP runnable on a laptop · DuckDB was removed in favour of PostgreSQL (same engine as job state store, one less service) · revisit if PostgreSQL local performance becomes a bottleneck
- **Frontend for MVP:** React + Vite + TypeScript, Tailwind CSS, shadcn/ui · modern component library, accessible primitives, fast DX · revisit never (core stack)
- **LLM tooling:** Claude Code with skills + slash commands + journal-based memory · maximizes context continuity between sessions · revisit never (this is the setup)
- **Provenance:** every generated Python line group carries `# SAS: <file>:<line>` comments · required for audit/compliance user story · non-negotiable
- **Validation strategy:** schema parity + row hash diff + aggregate parity + distribution checks · covers financial reporting confidence · may add more checks per customer

---

## 2026-04-17 (session 2 — foundation setup)

- **Migration approach:** LLM-assisted conversion (approach 3 of 4) — structured prompting with pattern catalog, provenance, and reconciliation as safety net · rationale in `docs/context/migration-approaches.md` · revisit if LLM accuracy proves insufficient at scale
- **Skills vs subagents:** skills only (no specialized subagents) · simpler, compose naturally, avoid duplicated context overhead · revisit if a task requires deep specialization that skills can't capture
- **Backlog as build tracker:** `journal/BACKLOG.md` is the single source of truth for what to build and in what order · read by `/session-start`, updated by `/session-end`
- **Feature-first planning:** when asked to build a feature, Claude invokes `feature-planner` — break into subtasks, update backlog, plan mode, wait for approval before writing code
- **MVP cut:** F1 (DATA step + PROC SQL) + F3 (schema + row count + aggregate parity), local only (CLOUD=false) · all other features are post-MVP
- **Agent framework:** Pydantic AI (`pydantic-ai`) for all LLM interactions — agents, tool definitions, structured outputs · gives type-safe LLM responses via `BaseModel` result types, keeps LLM calls testable and model-agnostic · revisit never (locked in)
- **Pre-commit hooks:** enforced via `pre-commit` library; hooks run ruff format, ruff lint, mypy on every commit · Claude must never use `--no-verify`; hooks are the quality gate, not optional

---

## 2026-04-17 (session 3 — architecture revision)

- **Microservices:** each service is a separate Docker image (backend, worker, frontend, postgres) · separation of concerns; worker decouples heavy processing from API latency · revisit never (core architecture)
- **Worker service:** async job runner as a dedicated container polling Postgres · allows independent scaling and restart of the processing layer without touching the API · revisit if queue volume demands a real message broker (RabbitMQ, SQS)
- **Job state in PostgreSQL:** jobs table stores status, input hash, files JSONB, output, and audit fields · already in the Docker stack; cloud-ready (managed Postgres later); avoids an extra service · revisit never for MVP, may add Redis for pub/sub in Phase 2
- **Async job flow:** POST /migrate → job_id → poll GET /jobs/{id} · keeps API response fast; client controls polling interval · revisit if real-time progress is needed (WebSocket, Phase 2)
- **Reconciliation inline in worker:** F3 runs automatically after codegen, not a separate endpoint · removes manual step; every migration always has a reconciliation result · revisit never
- **Provider-agnostic LLM via LLM_MODEL env var:** Pydantic AI resolves provider from model string (e.g. anthropic:claude-sonnet-4-6) · no custom routing code; swap provider by changing one env var · revisit never
- **Multi-file upload in MVP:** SAS projects are inherently multi-file; single-file MVP was not realistic · parser must order blocks by dependency across files · revisit scope if dependency resolution proves too complex for Phase 1
- **F8 and F9 bumped to MVP:** compliance audit traceability and downloadable output are mandatory for regulated (pharma/finance) first customers · data already in jobs table; no new architecture required · revisit never
- **Databricks paused:** DatabricksBackend stub remains in architecture but out of scope until Phase 4 · no Databricks workspace available for testing · revisit when workspace is confirmed

---

## 2026-04-17 (session 4 — DuckDB removal, skill hardening)

- **DuckDB removed from local backend:** LocalBackend now uses pandas + PostgreSQL instead of pandas + DuckDB · PostgreSQL is already a required service in Docker Compose; removing DuckDB eliminates one dependency and one moving part · revisit never (PostgreSQL is the standard)
- **Skills must not hard-code file paths:** skills and commands must derive service paths from `docs/architecture.md` — Directory Structure section — not embed them directly · prevents stale path refs when architecture evolves · applies to all future skill edits

---

## 2026-04-17 (session 5 — Databricks output target decision)

- **DatabricksBackend generates PySpark only:** three targets were evaluated — Databricks SQL, PySpark, and Delta Live Tables (DLT). PySpark confirmed as the sole output target for `DatabricksBackend`. Rationale: (1) PySpark is symmetric with `LocalBackend` — same Python, same `ComputeBackend` abstraction; (2) DATA steps map cleanly to DataFrame transformations or UDFs; (3) PROC SQL maps to `spark.sql(...)` strings naturally inside PySpark — no separate SQL output mode needed; (4) this is what enterprise clients mean by "Databricks migration" · revisit if a client explicitly requires SQL Warehouse or DLT output
- **Databricks SQL deferred:** SQL cannot handle DATA step logic (RETAIN, array, LAG, conditional multi-dataset output) — it would only cover PROC SQL-heavy codebases; a mixed SQL-in-PySpark approach (`spark.sql()` for PROC SQL blocks) achieves the readability benefit without a separate output mode · revisit in Phase 4+ if a client requires SQL Warehouse target
- **DLT (Delta Live Tables) deferred:** architecturally attractive (native lineage, declarative step model matches SAS) but cannot run locally — breaks the local/cloud symmetry that is a hard design constraint; LLM training data for DLT is thin · revisit Phase 4+ if local parity constraint is relaxed
- **Codegen constraint — no pandas-only idioms:** `CodeGenerator` must not emit pandas-specific calls; use parameterized DataFrame operations so `LocalBackend` and `DatabricksBackend` swap APIs without changing structure · enforced in Phase 1 codegen design

---

## 2026-04-18 (session 7 — F1 completion S10–S16 + multi-agent setup)

- **Multi-agent architecture adopted:** orchestrator + backend-builder + frontend-builder + fullstack-planner + tester agents defined in `.claude/agents/` · separates planning, implementation, and quality gating into distinct roles; orchestrator owns session lifecycle and commit gating · revisit if agent boundaries prove too rigid in practice
- **Orchestrator delegation is mandatory:** orchestrator must spawn specialist agents via Agent tool — never write implementation code directly · discovered this was being bypassed in first pass; enforced in orchestrator.md guardrails and saved to memory · revisit never
- **test-runner skill added:** dedicated `/test-runner` slash command for running `make test`, interpreting results, and reporting GREEN/RED verdict · prevents ad-hoc pytest invocations and centralises test output interpretation · revisit never
- **Coverage concurrency = thread + greenlet:** `[tool.coverage.run] concurrency = ["thread", "greenlet"]` required to trace async FastAPI route bodies via httpx/aiosqlite — without it, route handler lines showed 0% despite tests passing · revisit if coverage tooling changes
- **Makefile output suppressed globally:** PYTEST_FLAGS, NPM_FLAGS, DOCKER_BUILD_FLAGS variables added; all targets use `@` prefix and `--quiet`/`--silent` flags · saves tokens in CI and Claude sessions · revisit never
- **mypy tests.* exemption removed:** the blanket `ignore_errors = true` on `tests.*` was a shortcut; removed so mypy checks test files under strict mode · required fixing `dict` → `dict[str, Any]`, `type: ignore` cleanup, and N806 naming violations · revisit never

---

## 2026-04-18 (session 8 — CI hardening + Tailwind v4 migration)

- **tsc --noEmit is the correct type-check command:** `tsc -b` (project references build mode) requires `composite: true` which conflicts with `noEmit: true`; `tsc --noEmit` reads `tsconfig.app.json` directly and resolves paths correctly · revisit never
- **baseUrl required in tsconfig.app.json:** `pathsBasePath` is not propagated when a config is loaded as a referenced project via `tsc -b`; `baseUrl: "."` + `ignoreDeprecations: "6.0"` is the TS 6 migration path · revisit when TS 7 ships a `baseUrl` replacement
- **Tailwind v4 with Vite plugin:** shadcn v4 generates CSS for Tailwind v4; keeping v3 caused `@apply` errors on every new component; switched to `@tailwindcss/vite`, removed PostCSS config and JS theme config · revisit never
- **Docker job independent of test:** Dockerfile correctness is unrelated to Python logic; running in parallel reduces wall-clock CI time · revisit never
- **Reconciliation coverage scoped separately:** `src/worker/validation` measured in isolation via `.coveragerc-reconciliation` at 80% gate; main suite covers all of `src` at 90% · raise to 90% when missing lines covered
- **astral-sh/setup-uv pinned to full semver:** `v8` floating tag does not exist; must use `v8.1.0` · update when new minor released

---

## 2026-04-23 (session — Plan tab UX + BlockRevisionDrawer + PlainEnglishAgent)

- **block_id URL encoding uses `.replace(/:/g, '%3A')` not `encodeURIComponent`:** FastAPI `block_id:path` params decode `%2F` back to `/` before route matching, causing 404 when slash is encoded; colons must be encoded but slashes must be preserved as literal path segments · revisit never
- **BlockRevisionDrawer diff uses MonacoDiffViewer with `previousCode` prop:** instead of parsing unified diff strings (fragile, misaligned columns), each revision receives the prior revision's `python_code` directly; Monaco handles all diffing natively · revisit never
- **PlainEnglishAgent output field was `"markdown"` in prompt vs `"non_technical_doc"` in Pydantic model:** mismatch silently produced empty docs; corrected to match model field · revisit never
- **PlainEnglishAgent restructured to 5 sections with explicit list formatting:** Purpose (prose) + Source Data (bullets) + How It Works (numbered) + Outputs (bold bullets) + Migration Status (one sentence); "8-12 sentences, no bullet points" rule removed as it forced unstructured output · revisit never

---

## 2026-04-18 (session 6 — F1 engine implementation S00–S09)

- **LocalBackend.run_sql uses stdlib sqlite3, not PostgreSQL:** three options were evaluated — pandasql (SQLite wrapper, extra dep), live PostgreSQL (requires running service), stdlib sqlite3 (zero dep, self-contained). sqlite3 chosen: no extra dep, no service required for local tests, result fidelity is what matters not the SQL engine · revisit if PROC SQL edge cases (window functions, ANSI-only syntax) hit SQLite limits
- **Dockerfile README.md copy required before uv sync:** hatchling validates `readme = "README.md"` at package build time; both backend and worker Dockerfiles now copy README.md alongside pyproject.toml and uv.lock before running `uv sync --no-dev --frozen` · revisit never
- **make docker-build added as mandatory step for Dockerfile changes:** any commit touching a Dockerfile or docker-compose.yml must pass `make docker-build` in addition to `make test` · enforced in CLAUDE.md Critical Rules · revisit never
- **make test is a Critical Rule in CLAUDE.md:** `uv run pytest` and bare `pytest` are forbidden everywhere; only `make test` is allowed · previously only in skills; now in CLAUDE.md to cover all contexts · revisit never
- **pydantic-ai v1 API:** `result_type` → `output_type`; `result.data` → `result.output`; Agent overloads typed for `str` output only — BaseModel `output_type` works at runtime but mypy requires `ignore_errors = true` on `llm_client.py` · revisit if pydantic-ai adds typed overloads for structured output
- **backend-builder skill must be invoked when writing engine code:** discovered that running without the skill led to ruff/mypy violations in the first pass; backend-builder enforces the checklist that catches these · revisit never
- **BlockType uses StrEnum (Python 3.11+):** `class BlockType(str, Enum)` replaced with `class BlockType(StrEnum)` per ruff UP042 · no behaviour change · revisit never

---
```
