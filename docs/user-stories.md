# User Stories

## US1 — Technical User: Automated ETL Pipeline Generation

**As a** data engineer or developer,  
**I want** a tool that generates a full ETL automated pipeline in Python from our legacy SAS code,  
**So that** I can use the data directly (not just generate it), remain tool-agnostic (local or Databricks), and see transparently what happened during migration.

### Acceptance Criteria

- [ ] Given a SAS script, the system produces a runnable Python ETL pipeline
- [ ] The pipeline runs locally (pandas/DuckDB) when `CLOUD=false` and on Databricks (PySpark) when `CLOUD=true`
- [ ] Every generated line includes a provenance comment `# SAS: <file>:<line>`
- [ ] Any SAS construct that cannot be translated is flagged as `# SAS-UNTRANSLATABLE: <reason>` rather than silently dropped
- [ ] The same SAS input always produces the same Python output (deterministic)
- [ ] A reconciliation report is produced showing the generated output matches the original SAS results
- [ ] The dependency graph shows which SAS jobs/datasets feed which steps
- [ ] A side-by-side view lets the developer compare SAS and Python code block by block

---

## US2 — Non-Technical User: Explainable, Trustworthy Migration

**As a** business analyst, compliance officer, or finance stakeholder,  
**I want** an explanation of how the SAS logic was translated into Python,  
**So that** I can trust the output, check the documentation, and confirm it is compliant.

### Acceptance Criteria

- [ ] For any migrated pipeline, a plain-English explanation is available describing what the SAS code did and how the Python equivalent replicates it
- [ ] The explanation is structured (step by step), not a wall of text
- [ ] A reconciliation report (schema parity, row counts, aggregate checks) is accessible and readable by non-engineers
- [ ] A lineage view shows end-to-end data flow without requiring knowledge of the code
- [ ] The system flags any part of the migration that required manual review or could not be automated
- [ ] All outputs are audit-ready: traceable back to source SAS line numbers
