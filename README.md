# rosetta-decode

Decode legacy SAS with LLMs. Extract hidden business logic, map dependencies, and translate to Python/PySpark pipelines. From vendor lock-in to modern, open data platforms.

---

## What this is

A migration tool that takes legacy SAS scripts and produces runnable Python ETL pipelines — locally via pandas/PostgreSQL, or on Databricks via PySpark. A hosted LLM handles the translation; a reconciliation engine proves the output matches the original SAS results.

Controlled by a single flag in `.env`:

```
CLOUD=false   # pandas + PostgreSQL (local)
CLOUD=true    # PySpark (Databricks)
```

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — runs the full four-service stack
- [uv](https://docs.astral.sh/uv/) — Python package manager for local tooling (tests, linting, pre-commit)
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- [Node.js 20+](https://nodejs.org/) — only needed if running the frontend outside Docker
- [Claude Code](https://claude.ai/code) — required to work with the session workflow described below

---

## Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd rosetta-decode

# 2. Install local dev tools (ruff, mypy, pytest, pre-commit)
uv sync --extra dev

# 3. Register pre-commit hooks — run automatically on every commit
uv run pre-commit install

# 4. Copy env file and fill in your API key
cp .env.example .env
```

Minimum `.env` to get started:

```
DATABASE_URL=postgresql+asyncpg://rosetta:rosetta@localhost:5432/rosetta
CLOUD=false
LLM_MODEL=anthropic:claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...
LOG_LEVEL=INFO
POLL_INTERVAL_SECONDS=5
```

---

## Running the stack

```bash
make dev        # build and start all four services (postgres, backend, worker, frontend)
make dev-down   # stop everything
make dev-logs   # tail logs from all containers
```

| Service  | URL                       |
|----------|---------------------------|
| Backend API | `http://localhost:8000` |
| API docs    | `http://localhost:8000/docs` |
| Frontend    | `http://localhost:5173` |

---

## Common commands

All test and quality commands go through `make`. Never call `uv run pytest` or `ruff` directly.

```bash
make test                  # full test suite with coverage
make test-fast             # skip reconciliation + cloud + integration tests (quick feedback)
make test-reconciliation   # reconciliation tests only (requires Postgres running)
make lint                  # ruff linter
make format                # ruff auto-formatter
make check                 # lint + mypy type check
make coverage              # test suite with HTML coverage report (opens htmlcov/index.html)
```

---

## Session workflow (Claude Code)

This project is built with [Claude Code](https://claude.ai/code). Every working session follows a strict workflow so context is never lost between contributors. The workflow is enforced through slash commands — type them in the Claude Code prompt.

### Starting a session

Always run this first — before any other command or question:

```
/session-start
```

Claude reads the journal (`journal/SESSIONS.md`, `journal/BACKLOG.md`, `journal/DECISIONS.md`), checks for any active feature plan in `docs/plans/`, then summarises:
- What was done last session
- Which feature is in progress and what subtask is next (or what's next on the backlog if no feature is active)
- Any open questions or blockers

Claude then **waits for you to confirm or redirect** before proposing any work. Never skip this step.

---

### Planning a feature

Before implementing anything non-trivial:

```
/plan-feature
```

Claude reads all relevant docs (`docs/features.md`, `docs/architecture.md`, `docs/mvp-scope.md`, `docs/coding-standards.md`, `journal/BACKLOG.md`, `journal/DECISIONS.md`), then:

1. Breaks the feature into ordered subtasks — each producing one independently testable artefact
2. Writes a plan file to `docs/plans/F<N>-<slug>.md`
3. Updates `journal/BACKLOG.md` with the subtask list
4. Enters **plan mode** — Claude shows the plan and waits for your approval

**No code is written until you approve the plan.** This prevents speculative work and keeps changes reviewable.

Once approved, Claude works through subtasks sequentially, marking each done in the plan file and backlog before moving to the next. A feature is only complete when `make test` exits 0 and all acceptance criteria are checked off.

---

### Committing code

**Never commit manually.** All commits go through:

```
/git-committer
```

Claude will:
1. Verify the journal and backlog are current
2. Identify the logical unit to commit (if multiple unrelated changes exist, it splits them)
3. Stage specific files by name (never `git add -A`)
4. Draft a conventional commit message (`feat:`, `fix:`, `docs:`, `chore:`, etc.)
5. Show you the staged file list and commit message
6. **Wait for your explicit approval** before running `git commit`

Pre-commit hooks (ruff + mypy) run automatically. If a hook fails, Claude fixes the underlying issue and retries — `--no-verify` is forbidden.

`/session-end` calls `git-committer` automatically for journal commits, but for mid-session code commits, run it explicitly.

---

### Ending a session

Always run this before stopping:

```
/session-end
```

Claude will:
1. Mark completed subtasks in the active feature plan (`docs/plans/`)
2. Check off done items in `journal/BACKLOG.md` and add any newly discovered tasks
3. Append any new architectural decisions to `journal/DECISIONS.md`
4. Append a new entry to the **top** of `journal/SESSIONS.md` summarising what was done, decisions made, open questions, and the concrete first step for next session
5. Show you the journal diffs and wait for approval
6. Call `git-committer` to commit the journal updates

**Always end with `/session-end`. Never close Claude Code without running it** — the journal is how the next session (or contributor) picks up exactly where you left off.

---

### Skill reference

| Skill | When to use |
|---|---|
| `/session-start` | First thing every session — reads journal, summarises context, waits for confirmation |
| `/session-end` | Before stopping — updates journal, backlog, decisions, commits |
| `/plan-feature` | Before implementing any new feature — writes plan file, enters plan mode, waits for approval |
| `/git-committer` | Any mid-session commit — enforces atomic commits, conventional format, no secrets |

---

## The journal

The `journal/` folder is the source of truth for everything that isn't in the code:

| File | Purpose |
|---|---|
| `journal/SESSIONS.md` | What happened each session, decisions made, what's next |
| `journal/BACKLOG.md` | Phased task list — single source of truth for what to build and in what order |
| `journal/DECISIONS.md` | Architectural decisions with rationale and revisit conditions |

Read the top entry of `SESSIONS.md` and the active phase of `BACKLOG.md` before starting any work, even without Claude.

Active feature plans live in `docs/plans/F<N>-<slug>.md`. If a plan exists with `Status: in-progress`, it takes priority over the general backlog.

---

## Architecture principles

**No `if CLOUD` checks in business logic.** All execution differences between local (pandas/PostgreSQL) and Databricks (PySpark) are hidden behind a `ComputeBackend` interface (`src/worker/compute/base.py`). Business logic never knows which backend is running.

**Every generated line is traceable.** All Python code produced by the migration engine carries a `# SAS: <file>:<line>` provenance comment. Any output can be traced back to its SAS source. Non-negotiable — required for audit sign-off.

**Reconciliation is not optional.** Every new SAS construct handler ships with a reconciliation test in the same PR. A feature is not done until `make test` passes.

**Plans before code.** Any multi-file change goes through plan mode first. Claude proposes, you approve, then implementation begins.

---

## Key docs

| Doc | What it covers |
|---|---|
| `docs/architecture.md` | Four-service design, API contracts, ComputeBackend interface, data model |
| `docs/features.md` | Full feature list (F1–F18) with phase and area |
| `docs/mvp-scope.md` | MVP definition and definition of done |
| `docs/coding-standards.md` | Required conventions for all Python code |
| `docs/context/sas-patterns.md` | SAS pattern catalog used by the LLM |
| `docs/context/migration-approaches.md` | Why LLM-assisted conversion was chosen |

---

## Never commit

- `.env` — use `.env.example` as the template; never commit real keys
- Code that bypasses pre-commit hooks — `--no-verify` is forbidden
- Untested code — `make test` must pass before any commit
