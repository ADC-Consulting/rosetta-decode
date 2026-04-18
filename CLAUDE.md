```markdown
# SAS-to-Databricks Migration Tool

## Purpose

Build a tool that migrates legacy SAS code into Python/PySpark pipelines runnable
locally (pandas/PostgreSQL) or on Databricks (PySpark), controlled by the CLOUD flag
in .env. Tool must be transparent, tool-agnostic, and produce audit-ready output.

## Session Continuity — READ FIRST EVERY SESSION

At the start of every session:

1. Read `journal/SESSIONS.md` (top entry = last session)
2. Read `journal/BACKLOG.md` (what's next)
3. Read `journal/DECISIONS.md` (constraints already locked in)
4. Check `docs/plans/` for any plan file with `Status: in-progress` — if found, read it
5. Confirm context with the user before proposing work

At the end of every session:

1. Update any active `docs/plans/F<N>-*.md` (mark subtasks done, update status)
2. Append a new entry to `journal/SESSIONS.md` (top of file)
3. Update `journal/BACKLOG.md` (mark done, add new items)
4. Log any new decisions in `journal/DECISIONS.md`
5. If a non-trivial architectural choice was made, create an ADR in `docs/adr/`

## Architecture (short form — see docs/architecture.md)

Four microservices, each a separate Docker image:
- `backend` — FastAPI API: accepts uploads, enqueues jobs, serves results (`src/backend/`)
- `worker` — async job runner: SAS parse → LLM → codegen → reconcile (`src/worker/`)
- `frontend` — React + Vite + TypeScript + Tailwind + shadcn/ui (`src/frontend/`)
- `postgres` — job state, audit trail (PostgreSQL 16)

LLM provider selected via `LLM_MODEL` env var (e.g. `anthropic:claude-sonnet-4-6`).  
Execution backend abstracted behind `ComputeBackend` interface in `src/worker/compute/`.

## Key Docs

- User stories: `docs/user-stories.md`
- Features: `docs/features.md`
- Feature plans (active): `docs/plans/` ← check here for in-progress work
- Architecture: `docs/architecture.md`
- Coding standards: `docs/coding-standards.md` ← MUST follow for all code
- MVP scope: `docs/mvp-scope.md`
- SAS pattern catalog: `docs/context/sas-patterns.md`
- Migration approaches (context): `docs/context/migration-approaches.md`

## Coding Conventions

- Python 3.12, type hints required on all public functions
- Formatter: ruff (format + lint)
- Tests: always run via `make test` (never `uv run pytest` directly); every new SAS construct handler MUST ship with a reconciliation test
- Commit style: conventional commits (feat:, fix:, docs:, chore:, refactor:, test:)
- Generated Python must include provenance comments: `# SAS: <file>:<line>`

## Critical Rules

- NEVER commit secrets or .env files (only .env.example)
- When CLOUD=true: PySpark only. When CLOUD=false: pandas/PostgreSQL.
- Abstract execution behind a `ComputeBackend` interface — no `if CLOUD` checks scattered in business logic
- Every migration output must be reproducible: same SAS input → same Python output
- Use plan mode before any multi-file change
- NEVER run `uv run pytest` or `pytest` directly — always use `make test`. No exceptions.
- When modifying any Dockerfile or docker-compose.yml, run `make docker-build` after `make test` before committing.

## Workflow

### User-invoked skills (type `/skill-name` to run)

| Skill | When to use |
|---|---|
| `/session-start` | First thing every session — restores journal + active feature plan before any work |
| `/session-end` | Before stopping — updates feature plan, journal, reviews diffs, triggers commit |
| `/plan-feature` | Before implementing any new feature — reads docs, breaks into ordered subtasks with dependencies, writes `docs/plans/F<N>-<slug>.md`, enters plan mode |
| `/test-runner` | Run full test suite via `make test`, interpret results and coverage |
| `/git-pr-summary` | Generate copy-paste ready PR description in standard Markdown format |

### Claude-invoked skills (triggered automatically by context)

| Skill | When Claude uses it |
|---|---|
| `feature-planner` | "Build feature X" / "implement F1" — reads feature, breaks into subtasks, writes plan file, plans before coding |
| `backend-builder` | Worker engine/validation/compute code, FastAPI routes, Pydantic AI agents |
| `frontend-builder` | React pages and components (Vite + TypeScript + shadcn/ui) |
| `git-committer` | Before any commit — conventional format, journal + plan file update check |
| `git-branch-setup` | After plan approval, before any implementation is delegated — ensures the correct `feat/F<N>-<slug>` branch exists and is checked out |
| `git-pr-summary` | When user asks for PR text, "give me the PR summary", or is about to open a PR — orchestrator only |
| `test-runner` | Anytime the user says "run tests", "check tests", "are tests passing", or asks about coverage |

### Agents (`.claude/agents/`)

| Agent | Role | Owns |
|---|---|---|
| `orchestrator` | Default entry point — runs session-start on every invocation, delegates to specialists, gates commits | session-start, session-end, plan-feature, git-committer |
| `backend-builder` | Python implementation — worker engine, FastAPI routes, Pydantic AI, migrations | backend-builder skill |
| `frontend-builder` | React/TS implementation — components, pages, API clients | frontend-builder skill |
| `fullstack-planner` | Read-only cross-cutting analysis — API contracts, type alignment, sequencing | read-only |
| `tester` | Runs `make test`, reports pass/fail/coverage to orchestrator | test-runner skill |

> The product (the tool being built) calls hosted LLMs. Skills and agents are for Claude Code building the product.
> `docs/context/` files are the authoritative SAS reference for the LLM product layer.
```
