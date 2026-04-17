---
name: backend-builder
description: Use when implementing or modifying Python backend code — FastAPI routes, service/engine functions, Pydantic AI agents, ComputeBackend implementations, or validation logic.
---

## Do NOT use for

- Frontend work (use `frontend-builder`)
- Running tests, committing, or dependency changes (use dedicated skills)

## Preflight (run IN ORDER)

1. Read `docs/architecture.md` — Directory Structure section gives the authoritative service layout and file locations; ComputeBackend Interface section defines the contract
2. Read `docs/coding-standards.md` — Python section
3. Read `CLAUDE.md` — Critical Rules section
4. Read the active feature plan in `docs/plans/` if one exists
5. Check `pyproject.toml` to confirm needed deps are present

## Layer placement

**Do not hard-code paths here.** Derive the correct service (`backend`, `worker`) and subdirectory (`api/`, `engine/`, `compute/`, `validation/`, `db/`, `core/`) from the **Directory Structure** section of `docs/architecture.md` before writing any file. The structure is the authority — this skill is not.

## Architectural rules

- All data execution goes through `ComputeBackend`. No raw pandas or SQL in engine, validation, or API layers.
- No `if CLOUD:` checks outside the `BackendFactory`.
- All config comes from `Settings` (pydantic-settings) via dependency injection — no `os.getenv()` scattered in business logic.
- All I/O-bound code is `async def`. For sync libs (pyreadstat, lark, etc.), wrap with `asyncio.to_thread`.
- Errors module lives in the service root (e.g. `src/worker/errors.py`) — check `docs/architecture.md` for the exact path.

## Pydantic AI rules

- Agents live in a dedicated `agents/` subdirectory of the relevant service — check `docs/architecture.md`
- Always use `Agent(model=..., result_type=<BaseModel>, deps_type=<Deps>)`
- Register tools with `@agent.tool` — tool functions must be typed with a Google docstring
- Model selection comes from `Settings.llm_model`; never hard-code a model string
- Prefer `await agent.run(...)`; use `agent.run_stream(...)` only when the endpoint streams
- Never call any provider SDK (anthropic, openai) directly

## Coding standards (enforced)

- Type hints on all public functions; mypy strict mode must pass
- Google-style docstrings on public modules, classes, and functions
- Functions ≤ 50 lines, ≤ 5 parameters
- Imports grouped: stdlib → third-party → local (ruff `I` enforces)
- Line length 100 chars
- Use specific exception types; never bare `except:`
- Log with stdlib `logging` — never `print`

## Validation & error handling

- Validate at system boundaries only: API request bodies (Pydantic), LLM responses (Pydantic AI `result_type`), external file inputs
- Do NOT add defensive try/except around code that cannot fail
- DO raise specific named exceptions for expected failure modes (e.g. `SASParseError`, `BackendUnavailableError`)

## Testing (mandatory)

- Every new public function ships with a unit test mirroring its location under `tests/`
- Every new `ComputeBackend` method ships with tests for both LocalBackend and (stubbed) DatabricksBackend
- Every new Pydantic AI agent ships with at least one test using `agent.override(model=TestModel(...))`
- Reconciliation-relevant changes ship with a `@pytest.mark.reconciliation` test

## Output contract

When done, report:

1. Files created/modified (grouped by service and layer)
2. New exceptions or interfaces introduced
3. Test files added and what they cover
4. Any TODOs left behind (with justification)
5. Suggested commit message in Conventional Commits format

## Guardrails

- Never bypass `ComputeBackend`
- Never call an LLM provider SDK directly
- Never read `os.environ` outside the `Settings` / `core/` module
- Never add a new dependency without updating `pyproject.toml` and running `uv sync`
