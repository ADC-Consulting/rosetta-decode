# Session Journal

Most recent session on top. Each entry should answer:

- What did we do?

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
