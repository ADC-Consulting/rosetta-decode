# SAS -> PySpark Conversion Test Harness (SDTM/ADaM)

Synthetic pharma pipeline used to evaluate an LLM agent that converts SAS
legacy code into PySpark.

## Layout
- `data/raw/`        synthetic EDC extracts (input)
- `data/sdtm/`       SDTM datasets (produced by SAS at runtime)
- `data/adam/`       ADaM datasets (produced by SAS at runtime)
- `data/golden/`     **adsl_expected.csv** = reconciliation target
- `sas/`             SAS code your agent must convert
- `macros/`          SAS macros
- `formats/`         PROC FORMAT catalog
- `logs/`            synthetic execution log

## Difficulties Embedded
1.  RETAIN + BY + FIRST./LAST.
2.  MERGE with IN= flags
3.  PROC FORMAT + PUT(x, fmt.)
4.  %macro / %if / %do / &var resolution
5.  SAS dates, INPUT(yymmdd10.), INTCK
6.  Implicit numeric<->char coercion
7.  PROC SQL with HAVING
8.  PROC TRANSPOSE
9.  Missing-value semantics (. vs '')
10. LENGTH controlling truncation
11. Sequence variables via accumulator (AESEQ + 1)
12. Log-only side effects (%put)
13. LIBNAME paths
14. Mixed encodings (UTF-8 BOM, Latin-1)
15. Duplicate dosing rows

## Reconciliation target
The agent's PySpark pipeline should produce `data/adam/adsl_actual.csv` with
the same rows and columns as `data/golden/adsl_expected.csv`.
