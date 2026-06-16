# Introduction

## The problem

Organisations in finance, pharma, insurance, and government are sitting on decades of SAS code they can no longer afford to run. SAS Base and SAS Enterprise Guide licences cost hundreds of thousands of dollars per year, and the engineers who wrote that code have largely moved on. What remains is a black box: business-critical ETL pipelines that transform raw data into financial reports, risk models, regulatory submissions, and audit trails — but that almost no one on the current team fully understands.

Migrating manually is slow, error-prone, and expensive. A single SAS program can span thousands of lines across dozens of macro modules and include files, with runtime behaviour that is only visible in execution logs. Translating it to Python by hand takes weeks per script, requires SAS expertise most teams no longer have, and produces output that is hard to validate — there is no easy way to prove that the Python does what the SAS did.

The result is paralysis: organisations know they need to migrate, but the cost and risk of doing it manually is too high to justify.

## What rosetta-decode does

**rosetta-decode** is an agentic migration tool that automates SAS-to-Python translation end to end. It ingests one or more SAS scripts (main programs, macro modules, include files, execution logs, binary `.sas7bdat` datasets), runs them through a multi-agent LLM pipeline, and produces a complete, runnable Python ETL pipeline — with automatic validation to prove the output matches.

The execution target is controlled by a single environment flag: `CLOUD=false` runs on pandas/PostgreSQL locally; `CLOUD=true` targets Databricks via PySpark. The same generated code, same validation, same audit trail — different runtime.

**What gets automated:**

- Parsing and dependency-ordering SAS DATA steps, PROC SQL, PROC SORT, PROC IML, PROC FORMAT, macro definitions, macro calls, and macro variable resolution
- Translating each block to idiomatic Python using a specialised LLM agent per construct type, with per-block confidence scoring and strategy assignment (translate / manual / skip)
- Running the generated code in a sandboxed executor and comparing outputs against reference data (schema parity, row count, aggregate parity)
- Retrying failing blocks with failure diagnosis fed back into re-translation — without human intervention
- Generating column-level data lineage, plain-English business documentation, and a structured audit record for every job

**What it produces per migration:**

- Per-file Python modules and a `pipeline.py` entry point, every line tagged with `# SAS: <file>:<line>` provenance
- A migration plan with per-block strategy, risk level, and confidence score — visible in the UI before and after execution
- A reconciliation report (pass/fail per check, diff detail) suitable for financial audit sign-off
- An interactive data lineage graph tracing column-level flow from source files through every transformation to output
- A plain-language business summary of what the program does — for non-technical stakeholders and compliance reviewers
- A full audit record: input hashes, LLM model, timestamps, all check results — immutable once written

**What never gets silently dropped:** SAS constructs that cannot be reliably translated are preserved as `# SAS-UNTRANSLATABLE: <reason>` comments. Engineers always know exactly what needs manual attention.

## Current capabilities

The following has been fully implemented and is in active use:

**Migration engine**
- SAS parser: DATA steps (SET/MERGE/OUTPUT/WHERE/ARRAY/DROP/KEEP), PROC SQL, PROC SORT, PROC MEANS, PROC IML, PROC FORMAT, `%LET` macro variables, `%MACRO`/`%MEND` definitions and calls — dependency-ordered via topological sort
- Multi-agent LLM pipeline: AnalysisAgent → MigrationPlannerAgent → TranslationRouter (DataStepAgent / ProcAgent / GenericProcAgent / \_SimpleCopyHelper) → FailureInterpreterAgent → LineageEnricherAgent → DocumentationAgent + PlainEnglishAgent
- Per-block confidence scoring, strategy assignment, risk levels, and post-reconciliation enrichment
- Two-phase refinement loop: reconciliation failures trigger FailureInterpreterAgent diagnosis → retry hint → re-translation
- Cumulative code execution: each block is executed with all prior blocks' outputs in scope, eliminating cross-block NameErrors
- Sandboxed Python executor microservice: generated code never runs inside the worker process
- `.sas7bdat` binary dataset ingestion via `pyreadstat`; ZIP bulk upload (`.sas`, `.sas7bdat`, `.csv`, `.log`, `.xlsx`, `.xls`)

**API and data model**
- 17 Alembic migrations: jobs, block revisions, job traces, explain sessions
- Full REST API: migrate, job status, migration plan, lineage, documentation, block edit, refine, cancel, SSE live trace, chat Q&A
- Human edits and agent re-translations stored as versioned block revisions with unified diffs
- SSE live trace stream: real-time per-block progress events during job execution

**Frontend (React + Vite + TypeScript + Tailwind + shadcn/ui)**
- Jobs page: upload dialog, jobs table, live Activity indicator during execution
- Job detail: 5-tab view (Plan / Editor / Report / Lineage / History)
  - **Plan tab:** migration plan summary, per-block table with strategy badges, confidence, reconciliation status, rationale popovers, View Code dialog (SAS + Python side-by-side, Monaco editors)
  - **Editor tab:** SAS EG–style split layout — file explorer, Monaco code editor, bottom panel (Code / Log / Output / History sub-tabs), block revision history with Monaco DiffEditor
  - **Report tab:** trust report with confidence bar, version history rail, inline TipTap editor
  - **Lineage tab:** React Flow graph with multi-level toggle (Blocks / Files / Pipeline), DATA\_FILE nodes for uploaded data files, column-count edge labels
  - **History tab:** version timeline with agent / human edit icons
- Full-screen editor at `/jobs/:id/editor` with URL-based tab return
- Global Lineage page: cross-migration ReactFlow graph (multi-migration merge)
- Explain page: chat Q&A with two modes (Migration Chat / SAS General), suggestion chips, Monaco code blocks, session restore
- Docs page: migration documentation cards (proposed / accepted), confidence/risk badges, TipTap popup with Plain English / Technical tabs
- Live Trace popup: real-time job progress with per-block colour states, expandable recon panels, pipeline:full summary banner

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — runs the full five-service stack
- [uv](https://docs.astral.sh/uv/) — Python package manager
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- [Claude Code](https://claude.ai/code) — required for the development workflow
- Node.js 22 LTS — only needed outside Docker (version pinned in `src/frontend/.nvmrc`)

---

## Setup

```bash
git clone <repo-url>
cd rosetta-decode

uv sync --extra dev          # install Python deps + dev tools
uv run pre-commit install    # register git hooks

cp .env.example .env
# set ANTHROPIC_API_KEY and review other values
```

Minimum `.env`:

```
DATABASE_URL=postgresql+asyncpg://rosetta:rosetta@localhost:5432/rosetta
CLOUD=false
LLM_MODEL=anthropic:claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...
LOG_LEVEL=INFO
POLL_INTERVAL_SECONDS=5
```

```bash
make dev        # build images and start all five services
make dev-down   # stop everything
make dev-logs   # tail logs from all containers
```

| Service      | URL                            |
| ------------ | ------------------------------ |
| Backend API  | `http://localhost:8000`      |
| API docs     | `http://localhost:8000/docs` |
| Frontend     | `http://localhost:5173`      |
| Executor API | `http://localhost:8001`      |

---

## How to contribute

> ⚠️ **Never close Claude Code without running `/session-end`.** The journal is how the next contributor picks up exactly where you left off. Skipping it means lost context, duplicated work, and broken continuity.

This project is built with [Claude Code](https://claude.ai/code) using a multi-agent setup. **All work must go through the orchestrator agent** — type `@orchestrator` in Claude Code to invoke it. It owns session context, feature planning, and commit gating. Never write code, plan features, or commit without going through it first.

---

## Claude agentic workflow

### Agents

Five specialist agents collaborate via the Claude Code Agent SDK. Each agent owns a specific domain and delegates work it does not own.

| Agent | Role | When Claude invokes it |
|---|---|---|
| `orchestrator` | Default entry point. Runs `/session-start`, delegates to specialists, gates commits. Never writes code directly. | Every session — always start here via `@orchestrator` |
| `backend-builder` | Implements Python: FastAPI routes, worker engine, Pydantic AI agents, Alembic migrations, validation | When the task touches `src/backend/` or `src/worker/` |
| `frontend-builder` | Implements React/TS: components, pages, API client calls, Tailwind, shadcn/ui | When the task touches `src/frontend/` |
| `fullstack-planner` | Read-only cross-cutting analysis — API contracts, type alignment, sequencing across layers | When a feature spans both backend and frontend and the interface contract needs clarifying |
| `tester` | Runs `make test`, interprets coverage, reports pass/fail back to the orchestrator | After any implementation is complete |

**Rule:** the orchestrator delegates via the Agent tool. It never writes implementation code itself. Agents never commit — only the orchestrator gates commits via `/git-committer`.

---

### Skills (slash commands)

Skills are reusable routines invoked in the Claude Code conversation. Type `/skill-name` to run one.

#### User-invoked skills

These are run explicitly by the developer at the right moment in the workflow.

| Skill | When to use |
|---|---|
| `/session-start` | **First thing every session.** Reads `journal/SESSIONS.md`, `journal/BACKLOG.md`, `docs/plans/` for any in-progress plan, then confirms context before proposing work. |
| `/session-end` | **Before closing Claude Code.** Updates the active feature plan, appends to `journal/SESSIONS.md`, updates `journal/BACKLOG.md` and `journal/DECISIONS.md`, then calls `/git-committer`. |
| `/plan-feature` | **Before implementing any new feature.** Reads docs, breaks the feature into ordered subtasks, writes `docs/plans/F<N>-<slug>.md`, enters plan mode. No code is written until you approve the plan. |
| `/test-runner` | **When you want to run the test suite.** Wraps `make test`, interprets results and coverage, and reports back. Never call `pytest` or `uv run pytest` directly. |
| `/git-pr-summary` | **When opening a pull request.** Generates a copy-paste ready PR description in standard Markdown format from the commit history. |

#### Claude-invoked skills

These are triggered automatically by context — the orchestrator calls them without prompting.

| Skill | Triggered when |
|---|---|
| `feature-planner` | You say "build feature X" or "implement F<N>" — reads the feature definition, breaks into subtasks, writes the plan file, enters plan mode |
| `backend-builder` | Implementation task touches Python backend code |
| `frontend-builder` | Implementation task touches React/TS frontend code |
| `git-committer` | Before any `git commit` — enforces conventional commit format (`feat:`, `fix:`, `chore:`, etc.), stages specific files by name (never `git add -A`), shows the message before committing |
| `git-branch-setup` | After plan approval, before implementation starts — ensures the correct `feat/F<N>-<slug>` branch exists and is checked out |
| `test-runner` | You say "run tests", "check tests", "are tests passing", or ask about coverage |

---

### Typical session flow

```
1. Open Claude Code → @orchestrator → /session-start
   Orchestrator reads journal + active plan, confirms what's next.

2. /plan-feature  (for new features only)
   Orchestrator writes docs/plans/F<N>-<slug>.md, enters plan mode.
   You review and approve — no code written until this step.

3. Implementation
   Orchestrator delegates to backend-builder / frontend-builder agents.
   They write code; orchestrator stays in the loop.

4. /test-runner
   Tester agent runs make test, reports coverage and failures.
   Backend-builder fixes failures if any.

5. /git-committer  (when everything passes)
   Stages specific files, drafts conventional commit, runs pre-commit hooks.

6. /session-end  ← NEVER SKIP THIS
   Updates plan, journal, backlog, decisions. Commits journal entry.
```

### Starting a session

Open Claude Code, invoke the orchestrator, then run:

```
@orchestrator
```

The orchestrator runs `/session-start`, reads the journal, checks for any active feature plan in `docs/plans/`, and tells you exactly what's next. It waits for you to confirm before proposing any work. **Always do this before anything else.**

### Planning a feature

```
/plan-feature
```

The orchestrator reads all relevant docs, breaks the feature into ordered subtasks (one artefact each), writes `docs/plans/F<N>-<slug>.md`, updates the backlog, and enters plan mode. **No code is written until you approve the plan.**

### Running tests

```
make test
```

Never call `pytest` or `uv run pytest` directly. `make test` runs the full suite with coverage, plus `tsc --noEmit`, ESLint, and the Vite build — the same checks CI runs.

### Committing

```
/git-committer
```

Stages specific files by name (never `git add -A`), drafts a conventional commit message (`feat:`, `fix:`, `chore:`, etc.), and shows it to you before running `git commit`. Pre-commit hooks run automatically.

### Ending a session

```
/session-end
```

Updates the active feature plan, backlog, and decisions log. Appends a new entry to `journal/SESSIONS.md` with what was done, open questions, and the concrete first step for next session. Then calls `/git-committer` for the journal commit.

> ⚠️ **Never close Claude Code without running `/session-end`.** The journal is how the next contributor picks up exactly where you left off. Skipping it means lost context, duplicated work, and broken continuity.

---

## Project structure

```
rosetta-decode/
│
├── src/
│   ├── backend/                     # FastAPI service — HTTP API
│   │   ├── main.py                  # FastAPI app entrypoint
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── migrate.py       # POST /migrate — validate, persist, enqueue
│   │   │   │   ├── jobs.py          # GET /jobs/{id}, /plan, /lineage, /doc, /trace/stream, etc.
│   │   │   │   └── explain.py       # POST /explain, POST /explain/job — chat Q&A
│   │   │   └── schemas.py           # Pydantic request/response models
│   │   ├── db/
│   │   │   ├── models.py            # SQLAlchemy ORM models (Job, BlockRevision, ExplainSession, JobTrace)
│   │   │   └── session.py           # Async engine + session factory
│   │   └── core/
│   │       ├── config.py            # pydantic-settings (reads .env)
│   │       └── logging.py           # structured JSON logging
│   │
│   ├── worker/                      # Async job runner — no inbound HTTP
│   │   ├── main.py                  # Poll loop: picks queued jobs, runs pipeline
│   │   ├── engine/
│   │   │   ├── models.py            # SASBlock, GeneratedBlock, MigrationPlan, BlockPlan Pydantic models
│   │   │   ├── parser.py            # SASParser — DATA/PROC/IML/FORMAT blocks; %LET/%MACRO; MacroDef
│   │   │   ├── macro_expander.py    # %macro/%mend expansion (regex + LLM fallback)
│   │   │   ├── llm_client.py        # LLMClient — Pydantic AI agent, structured output
│   │   │   ├── codegen.py           # CodeGenerator — per-file .py modules + pipeline.py
│   │   │   ├── router.py            # TranslationRouter — routes blocks to correct agent
│   │   │   ├── stub_generator.py    # StubGenerator — manual/skip/untranslatable fallback
│   │   │   ├── block_executor.py    # Runs a single block's generated code in isolation
│   │   │   ├── trace.py             # TraceEmitter — SSE job-trace events
│   │   │   ├── doc_generator.py     # Orchestrates LineageEnricherAgent + DocumentationAgent
│   │   │   └── agents/
│   │   │       ├── analysis.py          # AnalysisAgent — complexity score, risk flags, strategy hints
│   │   │       ├── migration_planner.py # MigrationPlannerAgent — per-block strategy/risk/confidence
│   │   │       ├── data_step.py         # DataStepAgent — SAS DATA step → pandas
│   │   │       ├── proc.py              # ProcAgent — PROC SQL/SORT/MEANS/other → pandas/SQLAlchemy
│   │   │       ├── generic_proc.py      # GenericProcAgent — fallback for unrecognised PROCs
│   │   │       ├── macro_resolver.py    # MacroResolverAgent — parameterised macro expansion
│   │   │       ├── failure_interpreter.py # FailureInterpreterAgent — explains recon failures
│   │   │       ├── lineage_enricher.py  # LineageEnricherAgent — column-level data flow
│   │   │       ├── documentation.py     # DocumentationAgent — plain-language Markdown summary
│   │   │       ├── plain_english.py     # PlainEnglishAgent — structured 5-section business doc
│   │   │       └── shared.py            # SHARED_TRANSLATION_RULES, shared prompt utilities
│   │   ├── validation/
│   │   │   └── reconciliation.py    # ReconciliationService — schema, row count, aggregate checks
│   │   ├── compute/
│   │   │   ├── base.py              # ComputeBackend ABC
│   │   │   ├── local.py             # LocalBackend — pandas + PostgreSQL
│   │   │   └── factory.py           # BackendFactory — reads CLOUD env var
│   │   └── core/
│   │       └── config.py            # Worker settings
│   │
│   ├── executor/                    # Python sandbox microservice (port 8001)
│   │   ├── main.py                  # FastAPI app — POST /execute
│   │   ├── runner.py                # Subprocess + tempfile isolated execution
│   │   └── recon.py                 # Self-contained ReconciliationService for executor
│   │
│   └── frontend/                    # React + Vite + TypeScript + Tailwind + shadcn/ui
│       └── src/
│           ├── App.tsx              # Root component + routing
│           ├── components/
│           │   ├── ui/              # shadcn/ui primitives
│           │   ├── JobDetail/       # Per-job detail components (tabs, panels, modals)
│           │   │   ├── PlanTab.tsx          # Plan tab — migration plan + block table
│           │   │   ├── EditorTab.tsx        # Editor tab — SAS EG-style split + history
│           │   │   ├── ReportTab.tsx        # Report tab — trust report + version history
│           │   │   ├── LineageTab.tsx       # Lineage tab — React Flow graph
│           │   │   ├── BlockPlanTable.tsx   # Block table with groupBy, rationale, recon
│           │   │   └── ExecutionOutputPanel.tsx # Execution stdout/stderr/recon cards
│           │   ├── AppSidebar.tsx   # Navigation sidebar
│           │   ├── LiveTraceDialog.tsx  # SSE live job-trace popup
│           │   ├── LineageGraph.tsx     # React Flow lineage graph (multi-level: Blocks/Files/Pipeline)
│           │   ├── MonacoDiffViewer.tsx # Monaco DiffEditor (inline/side-by-side toggle)
│           │   ├── MonacoEditor.tsx     # Monaco Editor
│           │   ├── TiptapEditor.tsx     # Rich-text editor (Tiptap)
│           │   ├── RightSidebar.tsx     # Collapsible right sidebar (subtitle + sidebarKey)
│           │   └── VersionHistoryRail.tsx # Version timeline (agent/human icons)
│           ├── pages/
│           │   ├── JobsPage.tsx         # Jobs table + upload dialog
│           │   ├── JobDetailPage.tsx    # 5-tab job detail (Plan/Editor/Report/Lineage/History)
│           │   ├── EditorFullPage.tsx   # Full-screen editor (/jobs/:id/editor)
│           │   ├── GlobalLineagePage.tsx # Cross-migration lineage (Pipeline/Datasets/Columns)
│           │   ├── ExplainPage.tsx      # Chat Q&A (Migration Chat + SAS General modes)
│           │   └── DocsPage.tsx         # Documentation cards (proposed/accepted)
│           └── lib/
│               ├── utils.ts         # Tailwind class utilities
│               └── lineage-merge.ts # Multi-migration ReactFlow graph merge utility
│
├── tests/
│   ├── test_parser.py               # SASParser unit tests
│   ├── test_codegen.py              # CodeGenerator unit tests
│   ├── test_llm_client.py           # LLMClient (mocked) tests
│   ├── test_local_backend.py        # LocalBackend tests
│   ├── test_factory.py              # BackendFactory tests
│   ├── test_api_routes.py           # FastAPI route tests (httpx AsyncClient)
│   ├── test_api_smoke.py            # Smoke: POST /migrate + GET /jobs/{id}
│   ├── test_worker_main.py          # Worker poll loop tests
│   ├── test_agents.py               # Agent factory + structured output tests
│   ├── test_router.py               # TranslationRouter tests
│   ├── test_explain_routes.py       # /explain route tests
│   └── reconciliation/
│       ├── test_data_step.py        # Reconciliation test — DATA step → DataFrame
│       └── test_proc_sort.py        # Reconciliation test — PROC SORT → sorted DataFrame
│
├── alembic/
│   └── versions/                    # 001 → 017 migrations (jobs, block_revisions, job_traces, etc.)
│
├── sample_data/                     # Sample SAS files + reference CSVs for testing
├── docs/
│   ├── architecture.md              # Full architecture doc
│   ├── features.md                  # Feature list F1–F21
│   ├── mvp-scope.md                 # MVP definition
│   ├── coding-standards.md          # Required conventions
│   ├── plans/                       # Active feature plans (F<N>-<slug>.md)
│   │   └── latest/                  # Current in-progress plans
│   └── context/
│       ├── sas-patterns.md          # SAS pattern catalog used by the LLM
│       └── migration-approaches.md  # Why LLM-assisted conversion was chosen
├── journal/
│   ├── SESSIONS.md                  # Per-session log (most recent on top)
│   ├── BACKLOG.md                   # Phased task list — source of truth for what's next
│   └── DECISIONS.md                 # Architectural decisions with rationale
│
├── scripts/
│   └── check_npm_lockfile.sh        # Pre-commit: validates package-lock.json is in sync
├── .github/workflows/ci.yml         # CI pipeline (see below)
├── .pre-commit-config.yaml          # Pre-commit hook definitions
├── docker-compose.yml               # Five-service dev stack
├── pyproject.toml                   # Python deps, ruff, mypy, pytest config
└── Makefile                         # All dev commands
```

---

## Architecture

Five Docker services. The only shared state is PostgreSQL.

```
┌──────────────────────────────────────────────────────────────────────┐
│  frontend  (React + Vite + TypeScript + Tailwind + shadcn/ui)        │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ REST / SSE polling
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│  backend  (FastAPI, port 8000)                                        │
│  POST /migrate      → validate, persist files, insert job (queued)   │
│  GET  /jobs/{id}    → status + python_code + report                  │
│  GET  /jobs/{id}/plan    → MigrationPlan per-block detail            │
│  GET  /jobs/{id}/lineage → EnrichedLineage graph                     │
│  GET  /jobs/{id}/doc     → plain-language documentation              │
│  GET  /jobs/{id}/trace/stream → SSE live job trace                   │
│  PATCH /jobs/{id}/blocks/{block_id}/python → human edit              │
│  POST /jobs/{id}/refine  → agent re-translation                      │
│  POST /explain, POST /explain/job → chat Q&A                         │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ shared Postgres
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  postgres  (PostgreSQL 16)                                            │
│  jobs · block_revisions · explain_sessions · job_traces              │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ polls for queued jobs
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  worker  (same Python src, separate image — no inbound port)         │
│                                                                       │
│  SASParser → MacroExpander → Agents → Router → CodeGenerator        │
│  → RemoteReconciliationService (HTTP → executor)                     │
│                                                                       │
│  ComputeBackend (ABC)                                                 │
│    LocalBackend      → pandas + PostgreSQL        (CLOUD=false)      │
│    DatabricksBackend → PySpark                    (Phase 4, stub)    │
└──────────────────────┬───────────────────────────────────────────────┘
                       │ HTTP (POST /execute)
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  executor  (FastAPI, port 8001 — subprocess sandbox)                 │
│  POST /execute → runs generated Python in isolated tempfile process  │
│  Uploads mounted read-only at /workspace/data                        │
└──────────────────────────────────────────────────────────────────────┘
                       │
              Hosted LLM API
        (provider from LLM_MODEL env var)
```

**Key design decisions:**

- **No `if CLOUD` in business logic.** All execution differences are behind `ComputeBackend`. `BackendFactory` is the only place that reads `CLOUD`.
- **Deterministic output.** `input_hash = SHA256(all SAS files)`. Same input → same Python output, always.
- **Nothing silently dropped.** Untranslatable SAS constructs become `# SAS-UNTRANSLATABLE: <reason>` — never removed.
- **Audit trail.** Every generated line group carries `# SAS: <filename>:<line>`. Required for sign-off.
- **Reconciliation is not optional.** Every new SAS construct handler ships with a reconciliation test or the feature is not done.
- **Executor isolation.** Code execution runs in a separate sandboxed microservice (`executor`) — the worker never executes arbitrary Python in its own process.

### Worker pipeline (per job)

```
SASParser.parse(files)
  → ParseResult(blocks, macro_vars, macro_defs)   (dependency-ordered via Kahn's topo sort)
  ↓
MacroExpander.expand(blocks)
  → resolved SAS source (regex + MacroResolverAgent LLM fallback)
  ↓
AnalysisAgent.analyse(parse_result)
  → AnalysisResult (risk score, construct flags, strategy hints)
  ↓
MigrationPlannerAgent.plan(analysis_result)       ← parser block_type is authoritative
  → MigrationPlan (per-block strategy / risk / confidence)
  → persisted as migration_plan JSONB
  ↓
TranslationRouter.route(block, block_plan)         (for each block)
  → DataStepAgent / ProcAgent / GenericProcAgent / _SimpleCopyHelper
  → GeneratedBlock (code + provenance + confidence_score)
  ↓
CodeGenerator.assemble(blocks)
  → per-file .py modules + pipeline.py             (# SAS:<f>:<ln> on every group)
  ↓
RemoteReconciliationService → executor POST /execute
  → schema parity / row count / aggregate parity
  → on failure: FailureInterpreterAgent → retry hint fed back to TranslationRouter
  ↓
LineageEnricherAgent (best-effort)
  → EnrichedLineage (FileNode, FileEdge, PipelineStep, BlockStatus)
  → persisted as lineage JSONB
  ↓
DocumentationAgent + PlainEnglishAgent (best-effort)
  → Markdown doc (5 sections) → GET /jobs/{id}/doc
  ↓
job updated: status=done/proposed/under_review, generated_files=..., migration_plan=...
```

### Agentic pipeline

Each job runs through a sequence of LLM agents. All agents use structured Pydantic AI output. Best-effort agents (marked ✦) are wrapped in `try/except` — failure logs a warning but never aborts the job.

```
SASParser.parse()
  │
  ├─► MacroResolverAgent ──── resolves %macro/%mend definitions; LLM fallback for
  │                           complex parameterised macros that regex cannot expand
  │
  ├─► AnalysisAgent ─────────── reads the full ParseResult; produces a risk score,
  │                              identifies complex constructs, and sets translation
  │                              strategy hints for downstream agents
  │
  ├─► MigrationPlannerAgent ✦ ── reads AnalysisAgent output; assigns per-block
  │                               strategy (translate / stub / skip), risk level,
  │                               and confidence; block_type from parser is
  │                               authoritative (LLM value is ignored);
  │                               persisted as migration_plan JSONB
  │
  ├─► TranslationRouter ──────── routes each block to the correct translation agent
  │       │                      based on block_type; trivial SET+KEEP/DROP DATA
  │       │                      steps are handled by _SimpleCopyHelper (no LLM);
  │       │                      manual/manual_ingestion routed via _BestEffortAgentAdapter
  │       ├─► DataStepAgent ──── DATA step blocks → pandas DataFrame operations;
  │       │                      emits confidence + uncertainty_notes per block
  │       ├─► ProcAgent ──────── PROC SQL / PROC SORT / PROC MEANS → pandas/SQLAlchemy
  │       └─► GenericProcAgent ─ PROC IML / FORMAT and other PROCs; stubs unknown PROCs
  │
  ├─► CodeGenerator.assemble() ── merges GeneratedBlocks into per-file .py modules
  │                                + pipeline.py; every group gets # SAS:<f>:<ln>
  │
  ├─► RemoteReconciliationService → executor POST /execute
  │       │                         schema / row-count / aggregate parity checks
  │       │                         (cumulative code execution — all prior blocks included)
  │       └─► FailureInterpreterAgent ✦ ── reads the reconciliation report +
  │                                        generated code; explains the root cause
  │                                        in plain language; feeds retry hint back
  │                                        into second-phase re-translation
  │
  ├─► LineageEnricherAgent ✦ ── traces column-level data flow across blocks;
  │                              FileNode/FileEdge/PipelineStep multi-level graph;
  │                              DATA_FILE nodes injected for uploaded data files;
  │                              persisted as enriched_lineage in the job record
  │
  ├─► DocumentationAgent ✦ ──── generates a plain-language Markdown summary of
  │                              what the SAS program does, keyed to the business
  │                              domain; returned by GET /jobs/{id}/doc
  │
  └─► PlainEnglishAgent ✦ ──── structured 5-section business doc (Purpose, Source
                               Data, How It Works, Outputs, Migration Status);
                               used in DocsPage proposed/accepted cards
```

**Agent summary:**

| Agent | Role | Output |
|---|---|---|
| `MacroResolverAgent` | Expands `%macro`/`%mend` definitions, including parameterised macros the regex pre-processor can't handle | Resolved macro text |
| `AnalysisAgent` | Scores overall complexity, flags high-risk constructs, sets strategy hints | `AnalysisResult` (risk, flags, hints) |
| `MigrationPlannerAgent` ✦ | Assigns per-block strategy/risk/confidence; produces the plan shown in the UI Plan tab; parser `block_type` is authoritative | `MigrationPlan` → `migration_plan` JSONB |
| `DataStepAgent` | Translates SAS DATA steps to pandas — merges, filters, column derivations, conditionals | `GeneratedBlock` with provenance comments |
| `ProcAgent` | Translates PROC SQL / PROC SORT / PROC MEANS; stubs anything unrecognised | `GeneratedBlock` with provenance comments |
| `GenericProcAgent` | Handles PROC IML, PROC FORMAT, and other non-standard PROCs | `GeneratedBlock` with provenance comments |
| `FailureInterpreterAgent` ✦ | Explains reconciliation failures in plain English; generates a retry hint for re-translation | Human-readable failure summary + retry hint |
| `LineageEnricherAgent` ✦ | Traces column-level data flow; FileNode/FileEdge/PipelineStep multi-level graph; DATA_FILE node injection | `EnrichedLineage` → lineage JSONB |
| `DocumentationAgent` ✦ | Writes a business-readable Markdown summary of what the program does | Markdown string → `GET /jobs/{id}/doc` |
| `PlainEnglishAgent` ✦ | Structured 5-section business doc (Purpose, Source Data, How It Works, Outputs, Migration Status) | Structured doc → DocsPage |

### PostgreSQL schema

Schema is managed by Alembic (17 migrations, `alembic/versions/`). Async access via SQLAlchemy + asyncpg.

**Core tables:**

```sql
-- jobs: one row per migration job
CREATE TABLE jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status              TEXT NOT NULL,  -- queued|running|done|failed|proposed|under_review|cancelled
    input_hash          TEXT NOT NULL,
    files               JSONB NOT NULL,           -- { "script.sas": "<content>", ... }
    llm_model           TEXT,
    python_code         TEXT,
    generated_files     JSONB,                    -- { "module.py": "<content>", ... }
    migration_plan      JSONB,                    -- MigrationPlan (per-block strategy/risk/confidence)
    enriched_lineage    JSONB,
    report              JSONB,                    -- { checks: [...] }
    parent_job_id       UUID REFERENCES jobs(id), -- set for refine jobs
    skip_llm            BOOLEAN NOT NULL DEFAULT FALSE,
    error               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- block_revisions: every human or agent edit to a block
CREATE TABLE block_revisions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID NOT NULL REFERENCES jobs(id),
    block_id    TEXT NOT NULL,
    python_code TEXT NOT NULL,
    unified_diff TEXT,
    trigger     TEXT NOT NULL,  -- "human" | "agent"
    recon_checks JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- job_traces: SSE live-trace events (F20)
CREATE TABLE job_traces (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id     UUID NOT NULL REFERENCES jobs(id),
    event_type TEXT NOT NULL,
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- explain_sessions: chat Q&A sessions
CREATE TABLE explain_sessions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id     UUID REFERENCES jobs(id),
    mode       TEXT NOT NULL,  -- "migration" | "general"
    messages   JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## Infrastructure (Azure / Terraform)

The Azure resources that back the hosted LLM live in [`infra/`](infra/), managed with
Terraform. This replaces the borrowed model endpoint with our own.

### What it provisions

One resource group per environment owning:

- **AI Foundry** — AI Services account (`AIServices`) + Foundry hub + project, and the
  model deployment (`gpt-5.4`, Global/Data-Zone Standard). An optional second
  deployment (Claude) is gated behind `deploy_claude`.
- **Key Vault** — stores the model API key (`model-api-key`); the endpoint is a
  Terraform output, not a secret.
- **Storage account** — required backing store for the Foundry hub.
- **Network** — VNet + a private-endpoint subnet; the AI Services account is reached
  over a private endpoint with a private DNS zone.

### Layout

```
infra/
├── modules/          # resource_group, network, storage, key_vault, ai_foundry
├── env/
│   ├── common.tfvars        # shared values (region, model, capacity, …)
│   ├── dev.tfvars           # per-env: environment + subscription_id only
│   └── prd.tfvars
│   └── *.backend.hcl        # per-env remote-state key
├── main.tf           # wires the modules together
└── scripts/bootstrap-backend.sh   # creates the remote-state backend
```

One root config; `dev` and `prd` differ only by their `*.tfvars` / `*.backend.hcl`.
Resource names are derived from `project` + `environment`.

### Deploy

All commands are Make targets (run from repo root); `ENV` is `dev` or `prd`.

```bash
# 0. Log into the ADC subscription
az login

# 1. Create the remote-state backend (one-time, shared by dev+prd).
#    Derives a globally-unique storage account name and writes infra/backend.hcl.
make tf-bootstrap

# 2. Init + review + apply for an environment
make tf-init  ENV=dev
make tf-plan  ENV=dev      # read the plan
make tf-apply ENV=dev      # type yes if you agree

# 3. Read outputs (endpoint is here; key is in Key Vault)
cd infra && terraform output ai_services_endpoint && cd ..
az keyvault secret show --vault-name kv-rosetta-decode-dev \
  --name model-api-key --query value -o tsv
```

Wire the worker to the deployed model via `.env`:

```
AZURE_AI_FOUNDRY_ENDPOINT=<terraform output ai_services_endpoint>
AZURE_AI_FOUNDRY_API_KEY=<Key Vault: model-api-key>
LLM_MODEL=openai:gpt-5.4
```

### Tear down

```bash
make tf-destroy ENV=dev    # one environment
make tf-nuke               # destroy dev + prd, then the state backend
```

> **Key Vault auth:** the vault uses access policies (not RBAC) so a `Contributor`
> can self-grant secret access during apply. Switch to RBAC once an admin can assign
> `Key Vault Secrets Officer` — see the note in `modules/key_vault/main.tf`.

See [`infra/README.md`](infra/README.md) for module-level detail and backend config.

---

## Quality gates: pre-commit and CI

### Pre-commit hooks (run on every `git commit`)

Defined in `.pre-commit-config.yaml`. Installed via `uv run pre-commit install`.

| Hook                    | What it does                                                                                                                                   |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `no-commit-to-branch` | Blocks direct commits to `main`                                                                                                              |
| `npm-lockfile-sync`   | Runs `npm ci --dry-run` in `src/frontend/` — fails if `package.json` and `package-lock.json` are out of sync, before the commit lands |
| `ruff`                | Lints and auto-fixes Python (`src/`, `tests/`)                                                                                             |
| `ruff-format`         | Enforces consistent formatting                                                                                                                 |
| `mypy`                | Strict type checking with all relevant stubs                                                                                                   |

Hooks run automatically. `--no-verify` is forbidden.

### CI pipeline (`.github/workflows/ci.yml`)

Triggered on push to `main` or any `feat/**` branch, and on PRs targeting `main`.

| Job                | Needs     | What it does                                                                                                                               |
| ------------------ | --------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `check`          | —        | ruff lint, ruff format check, mypy                                                                                                         |
| `test`           | `check` | pytest — excludes `reconciliation`, `cloud`, `integration` markers                                                                  |
| `reconciliation` | `test`  | Spins up Postgres, runs Alembic migrations, runs `@pytest.mark.reconciliation` tests with 80% coverage gate on `src/worker/validation` |
| `frontend`       | —        | `npm ci --dry-run` (lockfile guard), `npm ci`, `tsc --noEmit`, ESLint, Vite build                                                    |
| `docker`         | —        | Builds all Dockerfiles (no push) with scoped GHA layer cache per image                                                               |

The `docker` job runs independently — Dockerfile correctness is unrelated to Python logic. The `frontend` job also runs independently; it does not wait for Python jobs.

**Coverage gates:** main test suite ≥ 90% on all of `src/`; reconciliation suite ≥ 80% on `src/worker/validation/` only (separate `.coveragerc-reconciliation`).

---

## Key docs

| Doc                          | What it covers                                                    |
| ---------------------------- | ----------------------------------------------------------------- |
| `docs/architecture.md`     | Full architecture, API contracts, ComputeBackend interface        |
| `docs/features.md`         | Feature list F1–F21 with phase and area                          |
| `docs/mvp-scope.md`        | MVP definition and definition of done                             |
| `docs/coding-standards.md` | Required conventions for Python and TypeScript                    |
| `journal/BACKLOG.md`       | Phased task list — single source of truth for what to build next |
| `journal/DECISIONS.md`     | Architectural decisions with rationale and revisit conditions     |
