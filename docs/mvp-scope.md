# MVP Scope

## Goal

Deliver a working end-to-end migration for a single, real SAS script — local execution only first, then Databricks — with full reconciliation proving the output matches.

---

## MVP Features (must ship)

| Feature | Scope limit for MVP |
|---|---|
| **F1 — Pipeline Generation** | DATA steps + PROC SQL only. No macro support in MVP. Single SAS file input. |
| **F3 — Validation & Reconciliation** | Schema parity + row count + aggregate parity. Hash diff is post-MVP. |

Everything else (F2, F4, F5, F6, F7) is post-MVP.

---

## CLOUD Flag Behaviour

Controlled by `CLOUD` in `.env` (never in code).

| `CLOUD` | Execution | Libraries |
|---|---|---|
| `false` | Local | pandas, DuckDB |
| `true` | Databricks | PySpark |

The `ComputeBackend` interface abstracts all execution differences. No `if CLOUD` checks are allowed outside of the backend initialization layer.

---

## Sample SAS Input Scope (MVP)

A single SAS script containing:
- At least one DATA step with a SET statement and variable transformations
- At least one PROC SQL block
- No macro definitions or calls
- No ODS, PROC REPORT, or platform I/O procedures

The same script is used for reconciliation: SAS output (exported as CSV) vs Python output.

---

## Post-MVP (next phases)

- Macro variable resolution and macro definitions (F1 extension)
- SAS log ingestion (F4)
- Row-level hash diff (F3 extension)
- Frontend: explanation UI (F2), side-by-side view (F7)
- Frontend: lineage (F5), dependency graph (F6)
- Databricks PySpark backend (CLOUD=true)
- Multi-file SAS input with dependency resolution

---

## Definition of Done (MVP)

- [ ] SAS script → Python pipeline generated (F1, CLOUD=false)
- [ ] Python pipeline runs locally without errors
- [ ] Reconciliation report generated showing schema + row count + aggregate parity pass (F3)
- [ ] All generated lines carry `# SAS: <file>:<line>` provenance comments
- [ ] Untranslatable constructs are flagged, not silently dropped
- [ ] At least one reconciliation pytest test passes
- [ ] ruff passes with no errors
- [ ] mypy passes with no errors
