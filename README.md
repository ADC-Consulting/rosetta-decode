# Introduction

Legacy SAS codebases are a liability. They encode decades of business logic in a language no one wants to maintain, tied to a vendor most organisations are trying to leave. **rosetta-decode** uses LLMs to extract that logic and translate it into production-ready Python ETL pipelines — runnable locally on pandas/PostgreSQL, or on Databricks via PySpark, controlled by a single environment flag.

A reconciliation engine validates every migration automatically: same SAS input, same output data, provably. Every generated line carries a `# SAS: <file>:<line>` provenance comment so auditors can trace any transformation back to its source.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — runs the full four-service stack (API, worker, frontend, Postgres)
- [uv](https://docs.astral.sh/uv/) — Python package manager
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- [Claude Code](https://claude.ai/code) — required for the development workflow

---

## Setup

```bash
git clone <repo-url>
cd rosetta-decode

uv sync --extra dev
uv run pre-commit install

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
make dev        # build and start all four services
make dev-down   # stop everything
make dev-logs   # tail logs
```

| Service     | URL                            |
| ----------- | ------------------------------ |
| Backend API | `http://localhost:8000`      |
| API docs    | `http://localhost:8000/docs` |
| Frontend    | `http://localhost:5173`      |

---

## How to contribute

This project is built with [Claude Code](https://claude.ai/code). When you open the project, the **orchestrator agent** is loaded automatically — it owns session context, feature planning, and commit gating. All development flows through it.

### Starting a session

```
/session-start
```

The orchestrator reads the journal (`journal/SESSIONS.md`, `journal/BACKLOG.md`, `journal/DECISIONS.md`), checks for any active feature plan in `docs/plans/`, and tells you exactly what's next. **Always run this before doing anything else.** It waits for you to confirm before proposing work.

### Planning a feature

```
/plan-feature
```

Before any implementation, the orchestrator reads all relevant docs, breaks the feature into ordered subtasks, writes a plan to `docs/plans/F<N>-<slug>.md`, and enters plan mode. **No code is written until you approve the plan.**

### Committing

```
/git-committer
```

The orchestrator stages specific files by name, drafts a conventional commit message, and shows it to you before running `git commit`. Pre-commit hooks (ruff + mypy) run automatically. `--no-verify` is forbidden.

### Ending a session

```
/session-end
```

Updates the active feature plan, backlog, and decisions log. Appends a new entry to `journal/SESSIONS.md` with what was done, decisions made, and the concrete first step for next session. Then calls `/git-committer` to commit the journal. **Never close Claude Code without running this.**

### Commands reference

```bash
make test       # full test suite with coverage — always use this, never pytest directly
make lint       # ruff linter
make format     # ruff auto-formatter
make check      # lint + mypy
```

---

## Key docs

| Doc                          | What it covers                                                    |
| ---------------------------- | ----------------------------------------------------------------- |
| `docs/architecture.md`     | Four-service design, API contracts, data model                    |
| `docs/features.md`         | Full feature list (F1–F18) with phase and area                   |
| `docs/mvp-scope.md`        | MVP definition and definition of done                             |
| `docs/coding-standards.md` | Required conventions for all Python and TypeScript code           |
| `journal/BACKLOG.md`       | Phased task list — single source of truth for what to build next |
