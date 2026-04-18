# MVP Scope

## Goal

Deliver a working end-to-end migration for a single, real SAS script — local execution only
(CLOUD=false) — with full reconciliation proving the output matches, accessible via a browser UI.

---

## MVP Features (must ship)

| Feature | Scope limit for MVP |
|---|---|
| **F1 — Pipeline Generation** | DATA steps + PROC SQL only. No macro support in MVP. Multi-file SAS input (scripts, macro modules, includes). LLM is the primary translation engine — mandatory, not optional. |
| **F3 — Validation & Reconciliation** | Schema parity + row count + aggregate parity. Hash diff is post-MVP. |
| **F8 — Compliance & Audit Traceability** | Immutable audit record per job (input hashes, model, timestamp, reconciliation results). Exposed via API. No new data computed — jobs table already holds it. |
| **F9 — Downloadable Migration Output** | `GET /jobs/{id}/download` returns a zip: `pipeline.py` + `reconciliation_report.json` + `audit.json`. |
| **F-LLM — LLM system prompt + resilience** | System prompt establishes the agent as a SAS migration expert targeting Python/PySpark. Worker must not crash if LLM API is temporarily unreachable — job marked failed with clear error, process stays alive. |
| **F-sas7bdat — Binary dataset reading** | `LocalBackend` reads `.sas7bdat` files via `pyreadstat` (dep already declared). `.sas7bdat` files are loaded as DataFrames and made available to the pipeline execution context. |
| **F-UI — Upload & Results page** | Single-page React UI: upload `.sas` + optional `.sas7bdat` / `.csv` / `.log` files, poll job status, view generated Python + reconciliation report, download zip. Wires to existing `POST /migrate`, `GET /jobs/{id}`, `GET /jobs/{id}/download`. |

Everything else is post-MVP.

---

## CLOUD Flag Behaviour

Controlled by `CLOUD` in `.env` (never in code).

| `CLOUD` | Execution | Libraries |
|---|---|---|
| `false` | Local | pandas, PostgreSQL |
| `true` | Databricks | PySpark |

The `ComputeBackend` interface abstracts all execution differences. No `if CLOUD` checks are
allowed outside of the backend initialization layer.

---

## Sample SAS Input Scope (MVP)

One or more SAS files representing a real project (main script + macro modules + includes), containing:
- At least one DATA step with a SET statement and variable transformations
- At least one PROC SQL block
- No macro definitions or calls
- No ODS, PROC REPORT, or platform-specific I/O procedures

Reference CSV outputs (exported from SAS) are used for reconciliation: SAS output vs Python output.
`.sas7bdat` reference datasets are also accepted and loaded via `LocalBackend`.

---

## Post-MVP (next phases)

**Phase 2:** Macro variable resolution + macro definitions (F1 extension), PROC SORT (F1 — already done),
row-level hash diff (F3 extension), record-level reconciliation (F15), log-based reverse
engineering (F4), artefact versioning (F10), plain-language docs (F11), refine conversion action (F18)

**Phase 3:** Code explanation UI (F2), side-by-side view (F7), editable code in UI (F13),
lineage UI (F5), dependency graph (F6), ETL pipeline view (F17), migration dashboard (F16),
technical docs + lineage metadata (F12)

**Phase 4:** Databricks PySpark backend (CLOUD=true), authentication & SSO (F14)

---

## Definition of Done (MVP)

- [ ] SAS script → Python pipeline generated (F1, CLOUD=false)
- [ ] Python pipeline runs locally without errors
- [ ] Reconciliation report generated showing schema + row count + aggregate parity pass (F3)
- [ ] All generated lines carry `# SAS: <file>:<line>` provenance comments
- [ ] Untranslatable constructs are flagged, not silently dropped
- [ ] At least one reconciliation pytest test passes
- [ ] `.sas7bdat` files can be loaded as DataFrames via `LocalBackend`
- [ ] Worker stays alive and marks job failed (not crash) when LLM API is unreachable
- [ ] User can upload SAS files via the UI and see the generated pipeline + reconciliation report
- [ ] User can download the zip from the UI
- [ ] ruff passes with no errors
- [ ] mypy passes with no errors
