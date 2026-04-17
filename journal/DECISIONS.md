```markdown
# Decisions Log

Append-only. For larger decisions, also create a full ADR in `docs/adr/`.
Format: date · decision · rationale · revisit?

---

## 2026-04-17

- **Language & runtime:** Python 3.11+ · modern typing, match statements, broad lib support · revisit if Databricks default changes
- **Execution backends:** pandas/DuckDB (local) and PySpark (Databricks), toggled by `CLOUD` env var · keeps MVP runnable on a laptop · revisit if DuckDB parity with Spark becomes a bottleneck
- **Frontend for MVP:** React + Vite + TypeScript, Tailwind CSS, shadcn/ui · modern component library, accessible primitives, fast DX · revisit never (core stack)
- **LLM tooling:** Claude Code with skills + slash commands + journal-based memory · maximizes context continuity between sessions · revisit never (this is the setup)
- **Provenance:** every generated Python line group carries `# SAS: <file>:<line>` comments · required for audit/compliance user story · non-negotiable
- **Validation strategy:** schema parity + row hash diff + aggregate parity + distribution checks · covers financial reporting confidence · may add more checks per customer

---

## 2026-04-17 (session 2 — foundation setup)

- **Migration approach:** LLM-assisted conversion (approach 3 of 4) — structured prompting with pattern catalog, provenance, and reconciliation as safety net · rationale in `docs/context/migration-approaches.md` · revisit if LLM accuracy proves insufficient at scale
- **Skills vs subagents:** skills only (no specialized subagents) · simpler, compose naturally, avoid duplicated context overhead · revisit if a task requires deep specialization that skills can't capture
- **Backlog as build tracker:** `journal/BACKLOG.md` is the single source of truth for what to build and in what order · read by `/session-start`, updated by `/session-end`
- **Feature-first planning:** when asked to build a feature, Claude invokes `feature-planner` — break into subtasks, update backlog, plan mode, wait for approval before writing code
- **MVP cut:** F1 (DATA step + PROC SQL) + F3 (schema + row count + aggregate parity), local only (CLOUD=false) · all other features are post-MVP
- **Agent framework:** Pydantic AI (`pydantic-ai`) for all LLM interactions — agents, tool definitions, structured outputs · gives type-safe LLM responses via `BaseModel` result types, keeps LLM calls testable and model-agnostic · revisit never (locked in)
- **Pre-commit hooks:** enforced via `pre-commit` library; hooks run ruff format, ruff lint, mypy on every commit · Claude must never use `--no-verify`; hooks are the quality gate, not optional

---
```
