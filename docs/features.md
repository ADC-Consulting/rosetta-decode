# Features

Features are grouped by MVP status. New features introduced after the initial set are marked with their phase.

---

## MVP Features

### F1 — Automated SAS-to-Python Pipeline Generation
**Area:** Backend / Migration Engine  
**Serves:** US1  
**Phase:** 1

Ingests one or more SAS scripts (main scripts, macro modules, includes), calls a hosted LLM with the SAS source as context, and produces a complete runnable ETL pipeline in Python. Execution mode is controlled by the `CLOUD` flag in `.env`: `false` → pandas/DuckDB (local), `true` → PySpark (Databricks).

The engine handles: DATA steps, PROC SQL, PROC SORT, macro definitions and calls, macro variable resolution. SAS constructs that cannot be reliably translated (e.g. PROC MIXED, ODS, platform-specific I/O) are preserved as comments marked `# SAS-UNTRANSLATABLE: <reason>` so engineers know exactly what needs manual attention.

Every generated line carries a provenance comment `# SAS: <file>:<line>`. Output is deterministic: identical SAS input always produces identical Python output, enabling version control and audit trails.

---

### F3 — Validation & Reconciliation
**Area:** Backend / Data Validation & Quality  
**Serves:** US1, US2  
**Phase:** 1

After migration, runs automated checks to prove that the Python pipeline produces results that match the original SAS outputs. Checks include:

- **Schema parity** — column names and data types match
- **Row count** — same number of rows
- **Row-level hash diff** — detects row-level discrepancies on key columns
- **Aggregate parity** — SUM, COUNT, AVG on financial/metric columns match within tolerance
- **Distribution checks** — percentile distributions are consistent

Produces a structured reconciliation report (pass/fail per check, diff summary, sample of mismatches) suitable for financial audit sign-off and compliance review.

---

### F8 — Compliance & Audit Traceability
**Area:** Backend / Audit & Compliance  
**Serves:** US1, US2  
**Phase:** 1  
**MVP rationale:** Without a queryable audit record, the tool cannot be trusted in regulated environments (pharma, finance). Provenance comments in the generated code are necessary but not sufficient — compliance teams need a durable, structured record of every migration event.

Every completed migration job exposes a full audit record containing: input file hashes, LLM model used, timestamp, all reconciliation check results, and the exact generated Python output. This record is stored in the jobs table (already in the data model) and exposed via the API. Nothing new is computed — the data is already there; this feature defines the contract for accessing and interpreting it.

The audit record is immutable once written. Re-running a migration creates a new job, not an update to an existing one.

---

### F9 — Downloadable Migration Output
**Area:** Backend / API  
**Serves:** US1, US2  
**Phase:** 1  
**MVP rationale:** The tool produces generated Python code and a reconciliation report. If users cannot export these artefacts — to hand to QA, auditors, or regulators — the tool is a dead end. This is a single endpoint returning a zip: no new architecture.

`GET /jobs/{id}/download` returns a zip archive containing:
- `pipeline.py` — the generated Python file with provenance comments
- `reconciliation_report.json` — the structured check results
- `audit.json` — the full audit record (input hashes, model used, timestamps)

The zip filename includes the job ID and timestamp for traceability.

---

## Post-MVP Features

### F2 — Code Explanation Assistant UI
**Area:** Frontend / Input & Editing  
**Serves:** US2  
**Phase:** 3

A chat-style interface where a developer or analyst pastes a SAS snippet or selects a generated Python block and asks the system to explain it. The product calls a hosted LLM and returns a step-by-step plain-English breakdown: what the code does, why each transformation exists (inferred from variable names, SAS log context, and domain patterns), and what the Python equivalent achieves.

Designed for onboarding engineers unfamiliar with legacy SAS idioms and for non-technical stakeholders who need to validate logic without reading code.

---

### F4 — Log-Based Reverse Engineering
**Area:** Backend / Migration Engine  
**Serves:** US1  
**Phase:** 2

Ingests SAS execution logs (`.log` files), sends them to a hosted LLM, and reconstructs logic that is not obvious from the SAS source alone — including macro expansions as they were resolved at runtime, conditional branches that were taken, and dataset filters applied dynamically.

Converts this reconstructed runtime logic into Python alongside (or instead of) the static source parse. Particularly useful when SAS source is incomplete, obfuscated, heavily macro-driven, or was written by engineers no longer at the company.

---

### F5 — Lineage Visibility UI for QA
**Area:** Frontend / QA & Audit Views  
**Serves:** US2  
**Phase:** 3

A read-only view showing the full data lineage of a migrated pipeline: which SAS datasets and files feed which processing steps, which steps produce which outputs, and how each maps to the generated Python code. QA teams and compliance officers can trace any specific column, aggregate, or output back to its SAS source without needing to read code.

Designed for audit and compliance workflows, not active development.

---

### F6 — Dependency Graph Visualization
**Area:** Frontend / Understanding & Comparison  
**Serves:** US1  
**Phase:** 3

An interactive graph where nodes represent SAS jobs, datasets, macros, and include files, and edges represent dependencies between them. Supports filtering by type, zooming, and clicking a node to inspect the associated source code or migration status.

Helps engineers understand the full dependency tree before starting migration: identify the correct migration order, find orphaned datasets, detect circular dependencies, and scope the effort.

---

### F7 — Side-by-Side SAS vs Python/PySpark View
**Area:** Frontend / Understanding & Comparison  
**Serves:** US1, US2  
**Phase:** 3

A diff-style interface showing original SAS code on the left and generated Python/PySpark on the right, synchronized by logical block (DATA step ↔ DataFrame transform, PROC SQL ↔ SQL query, macro call ↔ function call).

Developers can review each block, accept it, edit it inline, or flag it for manual review. Also supports running both versions against a sample dataset and comparing output tables directly in the UI — making it possible to spot discrepancies without switching tools.

---

### F10 — Artefact Versioning
**Area:** Backend / Migration Engine  
**Serves:** US1  
**Phase:** 2

Store multiple versions of generated code and reconciliation reports per migration job. When the same SAS input is re-run (e.g. after a pattern catalog update or model change), the new output is saved as a new version alongside the original. Engineers can compare versions and roll back.

The input_hash on the jobs table already distinguishes identical inputs from changed ones; versioning is a grouping and retrieval layer on top.

---

### F11 — Plain-Language & Business-Readable Documentation
**Area:** Backend + Frontend / Documentation  
**Serves:** US2  
**Phase:** 2

Automatically generate a plain-English summary of what each migrated pipeline does: what data it reads, what transformations it applies, what it outputs, and why (inferred from variable names, SAS log context, and domain patterns). Distinct from F2 (which is interactive and chat-driven) — this is a static, exportable document generated once per migration.

Designed for non-technical stakeholders, business analysts, and compliance reviewers who need to validate logic without reading code.

---

### F12 — Auto-Generated Technical Documentation & Lineage Metadata
**Area:** Backend / Documentation  
**Serves:** US1  
**Phase:** 3

Generate structured technical documentation for each migrated pipeline: step-by-step pipeline description, transformation rules applied, input/output schemas, and data lineage metadata (which columns come from which source, through which transformations). Output as Markdown or JSON, suitable for consumption by downstream documentation tools.

Complements F5 (Lineage UI) — this is the data layer F5 visualises.

---

### F13 — Editable Generated Code in UI
**Area:** Frontend / Input & Editing  
**Serves:** US1  
**Phase:** 3

An in-browser code editor (Monaco or CodeMirror) embedded in the job results view. Developers can modify the generated Python/PySpark code, save it, and trigger a re-reconciliation against the reference CSV without leaving the UI.

Distinct from F7 (side-by-side read-only diff) — this is an active editing surface.

---

### F14 — Authentication & SSO Integration
**Area:** Backend + Frontend / Security  
**Serves:** US1, US2  
**Phase:** 4

Secure login with SSO (SAML 2.0 / OIDC) and token-based API access (JWT). Role-based access: viewer (read-only), engineer (submit migrations), admin (manage users and configuration).

Not needed for MVP (single-team, controlled deployment). Required before any shared or customer-facing deployment.

---

### F15 — Record-Level Reconciliation
**Area:** Backend / Data Validation & Quality  
**Serves:** US1  
**Phase:** 2

Row-by-row comparison of SAS output vs Python output with configurable key columns, sort order, and numeric tolerance. For each mismatched row, reports the key, which columns differ, and the delta. Produces a diff table suitable for QA review.

Extends F3 (which covers schema, row count, and aggregates). The row-level hash diff already in F3 scope is a simpler predecessor; this feature adds full column-level diff detail and configurable tolerances.

---

### F16 — Migration Tracking Dashboard
**Area:** Frontend / Reporting  
**Serves:** US2  
**Phase:** 3

A summary view for engineering leads and C-level stakeholders: total SAS files submitted, percentage migrated, reconciliation pass rates, time per migration, and outstanding failures. Filters by date range and status.

Data is derived entirely from the jobs table — no new backend logic required.

---

### F17 — End-to-End ETL Pipeline View
**Area:** Frontend / Understanding & Comparison  
**Serves:** US1, US2  
**Phase:** 3

A visual overview of a complete migrated ETL pipeline: each processing step as a node (DATA step, PROC SQL, PROC SORT), connected by data flow edges, with status indicators (migrated, untranslatable, flagged). Clicking a node shows the SAS source and generated Python side by side.

Distinct from F6 (dependency graph between SAS files) — this is a within-job step view.

---

### F18 — Refine Conversion Action
**Area:** Frontend + Backend / Migration Engine  
**Serves:** US1  
**Phase:** 2

A "Refine" button on the job results page that re-submits the same SAS input to the LLM with additional context: the previous output, the reconciliation report, and explicit instructions to fix failing checks. The worker runs the full pipeline again and saves a new version (see F10).

Requires F10 (artefact versioning) to be meaningful.
