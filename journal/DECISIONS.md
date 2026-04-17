```markdown
# Decisions Log

Append-only. For larger decisions, also create a full ADR in `docs/adr/`.
Format: date · decision · rationale · revisit?

---

## 2026-04-17

- **Language & runtime:** Python 3.11+ · modern typing, match statements, broad lib support · revisit if Databricks default changes
- **Execution backends:** pandas/PostgreSQL (local) and PySpark (Databricks), toggled by `CLOUD` env var · keeps MVP runnable on a laptop · DuckDB was removed in favour of PostgreSQL (same engine as job state store, one less service) · revisit if PostgreSQL local performance becomes a bottleneck
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

## 2026-04-17 (session 3 — architecture revision)

- **Microservices:** each service is a separate Docker image (backend, worker, frontend, postgres) · separation of concerns; worker decouples heavy processing from API latency · revisit never (core architecture)
- **Worker service:** async job runner as a dedicated container polling Postgres · allows independent scaling and restart of the processing layer without touching the API · revisit if queue volume demands a real message broker (RabbitMQ, SQS)
- **Job state in PostgreSQL:** jobs table stores status, input hash, files JSONB, output, and audit fields · already in the Docker stack; cloud-ready (managed Postgres later); avoids an extra service · revisit never for MVP, may add Redis for pub/sub in Phase 2
- **Async job flow:** POST /migrate → job_id → poll GET /jobs/{id} · keeps API response fast; client controls polling interval · revisit if real-time progress is needed (WebSocket, Phase 2)
- **Reconciliation inline in worker:** F3 runs automatically after codegen, not a separate endpoint · removes manual step; every migration always has a reconciliation result · revisit never
- **Provider-agnostic LLM via LLM_MODEL env var:** Pydantic AI resolves provider from model string (e.g. anthropic:claude-sonnet-4-6) · no custom routing code; swap provider by changing one env var · revisit never
- **Multi-file upload in MVP:** SAS projects are inherently multi-file; single-file MVP was not realistic · parser must order blocks by dependency across files · revisit scope if dependency resolution proves too complex for Phase 1
- **F8 and F9 bumped to MVP:** compliance audit traceability and downloadable output are mandatory for regulated (pharma/finance) first customers · data already in jobs table; no new architecture required · revisit never
- **Databricks paused:** DatabricksBackend stub remains in architecture but out of scope until Phase 4 · no Databricks workspace available for testing · revisit when workspace is confirmed

---

## 2026-04-17 (session 4 — DuckDB removal, skill hardening)

- **DuckDB removed from local backend:** LocalBackend now uses pandas + PostgreSQL instead of pandas + DuckDB · PostgreSQL is already a required service in Docker Compose; removing DuckDB eliminates one dependency and one moving part · revisit never (PostgreSQL is the standard)
- **Skills must not hard-code file paths:** skills and commands must derive service paths from `docs/architecture.md` — Directory Structure section — not embed them directly · prevents stale path refs when architecture evolves · applies to all future skill edits

---

## 2026-04-17 (session 5 — Databricks output target decision)

- **DatabricksBackend generates PySpark only:** three targets were evaluated — Databricks SQL, PySpark, and Delta Live Tables (DLT). PySpark confirmed as the sole output target for `DatabricksBackend`. Rationale: (1) PySpark is symmetric with `LocalBackend` — same Python, same `ComputeBackend` abstraction; (2) DATA steps map cleanly to DataFrame transformations or UDFs; (3) PROC SQL maps to `spark.sql(...)` strings naturally inside PySpark — no separate SQL output mode needed; (4) this is what enterprise clients mean by "Databricks migration" · revisit if a client explicitly requires SQL Warehouse or DLT output
- **Databricks SQL deferred:** SQL cannot handle DATA step logic (RETAIN, array, LAG, conditional multi-dataset output) — it would only cover PROC SQL-heavy codebases; a mixed SQL-in-PySpark approach (`spark.sql()` for PROC SQL blocks) achieves the readability benefit without a separate output mode · revisit in Phase 4+ if a client requires SQL Warehouse target
- **DLT (Delta Live Tables) deferred:** architecturally attractive (native lineage, declarative step model matches SAS) but cannot run locally — breaks the local/cloud symmetry that is a hard design constraint; LLM training data for DLT is thin · revisit Phase 4+ if local parity constraint is relaxed
- **Codegen constraint — no pandas-only idioms:** `CodeGenerator` must not emit pandas-specific calls; use parameterized DataFrame operations so `LocalBackend` and `DatabricksBackend` swap APIs without changing structure · enforced in Phase 1 codegen design

---
```
