# Effort Estimation Model (PROVISIONAL)

> **Status: PROVISIONAL placeholder.** The consultant-day rates below are first-pass
> round numbers chosen to make the F77 scoping report structurally complete. They are
> **not** calibrated against real engagements and **must not** be quoted as committed
> estimates. The scoping report always carries `provisional: true` on its effort block,
> and the UI renders a "Provisional" badge. Replace these rates with calibrated figures
> once we have engagement data.

## Purpose

The F77 scoping/assessment mode produces a fast, LLM-free pre-sales estimate of the
effort to migrate a SAS file set. This document defines the **rate model** that turns
the per-file complexity inventory (from the static parser) into a low / mid / high
consultant-day estimate.

The model is intentionally simple and fully deterministic: same file inventory + same
rate table → byte-identical estimate (no LLM, no clock, no I/O). It is implemented in
[`src/worker/engine/estimation_model.py`](../../src/worker/engine/estimation_model.py)
(`RATE_TABLE` + `estimate_effort`).

## Complexity tiers

Each `.sas` file is classified into one tier by the scoping engine
([`src/worker/engine/scoping.py`](../../src/worker/engine/scoping.py)). Rules (no LLM):

| Tier | Rule |
|---|---|
| **simple** | Block types are a subset of `{DATA_STEP, PROC_SORT}` — no PROC SQL, no macro complexity. |
| **moderate** | Anything not simple or complex — typically PROC SQL and/or macros present. |
| **complex** | Any of: PROC IML / PROC OPTMODEL / PROC FCMP / PROC UNKNOWN; an ODS statement; external platform I/O (an `INFILE`/`FILE` path, or a non-`BASE` LIBNAME engine); or heavy macro nesting (nested `%macro`, or `%do`/`%if` nesting depth > 2). |

## Rate table (per file, consultant-days)

Each tier maps to `(low, mid, high)` consultant-days **per file**:

| Tier | Low | Mid | High |
|---|---|---|---|
| simple | 0.25 | 0.5 | 1.0 |
| moderate | 1.0 | 2.0 | 3.5 |
| complex | 3.0 | 5.0 | 8.0 |

## Computation

```
total_low  = Σ rate_low(tier_of_file)   over all .sas files
total_mid  = Σ rate_mid(tier_of_file)
total_high = Σ rate_high(tier_of_file)
```

Totals are rounded to 4 decimals for float stability. An empty inventory yields all zeros.

## Known limitations (intentionally surfaced — "no silent caps")

- Rates are uncalibrated placeholders, not derived from real engagement data.
- The model is per-file and tier-based; it does not yet weight by block count within a
  file, reconciliation availability, or data-volume.
- It does not account for cross-file dependency complexity or missing reference data
  beyond what the risk flags surface separately in the report.

These limitations are echoed in the report's `notes` and the `EffortEstimate.basis` string.
