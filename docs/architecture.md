# Architecture

## Overview

Rosetta Decode is a microservices application. Each service is a separate Docker image with a single responsibility. Services communicate over a shared Docker network; the only shared state is PostgreSQL.

---

## Services

| Service | Image source | Port | Responsibility |
|---|---|---|---|
| `postgres` | `postgres:16` | 5432 | Job state, audit trail, metadata |
| `backend` | `src/backend/Dockerfile` | 8000 | FastAPI API — accepts uploads, enqueues jobs, serves results |
| `worker` | `src/worker/Dockerfile` | — | Async job runner — parse → translate → assemble → reconcile |
| `frontend` | `src/frontend/Dockerfile` | 5173 | React/Vite UI |

`backend` and `worker` are built from the same Python codebase (`pyproject.toml` at root) but run as separate images with different entrypoints. The worker has no inbound HTTP port — it polls Postgres for queued jobs.

---

## Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  frontend  (React + Vite + TypeScript + Tailwind + shadcn/ui)        │
│  ┌──────────────────┐  ┌────────────────────┐  ┌──────────────────┐  │
│  │  Upload & Trigger │  │  Job Status + Code  │  │  Diff / Lineage  │  │
│  │  (multi-file)    │  │  + Reconcil. Report │  │  (Phase 3+)      │  │
│  └────────┬─────────┘  └────────┬────────────┘  └──────────────────┘  │
└───────────┼─────────────────────┼──────────────────────────────────────┘
            │  REST               │  polling
            ▼                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  backend  (FastAPI)                                                   │
│  POST /migrate   → validate, persist files, insert job → { job_id } │
│  GET  /jobs/{id} → read job row → { status, python_code, report }   │
└────────────────────────────┬─────────────────────────────────────────┘
                             │  writes job row (status=queued)
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  postgres  (PostgreSQL 16)                                            │
│  jobs: id, status, input_hash, files (JSONB), python_code,           │
│        report (JSONB), error, created_at, updated_at                 │
└────────────────────────────┬─────────────────────────────────────────┘
                             │  polls for queued jobs
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  worker  (Python — same src, separate process + image)               │
│                                                                       │
│  ┌─────────────────┐   ┌─────────────────┐   ┌──────────────────┐   │
│  │  SASParser       │   │  LLMClient       │   │  CodeGenerator   │   │
│  │  (lark grammar)  │──▶│  (Pydantic AI)   │──▶│  + Provenance    │   │
│  │  multi-file aware│   │  model=LLM_MODEL │   │  # SAS:<f>:<ln>  │   │
│  └─────────────────┘   └─────────────────┘   └────────┬─────────┘   │
│                                                         │             │
│  ┌──────────────────────────────────────────────────────▼──────────┐ │
│  │  ReconciliationService  (runs inline, after codegen)             │ │
│  │  schema parity · row count · aggregate parity                    │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                         │             │
│  ┌──────────────────────────────────────────────────────▼──────────┐ │
│  │  ComputeBackend (abstract interface)                             │ │
│  │  LocalBackend       → pandas + PostgreSQL      (active)              │ │
│  │  DatabricksBackend  → PySpark              (future — Phase 4)    │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
                             │
            ┌────────────────┴────────────────┐
            │  Hosted LLM API                  │
            │  provider resolved from           │
            │  LLM_MODEL env var               │
            │  (anthropic:..., openai:..., …)  │
            └──────────────────────────────────┘
```

---

## Data Flow — Migration

```
User uploads N SAS files (scripts, macro modules, includes) + optional reference CSVs
  → POST /migrate  (multipart/form-data)
      → validate files
      → store file contents in job row (JSONB)
      → insert job row (status=queued, input_hash=SHA256 of all file contents)
      → return { job_id }

worker polls Postgres for queued jobs:
  → mark job status=running
  → SASParser.parse(files)                  → List[SASBlock], ordered by dependency
  → for each block:
      LLMClient.translate(block, patterns)  → GeneratedBlock (Pydantic AI structured output)
  → CodeGenerator.assemble(blocks)          → full Python file, every line group carries
                                               # SAS: <filename>:<line>
  → ReconciliationService.run(ref_csv, python_code, backend)
      → schema parity check
      → row count check
      → aggregate parity check
  → update job (status=done, python_code=..., report=JSONB)
  → on any error: update job (status=failed, error=message)

client polls GET /jobs/{id}
  → { status: "done", python_code: "...", report: { checks: [...] } }
```

Identical SAS input always produces identical Python output (input_hash enforces determinism).  
Untranslatable constructs are preserved as `# SAS-UNTRANSLATABLE: <reason>` — never silently dropped.

---

## API Contracts

| Endpoint | Method | Request | Response |
|---|---|---|---|
| `/migrate` | POST | `multipart/form-data`: `sas_files[]` (1+), `ref_csv` (optional) | `{ job_id: str }` |
| `/jobs/{id}` | GET | path param `id` | `{ status, python_code?, report?, error? }` |

`report` shape:
```json
{
  "checks": [
    { "name": "schema_parity",     "status": "pass" },
    { "name": "row_count",         "status": "pass" },
    { "name": "aggregate_parity",  "status": "fail", "detail": "..." }
  ]
}
```

---

## PostgreSQL Schema

```sql
CREATE TABLE jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status      TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed')),
    input_hash  TEXT NOT NULL,   -- SHA256 of all SAS file contents
    files       JSONB NOT NULL,  -- { "filename.sas": "<content>", ... }
    python_code TEXT,
    report      JSONB,           -- { checks: [{ name, status, detail? }] }
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Schema managed by Alembic. Async access via SQLAlchemy (asyncpg driver).

---

## ComputeBackend Interface

All execution is routed through a single abstract interface. No `if CLOUD` checks are allowed outside the factory that creates the backend.

```python
from abc import ABC, abstractmethod
import pandas as pd

class ComputeBackend(ABC):

    @abstractmethod
    def read_csv(self, path: str) -> object:
        """Return a DataFrame (pandas or Spark) from a CSV path."""

    @abstractmethod
    def run_sql(self, query: str, context: dict[str, object]) -> object:
        """Execute SQL against registered tables and return a DataFrame."""

    @abstractmethod
    def write_parquet(self, df: object, path: str) -> None:
        """Write a DataFrame to Parquet at the given path."""

    @abstractmethod
    def to_pandas(self, df: object) -> pd.DataFrame:
        """Convert backend DataFrame to pandas for reconciliation."""
```

`BackendFactory.create()` reads `CLOUD` from env and returns the correct implementation.  
`DatabricksBackend` is stubbed — it will be activated in Phase 4.

---

## LLM Abstraction

The LLM provider and model are selected entirely via environment variable:

```
LLM_MODEL=anthropic:claude-sonnet-4-6   # or openai:gpt-4o, etc.
```

Pydantic AI resolves the provider from the model string. No custom routing code exists.  
All LLM calls go through a single `LLMClient` class — a Pydantic AI agent that returns structured output via a `BaseModel` result type.

Required env vars (see `.env.example`):
- `LLM_MODEL` — selects provider and model
- `ANTHROPIC_API_KEY` — required when using Anthropic models
- `OPENAI_API_KEY` — required when using OpenAI models

---

## Directory Structure

```
src/
  backend/
    Dockerfile
    api/          # FastAPI app, routers, request/response schemas (Pydantic)
    db/           # SQLAlchemy models, Alembic migrations, async session factory
    core/         # Settings (pydantic-settings), logging config
  worker/
    Dockerfile
    engine/       # SASParser, LLMClient, CodeGenerator
    validation/   # ReconciliationService
    compute/      # ComputeBackend (ABC), LocalBackend, DatabricksBackend (stub)
    core/         # Shared settings, logging (imported from backend/core or duplicated)
  frontend/
    Dockerfile
    src/
      pages/      # Upload page, job polling/results page
      components/ # Shared shadcn/ui primitives
      api/        # Typed fetch wrappers (MigrateApi, JobsApi)
tests/
  reconciliation/ # pytest tests — one per SAS construct handler
samples/          # Sample SAS files + reference output CSVs
```

---

## Docker Compose

```yaml
services:
  postgres:
    image: postgres:16
    ports: ["5432:5432"]
    environment: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

  backend:
    build: src/backend
    ports: ["8000:8000"]
    depends_on: [postgres]
    env_file: .env

  worker:
    build: src/worker
    depends_on: [postgres]
    env_file: .env

  frontend:
    build: src/frontend
    ports: ["5173:5173"]
```

All services on bridge network `rosetta-net`. Run the full stack with `make dev`.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.12 |
| API framework | FastAPI |
| Job state | PostgreSQL 16 + SQLAlchemy (async) + Alembic + asyncpg |
| Local execution | pandas + PostgreSQL |
| Cloud execution | PySpark / Databricks — Phase 4, paused |
| LLM integration | Pydantic AI — agents, tool definitions, structured outputs |
| LLM provider | Provider-agnostic via `LLM_MODEL` env var |
| SAS parsing | lark (DATA step grammar), sqlparse (PROC SQL) |
| Codegen templating | Jinja2 |
| Lineage / graph | networkx |
| Frontend | React + Vite + TypeScript |
| UI components | Tailwind CSS + shadcn/ui |
| Formatter / linter | ruff |
| Type checker | mypy (strict) |
| Tests | pytest (markers: `reconciliation`, `cloud`, `integration`) |
| Dev runtime | Docker Compose — 4 services |
