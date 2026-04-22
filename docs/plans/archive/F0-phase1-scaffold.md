# F0 — Phase 1 Scaffold (Vertical Slice Foundation)

**Phase:** 1  
**Area:** Backend / Worker / Frontend / Infra  
**Status:** done

## Goal

Stand up the full four-service skeleton (postgres, backend, worker, frontend) so that every subsequent Phase 1 feature has a real place to land. By the end of this plan, a developer can run `make dev`, hit `POST /migrate`, and see a job row created in PostgreSQL. No migration logic yet — just the wiring: Docker Compose, service scaffolds, Alembic migration for the `jobs` table, `ComputeBackend` abstract interface, and `LocalBackend` stub. Tests pass, ruff passes, mypy passes.

## Acceptance Criteria

- [ ] `docker compose up` starts all four services without errors
- [ ] `POST /migrate` (multipart, 1+ `.sas` files) returns `{ job_id: "<uuid>" }` and inserts a `queued` row in `jobs`
- [ ] `GET /jobs/{id}` returns `{ status: "queued" }` for the created job
- [ ] Worker poll loop starts, picks up the queued job, marks it `running` (no migration logic — just transition)
- [ ] `ComputeBackend` ABC defined; `LocalBackend` stub instantiates without error
- [ ] `make test` exits 0
- [ ] `ruff check` and `mypy` pass

## Subtasks

### S01: docker-compose.yml — 4-service revision
**File:** `docker-compose.yml`  
**Depends on:** none  
**Done when:** `docker compose config` validates cleanly with postgres, backend, worker, frontend services on `rosetta-net`
- [x] done

### S02: pyproject.toml — add SQLAlchemy async + Alembic + asyncpg
**File:** `pyproject.toml`  
**Depends on:** none  
**Done when:** `uv sync` succeeds and `import sqlalchemy.ext.asyncio` works in the venv
- [x] done

### S03: backend core — settings + logging
**File:** `src/backend/core/config.py`, `src/backend/core/logging.py`  
**Depends on:** S02  
**Done when:** `Settings` (pydantic-settings) loads `DATABASE_URL`, `LLM_MODEL`, `CLOUD` from env; structured logger configured
- [x] done

### S04: database layer — SQLAlchemy async engine + session factory
**File:** `src/backend/db/session.py`  
**Depends on:** S03  
**Done when:** `get_async_session()` yields an `AsyncSession` connected to PostgreSQL
- [x] done

### S05: Alembic init + jobs table migration
**File:** `alembic/`, `alembic/versions/001_create_jobs_table.py`  
**Depends on:** S04  
**Done when:** `alembic upgrade head` creates the `jobs` table with all columns from the architecture spec
- [x] done

### S06: SQLAlchemy Job model
**File:** `src/backend/db/models.py`  
**Depends on:** S05  
**Done when:** `Job` ORM model maps to the `jobs` table; all columns typed
- [x] done

### S07: backend API — request/response schemas
**File:** `src/backend/api/schemas.py`  
**Depends on:** none  
**Done when:** `MigrateRequest`, `MigrateResponse`, `JobStatusResponse` Pydantic models defined
- [x] done

### S08: backend API — POST /migrate route
**File:** `src/backend/api/routes/migrate.py`  
**Depends on:** S06, S07  
**Done when:** endpoint validates uploaded `.sas` files, computes `input_hash`, inserts `queued` job, returns `{ job_id }`
- [x] done

### S09: backend API — GET /jobs/{id} route
**File:** `src/backend/api/routes/jobs.py`  
**Depends on:** S06, S07  
**Done when:** endpoint reads job by UUID, returns status + available fields; 404 on missing
- [x] done

### S10: backend Dockerfile + FastAPI app entrypoint
**File:** `src/backend/Dockerfile`, `src/backend/main.py`  
**Depends on:** S08, S09  
**Done when:** `docker build src/backend` succeeds; `uvicorn` starts and `/docs` loads
- [x] done

### S11: ComputeBackend ABC
**File:** `src/worker/compute/base.py`  
**Depends on:** none  
**Done when:** `ComputeBackend` abstract class defines `read_csv`, `run_sql`, `write_parquet`, `to_pandas` with type hints
- [x] done

### S12: LocalBackend stub
**File:** `src/worker/compute/local.py`  
**Depends on:** S11  
**Done when:** `LocalBackend` inherits `ComputeBackend`; methods raise `NotImplementedError` with a clear message (filled in later by F1/F3 work)
- [x] done

### S13: BackendFactory
**File:** `src/worker/compute/factory.py`  
**Depends on:** S12  
**Done when:** `BackendFactory.create()` reads `CLOUD` env var; returns `LocalBackend()` when `false`; raises `NotImplementedError` for `true` (Databricks deferred)
- [x] done

### S14: worker core — settings
**File:** `src/worker/core/config.py`  
**Depends on:** S02  
**Done when:** `WorkerSettings` loads `DATABASE_URL`, `CLOUD`, `LLM_MODEL` from env
- [x] done

### S15: worker poll loop
**File:** `src/worker/main.py`  
**Depends on:** S14, S13, S06  
**Done when:** worker polls for `queued` jobs every 5 s, claims one (sets `status=running`), logs it, marks `failed` with `error="not implemented"` — no real migration logic yet
- [x] done

### S16: worker Dockerfile
**File:** `src/worker/Dockerfile`  
**Depends on:** S15  
**Done when:** `docker build src/worker` succeeds; worker starts and logs "polling for jobs"
- [x] done

### S17: frontend scaffold — Vite + React + TS + Tailwind + shadcn/ui
**File:** `src/frontend/` (full Vite scaffold)  
**Depends on:** none  
**Done when:** `npm run dev` inside `src/frontend/` serves a placeholder page; Tailwind + shadcn/ui configured
- [x] done

### S18: frontend Dockerfile
**File:** `src/frontend/Dockerfile`  
**Depends on:** S17  
**Done when:** `docker build src/frontend` succeeds; container serves the Vite dev server
- [x] done

### S19: .env.example
**File:** `.env.example`  
**Depends on:** S03, S14  
**Done when:** all required env vars documented with placeholder values; no real secrets
- [x] done

### S20: smoke test — POST /migrate + GET /jobs/{id}
**File:** `tests/test_api_smoke.py`  
**Depends on:** S08, S09  
**Done when:** pytest with `TestClient` confirms job creation and retrieval; `make test` exits 0
- [x] done

### S21: CI — fix graceful skip when src/ exists + add Alembic step
**File:** `.github/workflows/ci.yml`  
**Depends on:** S05, S10  
**Done when:** CI runs ruff, mypy, pytest, and `alembic upgrade head` against a Postgres service container without errors
- [x] done

## Dependencies on other features

- None — this is the foundation everything else builds on

## Out of scope for this feature

- Any actual SAS parsing or LLM calls (F1)
- Reconciliation logic (F3)
- Audit endpoint (F8)
- Download endpoint (F9)
- DatabricksBackend implementation (Phase 4)
- Frontend migration UI beyond the placeholder page (Phase 3)
