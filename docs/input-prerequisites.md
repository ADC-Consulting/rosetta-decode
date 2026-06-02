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

---

## What is extracted from each file type

This table describes what is currently read from each accepted file type. "Accepted but not extracted" means the file is stored and made available to the executor at runtime, but the metadata it contains is not parsed into the migration model.

| File type | What is currently extracted | What is accepted but not yet extracted |
|---|---|---|
| `.sas` | Block boundaries (DATA/PROC), LIBNAME declarations, `%LET` values, `%MACRO`/`%MEND` definitions, PROC type, input/output dataset names, DROP/KEEP/WHERE/ARRAY statements | `INFILE`/`INPUT` column definitions (fixed/delimited layouts); `CALL SYMPUT`/`SYMPUTX` runtime assignments; `PROC FORMAT` value-to-label mappings; `PROC SQL CREATE TABLE` column definitions; variable-level `FORMAT`/`INFORMAT` statements; `LIBNAME` engine type (`ENGINE=` option); `PROC TABULATE` structure |
| `.sas7bdat` | Dataset loaded as DataFrame and made available to the executor | Column labels (`meta.column_labels`), column display formats (`meta.column_formats`), variable types and lengths (`meta.readstat_variable_types`, `meta.column_lengths`), row count (`meta.row_count`) |
| `.csv` (reference) | Schema (column names, types), row count, aggregate sums — used for reconciliation checks | — |
| `.log` | NOTE lines with row counts, WARNING/ERROR context, macro expansion hints (via `LogInspectionAgent`) | Detailed variable attribute listings from `PROC CONTENTS` output written to log |
| `.xlsx` / `.xls` | File stored and rewritten as pandas `read_excel()` call at executor runtime | Column types, sheet names, named ranges — inferred by LLM, not parsed |

---

## Metadata gaps and their impact

The following metadata is present in SAS project files but not yet extracted. Each gap reduces translation accuracy in a specific way.

### Column types, labels, and formats from `.sas7bdat`

SAS stores rich per-column metadata in binary datasets: display formats (e.g. `DATE9.`, `DOLLAR12.2`), variable labels (human-readable column descriptions), and storage types (character vs. numeric). None of this is currently read from the file.

**Impact:** Column labels are lost; display formats are not converted to equivalent pandas/PySpark formatters; numeric/character type ambiguity falls to the LLM.

### `PROC FORMAT` value-to-label mappings

SAS `PROC FORMAT` defines lookup tables that map raw values to display labels (e.g. `1 = 'Male'`, `2 = 'Female'`). The parser detects these blocks but does not parse the inner `VALUE` statements.

**Impact:** Format definitions are not converted to Python dictionaries or `pd.Categorical` mappings; any downstream report that relies on formatted values will show raw codes.

### `INFILE` / `INPUT` column layout

SAS reads flat files using `INFILE` (file path) and `INPUT` (column layout). Fixed-column and delimiter-separated layouts define column names, positions, and types. The parser does not extract these.

**Impact:** Column definitions for flat-file ingestion blocks are unknown to the planner; the LLM must infer them, which is unreliable for fixed-column layouts.

### `CALL SYMPUT` / `CALL SYMPUTX`

These statements assign macro variables at runtime based on data values (e.g. the maximum date in a dataset becomes `&MAX_DATE`). They cannot be resolved statically.

**Impact:** Dynamic macro variables appear as unresolved tokens in downstream steps; translation quality degrades for any block that depends on runtime-computed parameters.

### `LIBNAME` engine type

The `LIBNAME` statement can reference different storage engines (base SAS, Hadoop via HDFS, ODBC, SAS/SHARE). The engine type is not stored.

**Impact:** All LIBNAME references are treated as local SAS datasets; Hadoop or ODBC sources are not flagged, which matters for Data Storage tab mapping in the 5-tab restructure.

---

## Planned but not yet implemented

These capabilities are in scope and tracked in the backlog, but not yet built. The upload infrastructure accepts the relevant files today; extraction logic is what is missing.

| Item | Backlog reference | Needed for |
|---|---|---|
| `.sas7bdat` column metadata — labels, display formats, variable types, lengths, row count | Tier 1 gap (#39 findings) | Data Storage tab (#43): column inventory with types/lengths; BI tab (#44): column labels as semantic layer dimension names |
| `PROC FORMAT` value-to-label mapping — inner `VALUE`/`INVALUE` pair parsing | Tier 1 gap (#39 findings) | BI tab (#44): format definitions map to dimension members; without them the tab can confirm a format exists but not what it contains |
| `LIBNAME` engine type — `ENGINE=` option on `LIBNAME` statements | Tier 2 gap (#39 findings) | Data Storage tab (#43): distinguishing local SAS libraries from ODBC/Hadoop external sources in the storage map |
| Column-level reconciliation — row-by-row diff with configurable keys and tolerances | F15 (Phase 2 backlog) | High-confidence verification of numeric pipelines beyond aggregate checks |

---

## Out of scope

The following are explicitly not supported and will not be implemented. These are hard technical limits or deliberate product boundaries, not deferred work.

| Item | Reason |
|---|---|
| `.sas7bcat` — SAS format/macro catalogs in binary format | Requires a live SAS installation to decode; no open-source reader covers the full spec |
| `.stx` / `.sas7bndx` — SAS transport and index files | No practical extraction path; content is redundant with `.sas7bdat` for migration purposes |
| Pre-compiled macro catalogs | Macros must be provided in source form (`.sas` files); compiled catalogs are not readable without SAS |
| External database schema queries (ODBC/Hadoop) | The tool cannot connect to external databases; live schema introspection is out of scope. Note: the engine type declared in the `LIBNAME` statement *is* extractable from source text and is tracked as a planned gap above |
| `PROC CAS` / CASL (SAS Viya) | CAS-specific statements are flagged as unrecognised blocks; no translation is attempted. Viya support is not planned |
