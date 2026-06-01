# Input Prerequisites

What rosetta-decode needs from you before it can run a migration.

---

## Required inputs

### SAS source files (`.sas`) — required

At least one `.sas` file must be uploaded. Multi-file projects (main script + macro modules + `%INCLUDE` targets) are fully supported — upload all files together in a `.zip` and the tool will resolve dependencies in the correct execution order.

**What the parser expects:**

- Standard Base SAS syntax (SAS 9.x)
- `DATA` / `RUN;` block boundaries
- `PROC <name>` / `RUN;` or `PROC <name>` / `QUIT;` boundaries
- `%LET` macro variable declarations
- `%MACRO` / `%MEND` macro definitions and `%<macroname>()` calls

**What the parser does not require:**

- A SAS license or SAS installation — the tool reads source text only
- Pre-compiled macro catalogs — macros must be in source form (`.sas` files)
- A specific file encoding — UTF-8 and Windows-1252 are both handled

---

## Optional reference inputs

These files are not required to run a migration but significantly improve reconciliation accuracy.

### Reference CSV (`.csv`)

A CSV file exported from SAS containing the expected output of the pipeline. Used by the reconciliation engine to verify that the Python-generated output matches SAS output on:

- Schema parity (column names and types)
- Row count
- Aggregate parity (SUM, COUNT, AVG on numeric columns)

**How to produce one from SAS:**

```sas
PROC EXPORT DATA=your_output_dataset
    OUTFILE='/path/to/reference.csv'
    DBMS=CSV REPLACE;
RUN;
```

Upload via the `ref_csv` field in the UI or API.

### SAS binary dataset (`.sas7bdat`)

A SAS binary dataset, typically an input or reference dataset. Read via `pyreadstat` and made available to the migration pipeline as a pandas DataFrame (local) or PySpark DataFrame (cloud).

Upload via the `ref_dataset` field in the UI or API.

### SAS execution log (`.log`)

A SAS log file from a previous run of the SAS pipeline. Used by the tool to:

- Detect runtime macro expansions that are not visible in the static source
- Identify datasets created or modified at runtime
- Enrich the translation context for the LLM

Not required; the tool migrates from source alone if no log is provided.

### Excel files (`.xlsx` / `.xls`)

Excel files that serve as input data to the SAS pipeline (e.g. lookup tables, reference data). Uploaded alongside SAS source and made available to the executor at runtime via the `/workspace/data/` path.

---

## Accepted upload formats

| Format | Role | Required? |
|---|---|---|
| `.sas` | SAS source file | Yes (at least one) |
| `.zip` | Archive containing any of the below | Alternative to individual uploads |
| `.csv` | Reference output for reconciliation | No |
| `.sas7bdat` | SAS binary dataset (input or reference) | No |
| `.log` | SAS execution log | No |
| `.xlsx` / `.xls` | Excel input data | No |

**Zip uploads:** A `.zip` may contain any mix of the above. Files with unrecognised extensions are rejected with a manifest listing what was accepted and what was skipped. No file count limit.

---

## SAS version compatibility

| Version | Status |
|---|---|
| SAS 9.3, 9.4 | Tested and supported |
| SAS 9.1, 9.2 | Supported (syntax is largely identical) |
| SAS Viya (SAS Cloud Analytic Services) | Not tested; most DATA step / PROC SQL syntax is compatible, but CAS-specific statements (`PROC CAS`, `CASL`) are flagged as unrecognised |
| SAS 6.x | Not tested; older syntax variants (e.g. `%*` comment style) may not parse correctly |

---

## System requirements

The tool itself requires:

- Docker + Docker Compose (all services are containerised)
- An LLM API key — Anthropic (Claude) by default; Azure OpenAI is also supported via `LLM_MODEL` in `.env`
- No SAS license or SAS installation

The uploaded SAS files must be self-contained or complete: if your SAS project references external macro libraries or data libraries not included in the upload, those references will be flagged as unresolved but will not block the migration.

---

## What makes a good migration input

- **Multi-file zip with all `%INCLUDE` targets** — the more complete the project, the more accurate the dependency graph and macro resolution
- **Reference CSV exported from the same SAS run** — enables automatic reconciliation; without it the tool can only verify execution (no errors) but cannot confirm numeric correctness
- **Descriptive variable and dataset names** — the LLM uses these as context; cryptic SAS names (`ds1`, `tmp`, `x`) produce lower-confidence translations
- **A SAS log from a real run** — captures runtime macro expansions and branch decisions that are invisible in source-only analysis
