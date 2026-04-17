# rosetta-decode

Decode legacy SAS with LLMs. Extract hidden business logic, map dependencies, and translate to Python/PySpark pipelines. From vendor lock-in to modern, open data platforms.

---

## What this is

A migration tool that takes legacy SAS scripts and produces runnable Python ETL pipelines — locally via pandas/DuckDB, or on Databricks via PySpark. A hosted LLM handles the translation; a reconciliation engine proves the output matches the original SAS results.

Controlled by a single flag in `.env`:

```
CLOUD=false   # pandas + DuckDB (local)
CLOUD=true    # PySpark (Databricks)
```

---

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) — install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Node.js 20+ (frontend, Phase 3 onwards)

---

## Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd rosetta-decode

# 2. Install dependencies (creates .venv automatically)
uv sync --extra dev

# 3. Register pre-commit hooks (runs ruff + mypy on every commit)
uv run pre-commit install

# 4. Copy env file and fill in your API key
cp .env.example .env
```

Your `.env` should look like:

```
CLOUD=false
ANTHROPIC_API_KEY=sk-ant-...
LOG_LEVEL=INFO
```

---

## Common commands

```bash
make test                  # full test suite
make test-fast             # skip slow reconciliation + cloud tests
make test-reconciliation   # reconciliation tests only
make lint                  # ruff linter
make format                # ruff formatter
make check                 # lint + mypy type check
make coverage              # test suite with HTML coverage report
```

---

## How we code here

This project is built with [Claude Code](https://claude.ai/code), an AI coding assistant with a structured session workflow. Every session is tracked in a journal so context is never lost between contributors.

### Getting started

Install Claude Code, then open this repo and run:

```
/session-start
```

Claude will read the journal, summarise what was done last session, what's next, and wait for you to confirm before doing anything. From there:

```
/plan-feature     # before building any new feature — breaks it into subtasks, enters plan mode
/session-end      # before stopping — updates the journal and commits
```

**Always start with `/session-start`. Always end with `/session-end`.** This is how we keep the project coherent across contributors and sessions.

### The journal

The `journal/` folder is the source of truth for everything that isn't in the code:

- `journal/SESSIONS.md` — what happened each session, decisions made, what's next
- `journal/BACKLOG.md` — phased task list, single source of truth for what to build
- `journal/DECISIONS.md` — architectural decisions and their rationale

Read the top entry of `SESSIONS.md` and `BACKLOG.md` before starting any work, even without Claude.

### The philosophy

**No `if CLOUD` checks in business logic.** All execution differences between local (pandas/DuckDB) and Databricks (PySpark) are hidden behind a `ComputeBackend` interface. Business logic never knows which backend is running. This keeps the codebase clean, testable, and honest about its abstractions.

**Every generated line is traceable.** All Python code produced by the migration engine carries a `# SAS: <file>:<line>` provenance comment. You can always trace any output back to its SAS source. This is non-negotiable — it's what makes the tool audit-ready.

**Reconciliation is not optional.** Every new SAS construct handler ships with a reconciliation test that proves the Python output matches the SAS output. A feature is not done until `make test` passes.

**Plans before code.** Any multi-file change goes through plan mode first. Claude proposes, you approve, then implementation begins. This prevents speculative work and keeps changes reviewable.

### Key docs

- `docs/architecture.md` — system design and the ComputeBackend interface contract
- `docs/features.md` — full feature list (F1–F7)
- `docs/mvp-scope.md` — what's in scope for MVP and the definition of done
- `docs/coding-standards.md` — required conventions for all Python code

---

## Never commit

- `.env` — use `.env.example` as the template
- Code that bypasses pre-commit hooks — `--no-verify` is forbidden
