# Features

## F1 — Automated SAS-to-Python Pipeline Generation
**Area:** Backend / Migration Engine  
**Serves:** US1

Ingests one or more SAS scripts, calls a hosted LLM with the SAS source as context, and produces a complete runnable ETL pipeline in Python. Execution mode is controlled by the `CLOUD` flag in `.env`: `false` → pandas/DuckDB (local), `true` → PySpark (Databricks).

The engine handles: DATA steps, PROC SQL, PROC SORT, macro definitions and calls, macro variable resolution. SAS constructs that cannot be reliably translated (e.g. PROC MIXED, ODS, platform-specific I/O) are preserved as comments marked `# SAS-UNTRANSLATABLE: <reason>` so engineers know exactly what needs manual attention.

Every generated line carries a provenance comment `# SAS: <file>:<line>`. Output is deterministic: identical SAS input always produces identical Python output, enabling version control and audit trails.

---

## F2 — Code Explanation Assistant UI
**Area:** Frontend / Input & Editing  
**Serves:** US2

A chat-style interface where a developer or analyst pastes a SAS snippet or selects a generated Python block and asks the system to explain it. The product calls a hosted LLM and returns a step-by-step plain-English breakdown: what the code does, why each transformation exists (inferred from variable names, SAS log context, and domain patterns), and what the Python equivalent achieves.

Designed for onboarding engineers unfamiliar with legacy SAS idioms and for non-technical stakeholders who need to validate logic without reading code.

---

## F3 — Validation & Reconciliation
**Area:** Backend / Data Validation & Quality  
**Serves:** US1, US2

After migration, runs automated checks to prove that the Python pipeline produces results that match the original SAS outputs. Checks include:

- **Schema parity** — column names and data types match
- **Row count** — same number of rows
- **Row-level hash diff** — detects row-level discrepancies on key columns
- **Aggregate parity** — SUM, COUNT, AVG on financial/metric columns match within tolerance
- **Distribution checks** — percentile distributions are consistent

Produces a structured reconciliation report (pass/fail per check, diff summary, sample of mismatches) suitable for financial audit sign-off and compliance review.

---

## F4 — Log-Based Reverse Engineering
**Area:** Backend / Migration Engine  
**Serves:** US1

Ingests SAS execution logs (`.log` files), sends them to a hosted LLM, and reconstructs logic that is not obvious from the SAS source alone — including macro expansions as they were resolved at runtime, conditional branches that were taken, and dataset filters applied dynamically.

Converts this reconstructed runtime logic into Python alongside (or instead of) the static source parse. Particularly useful when SAS source is incomplete, obfuscated, heavily macro-driven, or was written by engineers no longer at the company.

---

## F5 — Lineage Visibility UI for QA
**Area:** Frontend / QA & Audit Views  
**Serves:** US2

A read-only view showing the full data lineage of a migrated pipeline: which SAS datasets and files feed which processing steps, which steps produce which outputs, and how each maps to the generated Python code. QA teams and compliance officers can trace any specific column, aggregate, or output back to its SAS source without needing to read code.

Designed for audit and compliance workflows, not active development.

---

## F6 — Dependency Graph Visualization
**Area:** Frontend / Understanding & Comparison  
**Serves:** US1

An interactive graph where nodes represent SAS jobs, datasets, macros, and include files, and edges represent dependencies between them. Supports filtering by type, zooming, and clicking a node to inspect the associated source code or migration status.

Helps engineers understand the full dependency tree before starting migration: identify the correct migration order, find orphaned datasets, detect circular dependencies, and scope the effort.

---

## F7 — Side-by-Side SAS vs Python/PySpark View
**Area:** Frontend / Understanding & Comparison  
**Serves:** US1, US2

A diff-style interface showing original SAS code on the left and generated Python/PySpark on the right, synchronized by logical block (DATA step ↔ DataFrame transform, PROC SQL ↔ SQL query, macro call ↔ function call).

Developers can review each block, accept it, edit it inline, or flag it for manual review. Also supports running both versions against a sample dataset and comparing output tables directly in the UI — making it possible to spot discrepancies without switching tools.
