# Introduction

Legacy SAS codebases are a liability. They encode decades of business logic in a language no one wants to maintain, tied to a vendor most organisations are trying to leave. **rosetta-decode** uses LLMs to extract that logic and translate it into production-ready Python ETL pipelines — runnable locally on pandas/PostgreSQL, or on Databricks via PySpark, controlled by a single environment flag.

A reconciliation engine validates every migration automatically: same SAS input, same output data, provably. Every generated line carries a `# SAS: <file>:<line>` provenance comment so auditors can trace any transformation back to its source.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — runs the full four-service stack
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
make dev        # build images and start all four services
make dev-down   # stop everything
make dev-logs   # tail logs from all containers
```

| Service     | URL                            |
| ----------- | ------------------------------ |
| Backend API | `http://localhost:8000`      |
| API docs    | `http://localhost:8000/docs` |
| Frontend    | `http://localhost:5173`      |

---

## How to contribute

⚠️ **Never close Claude Code without running `/session-end`.** The journal is how the next contributor picks up exactly where you left off. Skipping it means lost context, duplicated work, and broken continuity.

This project is built with [Claude Code](https://claude.ai/code) using a multi-agent setup. **All work must go through the orchestrator agent** — type `@orchestrator` in Claude Code to invoke it. It owns session context, feature planning, and commit gating. Never write code, plan features, or commit without going through it first.

### Starting a session

Open Claude Code, invoke the orchestrator, then run:

```
@orchestrator
/session-start
```

The orchestrator reads the journal, checks for any active feature plan in `docs/plans/`, and tells you exactly what's next. It waits for you to confirm before proposing any work. **Always do this before anything else.**

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
│   │   │   │   └── jobs.py          # GET /jobs/{id}, /audit, /download
│   │   │   └── schemas.py           # Pydantic request/response models
│   │   ├── db/
│   │   │   ├── models.py            # SQLAlchemy Job ORM model
│   │   │   └── session.py           # Async engine + session factory
│   │   └── core/
│   │       ├── config.py            # pydantic-settings (reads .env)
│   │       └── logging.py           # structured JSON logging
│   │
│   ├── worker/                      # Async job runner — no inbound HTTP
│   │   ├── main.py                  # Poll loop: picks queued jobs, runs pipeline
│   │   ├── engine/
│   │   │   ├── models.py            # SASBlock, GeneratedBlock Pydantic models
│   │   │   ├── parser.py            # SASParser — DATA step + PROC SQL extraction
│   │   │   ├── llm_client.py        # LLMClient — Pydantic AI agent, structured output
│   │   │   └── codegen.py           # CodeGenerator — assembles pipeline.py with provenance
│   │   ├── validation/
│   │   │   └── reconciliation.py    # ReconciliationService — schema, row count, aggregate checks
│   │   ├── compute/
│   │   │   ├── base.py              # ComputeBackend ABC
│   │   │   ├── local.py             # LocalBackend — pandas + PostgreSQL
│   │   │   └── factory.py           # BackendFactory — reads CLOUD env var
│   │   └── core/
│   │       └── config.py            # Worker settings
│   │
│   └── frontend/                    # React + Vite + TypeScript + Tailwind + shadcn/ui
│       └── src/
│           ├── App.tsx              # Root component + routing
│           ├── components/ui/       # shadcn/ui primitives
│           └── lib/utils.ts         # Tailwind class utilities
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
│   └── reconciliation/
│       └── test_data_step.py        # Reconciliation test — DATA step → DataFrame
│
├── alembic/
│   └── versions/
│       ├── 001_create_jobs_table.py
│       └── 002_add_llm_model.py
│
├── samples/                         # Sample SAS files + reference CSVs for testing
├── docs/
│   ├── architecture.md              # Full architecture doc
│   ├── features.md                  # Feature list F1–F18
│   ├── mvp-scope.md                 # MVP definition
│   ├── coding-standards.md          # Required conventions
│   ├── plans/                       # Active feature plans (F<N>-<slug>.md)
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
├── docker-compose.yml               # Four-service dev stack
├── pyproject.toml                   # Python deps, ruff, mypy, pytest config
└── Makefile                         # All dev commands
```

---

## Architecture

Four Docker services. The only shared state is PostgreSQL.

```
┌──────────────────────────────────────────────────────────────────────┐
│  frontend  (React + Vite + TypeScript + Tailwind + shadcn/ui)        │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ REST / polling
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│  backend  (FastAPI)                                                   │
│  POST /migrate   → validate, persist files, insert job (status=queued)│
│  GET  /jobs/{id} → { status, python_code, report }                   │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ shared Postgres
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  postgres  (PostgreSQL 16)                                            │
│  jobs: id · status · input_hash · files (JSONB) · python_code        │
│         · report (JSONB) · error · created_at · updated_at           │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ polls for queued jobs
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  worker  (same Python src, separate image — no inbound port)         │
│                                                                       │
│  SASParser → LLMClient (Pydantic AI) → CodeGenerator → Reconcile    │
│                                                                       │
│  ComputeBackend (ABC)                                                 │
│    LocalBackend      → pandas + PostgreSQL        (CLOUD=false)      │
│    DatabricksBackend → PySpark                    (Phase 4, stub)    │
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

### Worker pipeline (per job)

```
SASParser.parse(files)               → List[SASBlock]  (ordered by dependency)
  ↓
LLMClient.translate(block, patterns) → GeneratedBlock   (structured Pydantic AI output)
  ↓ (for each block)
CodeGenerator.assemble(blocks)       → pipeline.py      (with # SAS:<f>:<ln> on every group)
  ↓
ReconciliationService.run(ref_csv, python_code, backend)
  → schema parity check
  → row count check
  → aggregate parity check
  ↓
job updated: status=done, python_code=..., report=JSONB
```

### PostgreSQL schema

```sql
CREATE TABLE jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status      TEXT NOT NULL CHECK (status IN ('queued','running','done','failed')),
    input_hash  TEXT NOT NULL,
    files       JSONB NOT NULL,   -- { "script.sas": "<content>", ... }
    llm_model   TEXT,
    python_code TEXT,
    report      JSONB,            -- { checks: [{ name, status, detail? }] }
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Schema is managed by Alembic. Async access via SQLAlchemy + asyncpg.

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
| `docker`         | —        | Builds all three Dockerfiles (no push) with scoped GHA layer cache per image                                                               |

The `docker` job runs independently — Dockerfile correctness is unrelated to Python logic. The `frontend` job also runs independently; it does not wait for Python jobs.

**Coverage gates:** main test suite ≥ 90% on all of `src/`; reconciliation suite ≥ 80% on `src/worker/validation/` only (separate `.coveragerc-reconciliation`).

---

## Key docs

| Doc                          | What it covers                                                    |
| ---------------------------- | ----------------------------------------------------------------- |
| `docs/architecture.md`     | Full architecture, API contracts, ComputeBackend interface        |
| `docs/features.md`         | Feature list F1–F18 with phase and area                          |
| `docs/mvp-scope.md`        | MVP definition and definition of done                             |
| `docs/coding-standards.md` | Required conventions for Python and TypeScript                    |
| `journal/BACKLOG.md`       | Phased task list — single source of truth for what to build next |
| `journal/DECISIONS.md`     | Architectural decisions with rationale and revisit conditions     |
