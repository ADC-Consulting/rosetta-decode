# sas_pharma_sandbox

**Fictional study:** ADC-XYZ-001 (Phase 2 clinical trial)
**Domain:** Clinical data management — SDTM build and ADaM subject-level analysis dataset (ADSL)
**Study ID macro:** `STUDYID = ADC-XYZ-001`, 500 synthetic subjects

## What this project does

This SAS batch pipeline constructs a standard CDISC-compliant data package for a fictional Phase 2 drug trial. It reads raw Electronic Data Capture (EDC) extracts, standardises them into SDTM (Study Data Tabulation Model) datasets, then derives an ADaM (Analysis Data Model) subject-level dataset used for safety and efficacy reporting.

1. Reads raw demographic, exposure, adverse event, lab, and vital signs feeds from the EDC (`data/raw/`)
2. Builds SDTM.DM — subject demographics; handles UTF-8 BOM input and ISO date parsing (`01_build_sdtm_dm.sas`)
3. Builds SDTM.EX — exposure/dosing records; deduplicates duplicate dosing rows with PROC SORT NODUPKEY (`02_build_sdtm_ex.sas`)
4. Builds SDTM.AE — adverse events; derives per-subject sequence numbers using RETAIN + BY + FIRST. (`03_build_sdtm_ae.sas`)
5. Builds SDTM.LB — laboratory results; handles Latin-1 encoded input, char→numeric coercion, and pivots via PROC TRANSPOSE (`04_build_sdtm_lb.sas`)
6. Derives ADaM ADSL — subject-level analysis dataset: first dose dates via macro SQL, age group via PROC FORMAT/PUT, BY-merge with IN= flags, INTCK duration calculation, AE summary (`05_build_adam_adsl.sas`)

## File map

| File | Purpose |
|---|---|
| `sas/00_setup.sas` | LIBNAME assignments, OPTIONS, PROC FORMAT inclusion, macro %INCLUDEs |
| `sas/01_build_sdtm_dm.sas` | Raw DM → SDTM.DM; ISO date parse, LENGTH truncation, UTF-8 BOM input |
| `sas/02_build_sdtm_ex.sas` | Raw EX → SDTM.EX; PROC SORT NODUPKEY to dedup duplicate dosing rows |
| `sas/03_build_sdtm_ae.sas` | Raw AE → SDTM.AE; RETAIN + BY + FIRST. for per-subject AESEQ counter; PUT with format |
| `sas/04_build_sdtm_lb.sas` | Raw LB → SDTM.LB; Latin-1 encoding, char→numeric coercion, PROC TRANSPOSE pivot |
| `sas/05_build_adam_adsl.sas` | SDTM → ADaM ADSL; macro calls, PROC SQL HAVING, BY-merge with IN=, INTCK |
| `sas/run_all.sas` | Batch entry point — %INCLUDEs 00–05 in sequence |
| `macros/m_first_dose.sas` | PROC SQL inside macro; dedup subquery; MIN/MAX first/last dose dates |
| `macros/m_derive_age_group.sas` | %if/%do guard; PUT with PROC FORMAT age group format |
| `macros/m_safety_flag.sas` | Returns value via %GLOBAL macro variable (scope side-effect) |
| `macros/m_merge_check.sas` | BY-group MERGE with IN= flags; inner-join semantics |
| `formats/pharma_formats.sas` | PROC FORMAT: age group ranges, sex decode, AE severity grade labels |

## Input data

| File | Location | Rows | Notes |
|---|---|---|---|
| `dm_raw.csv` | `data/raw/` | 500 | Subject demographics; UTF-8 BOM encoded |
| `ex_raw.csv` | `data/raw/` | ~612 | Dosing records; ~11 intentional duplicate rows |
| `ae_raw.csv` | `data/raw/` | ~1 043 | Adverse events; variable rows per subject |
| `lb_raw.csv` | `data/raw/` | 12 000 | Lab results; Latin-1 encoded; ~2% missing values |
| `vs_raw.csv` | `data/raw/` | ~2 000 | Vital signs (SYSBP); 4 visits per subject |

## Golden output

| File | Corresponds to | Grain |
|---|---|---|
| `data/golden/adsl_expected.csv` | `adam.adsl` written by `05_build_adam_adsl.sas` | One row per subject (500 rows) |

The golden file is derived from the same subject-level logic as the SAS pipeline but generated independently by `scripts/generate_pharma_data.py` (seed `20260505`). Rosetta's reconciliation check compares the executor's `adsl_actual.csv` output against this file.

## Runtime output directories

SAS writes intermediate datasets here at run time — empty on first checkout:

| Directory | Content |
|---|---|
| `data/sdtm/` | SDTM.DM, SDTM.EX, SDTM.AE, SDTM.LB (SAS7BDAT) |
| `data/adam/` | ADAM.ADSL + `adsl_actual.csv` |
| `data/logs/` | `run_all.log` — synthetic execution log |

## Difficulties embedded

These are the deliberate translation challenges rosetta must handle:

| # | Pattern | Where |
|---|---|---|
| 1 | RETAIN + BY + FIRST./LAST. | `03_build_sdtm_ae.sas` |
| 2 | MERGE with IN= flags (inner/left join semantics) | `05_build_adam_adsl.sas`, `m_merge_check.sas` |
| 3 | PROC FORMAT + PUT(x, fmt.) | `03_build_sdtm_ae.sas`, `m_derive_age_group.sas`, `formats/` |
| 4 | %macro / %if / %do / &var resolution | all macros |
| 5 | SAS dates — INPUT(yymmdd10.), INTCK, FORMAT yymmdd10. | `01`, `02`, `03`, `05` |
| 6 | Implicit numeric↔char coercion | `04_build_sdtm_lb.sas` |
| 7 | PROC SQL with HAVING | `05_build_adam_adsl.sas` |
| 8 | PROC TRANSPOSE (wide pivot) | `04_build_sdtm_lb.sas` |
| 9 | Missing-value semantics (`.` vs `''`) | `04_build_sdtm_lb.sas` |
| 10 | LENGTH controlling string truncation | `01_build_sdtm_dm.sas`, `05_build_adam_adsl.sas` |
| 11 | Row-sequence accumulator (AESEQ + 1) | `03_build_sdtm_ae.sas` |
| 12 | %PUT log-only side effects | `05_build_adam_adsl.sas` |
| 13 | LIBNAME path references | `00_setup.sas` |
| 14 | Mixed file encodings (UTF-8 BOM, Latin-1) | `dm_raw.csv`, `lb_raw.csv` |
| 15 | Duplicate dosing rows requiring dedup | `ex_raw.csv` → `02_build_sdtm_ex.sas` |
