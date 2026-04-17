---
name: backend-builder
description: Use when implementing or modifying Python backend code — FastAPI routes, service/engine functions, Pydantic AI agents, ComputeBackend implementations, or validation logic.
---

## Do NOT use for

- Frontend work (use `frontend-builder`)
- Running tests, committing, or dependency changes (use dedicated skills)

## Preflight (run IN ORDER)

1. Read `docs/architecture.md` — especially the `ComputeBackend` interface contract
2. Read `docs/coding-standards.md` — Python section
3. Read `CLAUDE.md` — Critical Rules section
4. Inspect `src/backend/compute/` to see existing `ComputeBackend` implementations (if it exists)
5. Inspect `src/backend/config.py` for the `Settings` object (if it exists)
6. Check `pyproject.toml` to confirm `pydantic-ai` and other needed deps are installed

## Layer placement (strict)

- `src/backend/api/` → FastAPI routers, request/response models
- `src/backend/engine/` → SAS migration engine (translator orchestration, codegen)
- `src/backend/validation/` → reconciliation, parity checks, report generators
- `src/backend/compute/` → `ComputeBackend` protocol + pandas/PySpark implementations
- `src/backend/agents/` → Pydantic AI agents and their tool definitions
- `src/backend/config.py` → `Settings` (pydantic-settings) — the ONLY place `os.environ` is read

## Architectural rules

- All data execution goes through `ComputeBackend`. No raw pandas/PySpark in `engine/`, `validation/`, or `api/`.
- No `if CLOUD:` outside `src/backend/compute/factory.py`.
- All config comes from `Settings` via dependency injection — no `os.getenv()` scattered.
- All I/O-bound code is `async def`. For sync libs (pyreadstat, etc.), wrap with `asyncio.to_thread` — FastAPI routes must also be `async def` to benefit from this.

## Pydantic AI rules

- Agents live in `src/backend/agents/<agent_name>.py` with a matching `<AgentName>Result` Pydantic model
- Always use `Agent(model=..., result_type=<BaseModel>, deps_type=<Deps>)`
- Register tools with `@agent.tool` — tool functions must be typed and have a Google docstring
- Model selection comes from `Settings.llm_model`; never hard-code `"claude-3-5-sonnet-..."`
- Prefer `await agent.run(...)`; use `agent.run_stream(...)` only when the endpoint streams
- Never call `anthropic.Anthropic()` or any provider SDK directly

## Coding standards (enforced)

- Type hints on all public functions; mypy strict mode must pass
- Google-style docstrings on public modules/classes/functions
- Functions ≤ 50 lines, ≤ 5 parameters
- Imports grouped: stdlib → third-party → local (ruff `I` enforces)
- Line length 100 chars
- Use specific exception types; never bare `except:`
- Log with stdlib `logging` with context — never `print`

## Validation & error handling

- Validate at system boundaries only: API request bodies (Pydantic), LLM responses (Pydantic AI `result_type`), external file inputs (validate using Pydantic at the boundary)
- Do NOT add defensive try/except around code that cannot fail
- DO raise specific, named exceptions for expected failure modes (`SASParseError`, `BackendUnavailableError`, etc.) defined in `src/backend/errors.py`

## Testing (mandatory)

- Every new public function ships with a colocated unit test in `tests/backend/<same_path>/test_*.py`
- Every new `ComputeBackend` method ships with tests for both pandas and PySpark impls
- Every new Pydantic AI agent ships with at least one test using `agent.override(model=TestModel(...))`
- Reconciliation-relevant changes ship with a `@pytest.mark.reconciliation` test

## Output contract

When done, report:

1. Files created/modified (grouped by layer)
2. New exceptions or interfaces introduced
3. Test files added and what they cover
4. Any TODOs left behind (with justification)
5. Suggested commit message in Conventional Commits format

## Guardrails

- Never bypass `ComputeBackend`
- Never call an LLM provider SDK directly
- Never read `os.environ` outside `config.py`
- Never add a new dependency without updating `pyproject.toml` and running `uv sync`
