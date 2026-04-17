```markdown
# SAS-to-Databricks Migration Tool

## Purpose

Build a tool that migrates legacy SAS code into Python/PySpark pipelines runnable
locally (pandas/DuckDB) or on Databricks (PySpark), controlled by the CLOUD flag
in .env. Tool must be transparent, tool-agnostic, and produce audit-ready output.

## Session Continuity — READ FIRST EVERY SESSION

At the start of every session:

1. Read `journal/SESSIONS.md` (top entry = last session)
2. Read `journal/BACKLOG.md` (what's next)
3. Read `journal/DECISIONS.md` (constraints already locked in)
4. Confirm context with the user before proposing work

At the end of every session:

1. Append a new entry to `journal/SESSIONS.md` (top of file)
2. Update `journal/BACKLOG.md` (mark done, add new items)
3. Log any new decisions in `journal/DECISIONS.md`
4. If a non-trivial architectural choice was made, create an ADR in `docs/adr/`

## Architecture (short form — see docs/architecture.md)

- Backend: Python 3.11+, FastAPI, Pydantic AI (agent framework, tools, structured outputs), migration engine, validation engine
- Frontend: React + Vite + TypeScript, Tailwind CSS, shadcn/ui components
- Execution: local (pandas/DuckDB) or Databricks (PySpark)
- Controlled by CLOUD flag in .env (false = local, true = Databricks)

## Key Docs

- User stories: `docs/user-stories.md`
- Features: `docs/features.md`
- Architecture: `docs/architecture.md`
- Coding standards: `docs/coding-standards.md` ← MUST follow for all code
- MVP scope: `docs/mvp-scope.md`
- SAS pattern catalog: `docs/context/sas-patterns.md`
- Migration approaches (context): `docs/context/migration-approaches.md`

## Coding Conventions

- Python 3.11+, type hints required on all public functions
- Formatter: ruff (format + lint)
- Tests: pytest; every new SAS construct handler MUST ship with a reconciliation test
- Commit style: conventional commits (feat:, fix:, docs:, chore:, refactor:, test:)
- Generated Python must include provenance comments: `# SAS: <file>:<line>`

## Critical Rules

- NEVER commit secrets or .env files (only .env.example)
- When CLOUD=true: PySpark only. When CLOUD=false: pandas/DuckDB.
- Abstract execution behind a `ComputeBackend` interface — no `if CLOUD` checks scattered in business logic
- Every migration output must be reproducible: same SAS input → same Python output
- Use plan mode before any multi-file change

## Workflow

### User-invoked skills (type `/skill-name` to run)

| Skill | When to use |
|---|---|
| `/session-start` | First thing every session — restores journal context before any work |
| `/session-end` | Before stopping — updates journal, reviews diffs, triggers commit |
| `/plan-feature` | Before implementing any new feature — breaks into subtasks, enters plan mode |

### Claude-invoked skills (triggered automatically by context)

| Skill | When Claude uses it |
|---|---|
| `feature-planner` | "Build feature X" / "implement F1" — reads feature, breaks into subtasks, plans before coding |
| `backend-builder` | FastAPI routes, service layer, `ComputeBackend` wiring, Pydantic AI agents |
| `frontend-builder` | React pages and components (Vite + TypeScript + shadcn/ui) |
| `git-committer` | Before any commit — conventional format, journal update check |

> The product (the tool being built) calls hosted LLMs. Skills are for Claude Code building the product.
> `docs/context/` files are the authoritative SAS reference for the LLM product layer.
```
