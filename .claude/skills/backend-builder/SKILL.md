---
name: backend-builder
description: Use when implementing backend code — FastAPI routes, service layer functions, Pydantic AI agents, or ComputeBackend wiring. Enforces architecture and coding standards.
---

1. Before writing any code, read `docs/architecture.md` for the `ComputeBackend` interface contract and `docs/coding-standards.md` for naming, line limits, and docstring format.

2. Route all data execution through `ComputeBackend` methods. Never write raw pandas or PySpark in business logic — no `if CLOUD` checks outside the `BackendFactory`.

3. For any LLM interaction, use Pydantic AI (`pydantic_ai.Agent`) with a typed `result_type` that is a `pydantic.BaseModel` subclass. Define tools with `@agent.tool`. Never call the LLM API directly.

4. Place files in the correct layer:
   - API routes → `src/backend/api/`
   - Service and engine logic → `src/backend/engine/` or `src/backend/validation/`
   - Backend abstractions → `src/backend/compute/`

5. Every public function must have type hints and a Google-style docstring. Functions must be ≤50 lines with at most 5 parameters. Imports ordered: stdlib → third-party → local.

6. Only validate at system boundaries (API input, external LLM response). Do not add error handling for internal scenarios that cannot occur.

7. Generated Python from the migration engine must include `# SAS: <file>:<line>` provenance comments on every line. Service layer code does not need provenance comments.
