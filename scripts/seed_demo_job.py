#!/usr/bin/env python3
r"""Seed a demo migration job for showcasing the product.

Creates a complete "Monthly Revenue Pipeline" job that demonstrates:
- Clear 6-step ETL lineage (Source Pipeline view)
- Mix of auto-verified, needs-review, and manual blocks
- Populated data model with 10 tables across two schemas (Data Storage tab)

Usage:
    DATABASE_URL=postgresql+asyncpg://rosetta:rosetta@localhost:5432/rosetta \\
        uv run python scripts/seed_demo_job.py

    # Or with Docker running:
    uv run python scripts/seed_demo_job.py
"""

import asyncio
import hashlib
import os
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Use project ORM models so JSON serialisation is handled by SQLAlchemy.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.backend.db.models import BlockRevision, Job

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://rosetta:rosetta@localhost:5432/rosetta",
)

DEMO_JOB_ID = "dec0de00-0000-4000-8000-000000000001"
DEMO_JOB_NAME = "Monthly Revenue Pipeline"

# ---------------------------------------------------------------------------
# SAS source files
# ---------------------------------------------------------------------------

SAS_FILES = {
    "autoexec.sas": """\
options mprint mlogic symbolgen;

%let root = /path/to/sas_project;

libname rawdir "&root./data/raw";
libname outdir "&root./data/output";

filename csvcust  "&root./data/raw/customers.csv";
filename csvtx    "&root./data/raw/transactions.csv";
filename csvfx    "&root./data/raw/exchange_rates.csv";
filename xlsprod  "&root./data/raw/products.xlsx";
""",
    "macros/clean_string.sas": """\
%macro clean_string(val);
    %sysfunc(strip(%sysfunc(upcase(&val))))
%mend;
""",
    "macros/assert_rowcount.sas": """\
%macro assert_rowcount(ds, min_rows);
    %local nobs;
    proc sql noprint;
        select count(*) into :nobs from &ds.;
    quit;
    %if &nobs. < &min_rows. %then %do;
        %put ERROR: Dataset &ds. has only &nobs. rows, expected at least &min_rows.;
        %abort cancel;
    %end;
%mend;
""",
    "sas/01_load_sources.sas": """\
/* 01_load_sources.sas - import CSV/XLSX sources */
%include "&root./sas/autoexec.sas";

proc import datafile=csvcust out=rawdir.customers dbms=csv replace;
    guessingrows=max;
run;

proc import datafile=csvtx out=rawdir.transactions dbms=csv replace;
    guessingrows=max;
run;

proc import datafile=csvfx out=rawdir.exchange_rates dbms=csv replace;
    guessingrows=max;
run;

proc import datafile=xlsprod out=rawdir.products dbms=xlsx replace;
    sheet="Sheet1"; getnames=yes;
run;
""",
    "sas/02_clean_customers.sas": """\
/* 02_clean_customers.sas */
%include "&root./sas/autoexec.sas";
%include "&root./macros/clean_string.sas";
%include "&root./macros/assert_rowcount.sas";

data rawdir.customers_clean;
    set rawdir.customers;
    if missing(CUSTOMER_ID) then delete;
    COUNTRY_CLEAN = %clean_string(COUNTRY);
    SEGMENT_CLEAN = %clean_string(SEGMENT);
run;

%assert_rowcount(rawdir.customers_clean, 1);
""",
    "sas/03_clean_transactions.sas": """\
/* 03_clean_transactions.sas */
%include "&root./sas/autoexec.sas";
%include "&root./macros/assert_rowcount.sas";

data rawdir.transactions_clean;
    set rawdir.transactions;
    if missing(CUSTOMER_ID) then delete;
    if missing(CURRENCY)    then delete;
    if AMOUNT_LOCAL <= 0    then delete;
run;

%assert_rowcount(rawdir.transactions_clean, 1);
""",
    "sas/04_join_and_aggregate.sas": """\
/* 04_join_and_aggregate.sas - FX convert, enrich, aggregate */
%include "&root./sas/autoexec.sas";

proc sql;
    create table work.tx_fx as
    select t.CUSTOMER_ID,
           t.PRODUCT_ID,
           datepart(t.TX_DATE) as TX_DATE format=yymmdd10.,
           t.AMOUNT_LOCAL,
           t.CURRENCY,
           f.RATE_TO_EUR,
           (t.AMOUNT_LOCAL / f.RATE_TO_EUR) as AMOUNT_EUR
    from rawdir.transactions_clean as t
    inner join rawdir.exchange_rates as f
      on datepart(t.TX_DATE) = input(f.DATE, yymmdd10.)
     and t.CURRENCY = f.CURRENCY;
quit;

proc sql;
    create table work.tx_fx_cat as
    select x.*, p.CATEGORY
    from work.tx_fx as x
    left join rawdir.products as p
      on x.PRODUCT_ID = p.PRODUCT_ID;
quit;

proc sql;
    create table outdir.customer_revenue_daily as
    select c.CUSTOMER_ID,
           x.TX_DATE as DATE,
           sum(x.AMOUNT_EUR) as TOTAL_EUR,
           c.COUNTRY_CLEAN,
           c.SEGMENT_CLEAN,
           c.IS_ACTIVE
    from work.tx_fx_cat as x
    inner join rawdir.customers_clean as c
      on x.CUSTOMER_ID = c.CUSTOMER_ID
    group by c.CUSTOMER_ID, x.TX_DATE, c.COUNTRY_CLEAN, c.SEGMENT_CLEAN, c.IS_ACTIVE;
quit;

proc sql;
    create table outdir.category_revenue as
    select CATEGORY, sum(AMOUNT_EUR) as TOTAL_EUR
    from work.tx_fx_cat
    group by CATEGORY
    order by TOTAL_EUR desc;
quit;
""",
    "sas/05_risk_scoring_iml.sas": """\
/* 05_risk_scoring_iml.sas
   Descriptive stats on daily revenue: mean, sample std, z-score with zero guard. */
%include "&root./sas/autoexec.sas";

proc iml;
    use outdir.customer_revenue_daily;
    read all var {CUSTOMER_ID DATE TOTAL_EUR} into X[colname=vars];
    close outdir.customer_revenue_daily;

    revenue  = X[, 3];
    mean_rev = mean(revenue);
    std_rev  = std(revenue);
    if std_rev = 0 then std_rev = 1;

    z   = (revenue - mean_rev) / std_rev;
    out = X || z;

    create outdir.customer_revenue_zscore
        from out[colname={"CUSTOMER_ID" "DATE" "TOTAL_EUR" "Z_SCORE"}];
    append from out;
    close outdir.customer_revenue_zscore;
quit;
""",
    "sas/06_summary_stats.sas": """\
/* 06_summary_stats.sas - PROC SORT + PROC MEANS */
%include "&root./sas/autoexec.sas";

proc sort data=outdir.customer_revenue_daily
          out=work.revenue_sorted;
    by SEGMENT_CLEAN COUNTRY_CLEAN;
run;

proc means data=work.revenue_sorted noprint;
    class SEGMENT_CLEAN COUNTRY_CLEAN;
    var TOTAL_EUR;
    output out=outdir.revenue_summary
        n=N_ROWS
        mean=MEAN_EUR
        sum=SUM_EUR
        min=MIN_EUR
        max=MAX_EUR;
run;
""",
}

# ---------------------------------------------------------------------------
# Generated Python files
# ---------------------------------------------------------------------------

GENERATED_FILES = {
    "pipeline.py": """\
\"\"\"Monthly Revenue Pipeline — generated by Rosetta Decode.\"\"\"
# Run each step in order. Edit risk_scoring.py before running in production.
import load_sources
import clean_validate
import fx_enrich
import aggregate
import risk_scoring   # MANUAL — review before running
import summary_stats


def run() -> None:
    load_sources.run()
    clean_validate.run()
    fx_enrich.run()
    aggregate.run()
    risk_scoring.run()
    summary_stats.run()


if __name__ == "__main__":
    run()
""",
    "load_sources.py": """\
\"\"\"Step 1: ingest raw CSV/XLSX sources into parquet staging.\"\"\"
import pandas as pd


def run() -> None:
    # SAS: sas/01_load_sources.sas:4
    customers = pd.read_csv("data/raw/customers.csv")
    customers.to_parquet("data/staging/customers.parquet", index=False)

    # SAS: sas/01_load_sources.sas:8
    transactions = pd.read_csv("data/raw/transactions.csv")
    transactions.to_parquet("data/staging/transactions.parquet", index=False)

    # SAS: sas/01_load_sources.sas:12
    exchange_rates = pd.read_csv("data/raw/exchange_rates.csv")
    exchange_rates.to_parquet("data/staging/exchange_rates.parquet", index=False)

    # SAS: sas/01_load_sources.sas:16
    # REVIEW REQUIRED: openpyxl required; confirm sheet name "Sheet1" is still correct
    products = pd.read_excel("data/raw/products.xlsx", sheet_name="Sheet1", header=0)
    products.to_parquet("data/staging/products.parquet", index=False)
""",
    "clean_validate.py": """\
\"\"\"Step 2: clean and validate customer and transaction records.\"\"\"
import pandas as pd


def run() -> None:
    # SAS: sas/02_clean_customers.sas:5
    customers = pd.read_parquet("data/staging/customers.parquet")
    customers = customers.dropna(subset=["CUSTOMER_ID"])
    customers["COUNTRY_CLEAN"] = customers["COUNTRY"].str.strip().str.upper()
    customers["SEGMENT_CLEAN"] = customers["SEGMENT"].str.strip().str.upper()
    customers.to_parquet("data/staging/customers_clean.parquet", index=False)

    # SAS: sas/02_clean_customers.sas:12 (%assert_rowcount)
    # REVIEW REQUIRED: macro asserts row count >= 1; aborts pipeline on failure
    assert len(customers) >= 1, "customers_clean is empty — pipeline aborted"

    # SAS: sas/03_clean_transactions.sas:4
    transactions = pd.read_parquet("data/staging/transactions.parquet")
    transactions = transactions.dropna(subset=["CUSTOMER_ID", "CURRENCY"])
    transactions = transactions[transactions["AMOUNT_LOCAL"] > 0]
    transactions.to_parquet("data/staging/transactions_clean.parquet", index=False)

    # SAS: sas/03_clean_transactions.sas:12 (%assert_rowcount)
    # REVIEW REQUIRED: macro asserts row count >= 1; aborts pipeline on failure
    assert len(transactions) >= 1, "transactions_clean is empty — pipeline aborted"
""",
    "fx_enrich.py": """\
\"\"\"Step 3: FX-convert transaction amounts to EUR and add product category.\"\"\"
import pandas as pd


def run() -> None:
    # SAS: sas/04_join_and_aggregate.sas:4 (PROC SQL — tx_fx)
    transactions = pd.read_parquet("data/staging/transactions_clean.parquet")
    fx = pd.read_parquet("data/staging/exchange_rates.parquet")

    transactions["TX_DATE"] = pd.to_datetime(transactions["TX_DATE"]).dt.normalize()
    fx["DATE"] = pd.to_datetime(fx["DATE"])

    tx_fx = transactions.merge(
        fx,
        left_on=["TX_DATE", "CURRENCY"],
        right_on=["DATE", "CURRENCY"],
        how="inner",
    )
    tx_fx["AMOUNT_EUR"] = tx_fx["AMOUNT_LOCAL"] / tx_fx["RATE_TO_EUR"]
    tx_fx = tx_fx[
        [
            "CUSTOMER_ID", "PRODUCT_ID", "TX_DATE",
            "AMOUNT_LOCAL", "CURRENCY", "RATE_TO_EUR", "AMOUNT_EUR",
        ]
    ]

    # SAS: sas/04_join_and_aggregate.sas:18 (PROC SQL — tx_fx_cat)
    products = pd.read_parquet("data/staging/products.parquet")
    tx_fx_cat = tx_fx.merge(
        products[["PRODUCT_ID", "CATEGORY"]],
        on="PRODUCT_ID",
        how="left",
    )
    tx_fx_cat.to_parquet("data/staging/tx_fx_cat.parquet", index=False)
""",
    "aggregate.py": """\
\"\"\"Step 4: aggregate daily customer revenue and category totals.\"\"\"
import pandas as pd


def run() -> None:
    tx_fx_cat = pd.read_parquet("data/staging/tx_fx_cat.parquet")
    customers = pd.read_parquet("data/staging/customers_clean.parquet")

    # SAS: sas/04_join_and_aggregate.sas:25 (PROC SQL — customer_revenue_daily)
    customer_revenue_daily = (
        tx_fx_cat.merge(
            customers[["CUSTOMER_ID", "COUNTRY_CLEAN", "SEGMENT_CLEAN", "IS_ACTIVE"]],
            on="CUSTOMER_ID",
            how="inner",
        )
        .groupby(
            ["CUSTOMER_ID", "TX_DATE", "COUNTRY_CLEAN", "SEGMENT_CLEAN", "IS_ACTIVE"],
            as_index=False,
        )
        .agg(TOTAL_EUR=("AMOUNT_EUR", "sum"))
        .rename(columns={"TX_DATE": "DATE"})
    )
    customer_revenue_daily.to_parquet("data/output/customer_revenue_daily.parquet", index=False)

    # SAS: sas/04_join_and_aggregate.sas:37 (PROC SQL — category_revenue)
    category_revenue = (
        tx_fx_cat
        .groupby("CATEGORY", as_index=False)
        .agg(TOTAL_EUR=("AMOUNT_EUR", "sum"))
        .sort_values("TOTAL_EUR", ascending=False)
    )
    category_revenue.to_parquet("data/output/category_revenue.parquet", index=False)
""",
    "risk_scoring.py": """\
\"\"\"Step 5: z-score risk scoring on daily revenue.\"\"\"
# ============================================================
# MANUAL MIGRATION REQUIRED — PROC IML
# ============================================================
# PROC IML is SAS's proprietary matrix language.  The NumPy
# implementation below faithfully reproduces the original
# computation but MUST be reviewed before production use:
#
#  - SAS std() uses sample standard deviation (ddof=1)
#  - Zero guard: if std == 0, std is forced to 1.0
#  - Output column order: CUSTOMER_ID, DATE, TOTAL_EUR, Z_SCORE
#
# Validate z-score distributions against the SAS baseline.
# ============================================================
import numpy as np
import pandas as pd


def run() -> None:
    # SAS: sas/05_risk_scoring_iml.sas:3
    df = pd.read_parquet("data/output/customer_revenue_daily.parquet")
    revenue = df["TOTAL_EUR"].to_numpy()

    mean_rev = revenue.mean()
    std_rev = revenue.std(ddof=1)  # sample std, matching SAS std()
    if std_rev == 0.0:
        std_rev = 1.0  # zero guard from original SAS code

    df["Z_SCORE"] = (revenue - mean_rev) / std_rev
    customer_revenue_zscore = df[["CUSTOMER_ID", "DATE", "TOTAL_EUR", "Z_SCORE"]]
    customer_revenue_zscore.to_parquet("data/output/customer_revenue_zscore.parquet", index=False)
""",
    "summary_stats.py": """\
\"\"\"Step 6: sort and summarise revenue by segment and country.\"\"\"
import pandas as pd


def run() -> None:
    df = pd.read_parquet("data/output/customer_revenue_daily.parquet")

    # SAS: sas/06_summary_stats.sas:3 (PROC SORT)
    revenue_sorted = df.sort_values(["SEGMENT_CLEAN", "COUNTRY_CLEAN"])

    # SAS: sas/06_summary_stats.sas:8 (PROC MEANS with CLASS)
    # REVIEW REQUIRED: PROC MEANS CLASS produces hierarchical subtotals including
    # grand-total rows (class vars = missing). Verify whether grand-total rows
    # are needed downstream before using groupby alone.
    revenue_summary = (
        revenue_sorted
        .groupby(["SEGMENT_CLEAN", "COUNTRY_CLEAN"], as_index=False)
        .agg(
            N_ROWS=("TOTAL_EUR", "count"),
            MEAN_EUR=("TOTAL_EUR", "mean"),
            SUM_EUR=("TOTAL_EUR", "sum"),
            MIN_EUR=("TOTAL_EUR", "min"),
            MAX_EUR=("TOTAL_EUR", "max"),
        )
    )
    revenue_summary.to_parquet("data/output/revenue_summary.parquet", index=False)
""",
}

# ---------------------------------------------------------------------------
# Migration plan
# ---------------------------------------------------------------------------

BLOCK_PLANS = [
    # ── 01_load_sources.sas ──────────────────────────────────────────
    {
        "block_id": "01_load_sources.sas:4",
        "source_file": "sas/01_load_sources.sas",
        "start_line": 4,
        "end_line": 6,
        "block_type": "PROC_IMPORT",
        "strategy": "translated",
        "risk": "low",
        "rationale": (
            "PROC IMPORT from CSV is directly equivalent to pd.read_csv."
            " Column types may need validation after migration."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.92,
        "confidence_band": "high",
        "input_datasets": ["customers.csv"],
        "output_datasets": ["rawdir.customers"],
    },
    {
        "block_id": "01_load_sources.sas:8",
        "source_file": "sas/01_load_sources.sas",
        "start_line": 8,
        "end_line": 10,
        "block_type": "PROC_IMPORT",
        "strategy": "translated",
        "risk": "low",
        "rationale": "PROC IMPORT from CSV is directly equivalent to pd.read_csv.",
        "estimated_effort": "low",
        "confidence_score": 0.92,
        "confidence_band": "high",
        "input_datasets": ["transactions.csv"],
        "output_datasets": ["rawdir.transactions"],
    },
    {
        "block_id": "01_load_sources.sas:12",
        "source_file": "sas/01_load_sources.sas",
        "start_line": 12,
        "end_line": 14,
        "block_type": "PROC_IMPORT",
        "strategy": "translated",
        "risk": "low",
        "rationale": "PROC IMPORT from CSV is directly equivalent to pd.read_csv.",
        "estimated_effort": "low",
        "confidence_score": 0.92,
        "confidence_band": "high",
        "input_datasets": ["exchange_rates.csv"],
        "output_datasets": ["rawdir.exchange_rates"],
    },
    {
        "block_id": "01_load_sources.sas:16",
        "source_file": "sas/01_load_sources.sas",
        "start_line": 16,
        "end_line": 18,
        "block_type": "PROC_IMPORT",
        "strategy": "translated_with_review",
        "risk": "medium",
        "rationale": (
            "PROC IMPORT from XLSX requires openpyxl."
            " Sheet name 'Sheet1' and column layout should be confirmed against"
            " the actual file before deployment."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.74,
        "confidence_band": "medium",
        "input_datasets": ["products.xlsx"],
        "output_datasets": ["rawdir.products"],
    },
    # ── 02_clean_customers.sas ────────────────────────────────────────
    {
        "block_id": "02_clean_customers.sas:5",
        "source_file": "sas/02_clean_customers.sas",
        "start_line": 5,
        "end_line": 10,
        "block_type": "DATA_STEP",
        "strategy": "translated",
        "risk": "low",
        "rationale": (
            "Straightforward DATA step: row filter on missing key, two string"
            " normalisation columns using %clean_string macro (strip+upcase)."
            " Direct pandas equivalent."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.91,
        "confidence_band": "high",
        "input_datasets": ["rawdir.customers"],
        "output_datasets": ["rawdir.customers_clean"],
    },
    {
        "block_id": "02_clean_customers.sas:12",
        "source_file": "sas/02_clean_customers.sas",
        "start_line": 12,
        "end_line": 12,
        "block_type": "MACRO_CALL",
        "strategy": "translated_with_review",
        "risk": "medium",
        "rationale": (
            "%assert_rowcount aborts the SAS session on failure."
            " The Python equivalent raises AssertionError, which has different"
            " error-propagation behaviour in orchestrated environments."
            " Review error handling strategy."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.69,
        "confidence_band": "medium",
        "input_datasets": ["rawdir.customers_clean"],
        "output_datasets": [],
    },
    # ── 03_clean_transactions.sas ──────────────────────────────────────
    {
        "block_id": "03_clean_transactions.sas:4",
        "source_file": "sas/03_clean_transactions.sas",
        "start_line": 4,
        "end_line": 9,
        "block_type": "DATA_STEP",
        "strategy": "translated",
        "risk": "low",
        "rationale": (
            "Filter on missing CUSTOMER_ID/CURRENCY and non-positive AMOUNT_LOCAL."
            " Straightforward pandas dropna + boolean mask."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.93,
        "confidence_band": "high",
        "input_datasets": ["rawdir.transactions"],
        "output_datasets": ["rawdir.transactions_clean"],
    },
    {
        "block_id": "03_clean_transactions.sas:12",
        "source_file": "sas/03_clean_transactions.sas",
        "start_line": 12,
        "end_line": 12,
        "block_type": "MACRO_CALL",
        "strategy": "translated_with_review",
        "risk": "medium",
        "rationale": (
            "%assert_rowcount aborts the SAS session on failure."
            " Review error handling strategy — same concern as in 02_clean_customers."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.69,
        "confidence_band": "medium",
        "input_datasets": ["rawdir.transactions_clean"],
        "output_datasets": [],
    },
    # ── 04_join_and_aggregate.sas ──────────────────────────────────────
    {
        "block_id": "04_join_and_aggregate.sas:4",
        "source_file": "sas/04_join_and_aggregate.sas",
        "start_line": 4,
        "end_line": 16,
        "block_type": "PROC_SQL",
        "strategy": "translated",
        "risk": "low",
        "rationale": (
            "INNER JOIN on date+currency to FX-convert transaction amounts."
            " DATEPART() and INPUT() date conversions mapped to pd.to_datetime normalization."
            " Translated to pandas merge."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.93,
        "confidence_band": "high",
        "input_datasets": ["rawdir.transactions_clean", "rawdir.exchange_rates"],
        "output_datasets": ["work.tx_fx"],
    },
    {
        "block_id": "04_join_and_aggregate.sas:18",
        "source_file": "sas/04_join_and_aggregate.sas",
        "start_line": 18,
        "end_line": 23,
        "block_type": "PROC_SQL",
        "strategy": "translated",
        "risk": "low",
        "rationale": "LEFT JOIN to add product category. Simple pandas merge with how='left'.",
        "estimated_effort": "low",
        "confidence_score": 0.95,
        "confidence_band": "high",
        "input_datasets": ["work.tx_fx", "rawdir.products"],
        "output_datasets": ["work.tx_fx_cat"],
    },
    {
        "block_id": "04_join_and_aggregate.sas:25",
        "source_file": "sas/04_join_and_aggregate.sas",
        "start_line": 25,
        "end_line": 35,
        "block_type": "PROC_SQL",
        "strategy": "translated",
        "risk": "low",
        "rationale": (
            "GROUP BY aggregation with INNER JOIN."
            " Translated to pandas merge + groupby + sum. Column rename DATE applied."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.91,
        "confidence_band": "high",
        "input_datasets": ["work.tx_fx_cat", "rawdir.customers_clean"],
        "output_datasets": ["outdir.customer_revenue_daily"],
    },
    {
        "block_id": "04_join_and_aggregate.sas:37",
        "source_file": "sas/04_join_and_aggregate.sas",
        "start_line": 37,
        "end_line": 41,
        "block_type": "PROC_SQL",
        "strategy": "translated",
        "risk": "low",
        "rationale": "Simple GROUP BY + ORDER BY aggregation. pandas groupby with sort_values.",
        "estimated_effort": "low",
        "confidence_score": 0.95,
        "confidence_band": "high",
        "input_datasets": ["work.tx_fx_cat"],
        "output_datasets": ["outdir.category_revenue"],
    },
    # ── 05_risk_scoring_iml.sas ────────────────────────────────────────
    {
        "block_id": "05_risk_scoring_iml.sas:3",
        "source_file": "sas/05_risk_scoring_iml.sas",
        "start_line": 3,
        "end_line": 21,
        "block_type": "PROC_IML",
        "strategy": "manual",
        "risk": "high",
        "rationale": (
            "PROC IML is SAS's proprietary matrix language."
            " NumPy reference implementation provided."
            " Validate sample-std (ddof=1) and zero-guard behaviour against"
            " the SAS baseline before using in production."
        ),
        "estimated_effort": "high",
        "confidence_score": 0.0,
        "confidence_band": "low",
        "input_datasets": ["outdir.customer_revenue_daily"],
        "output_datasets": ["outdir.customer_revenue_zscore"],
    },
    # ── 06_summary_stats.sas ──────────────────────────────────────────
    {
        "block_id": "06_summary_stats.sas:3",
        "source_file": "sas/06_summary_stats.sas",
        "start_line": 3,
        "end_line": 6,
        "block_type": "PROC_SORT",
        "strategy": "translated",
        "risk": "low",
        "rationale": "PROC SORT BY two class variables. Direct pandas sort_values equivalent.",
        "estimated_effort": "low",
        "confidence_score": 0.96,
        "confidence_band": "high",
        "input_datasets": ["outdir.customer_revenue_daily"],
        "output_datasets": ["work.revenue_sorted"],
    },
    {
        "block_id": "06_summary_stats.sas:8",
        "source_file": "sas/06_summary_stats.sas",
        "start_line": 8,
        "end_line": 16,
        "block_type": "PROC_MEANS",
        "strategy": "translated_with_review",
        "risk": "medium",
        "rationale": (
            "PROC MEANS with CLASS generates hierarchical subtotals including grand-total rows"
            " where class variables are missing (_TYPE_ column)."
            " The pandas groupby translation omits grand-total rows."
            " Confirm whether downstream consumers require them."
        ),
        "estimated_effort": "medium",
        "confidence_score": 0.72,
        "confidence_band": "medium",
        "input_datasets": ["work.revenue_sorted"],
        "output_datasets": ["outdir.revenue_summary"],
    },
]

LIBNAME_MAP = {
    "rawdir": "data/raw",
    # outdir is intentionally omitted: output tables have no libname so they
    # appear in the ERD (Data Model view) and the "Migration output" sidebar section.
}

DATA_SCHEMA = {
    "data/raw/customers.csv": {
        "columns": ["CUSTOMER_ID", "NAME", "COUNTRY", "SEGMENT", "EMAIL", "IS_ACTIVE"],
        "column_types": {
            "CUSTOMER_ID": "double",
            "NAME": "character",
            "COUNTRY": "character",
            "SEGMENT": "character",
            "EMAIL": "character",
            "IS_ACTIVE": "double",
        },
        "column_labels": {
            "CUSTOMER_ID": "Customer Identifier",
            "NAME": "Full Name",
            "COUNTRY": "ISO Country Code",
            "SEGMENT": "Customer Segment",
            "EMAIL": "Email Address",
            "IS_ACTIVE": "Active Flag (1=active)",
        },
        "column_formats": {
            "CUSTOMER_ID": "8.",
            "IS_ACTIVE": "1.",
        },
        "row_count": 4821,
    },
    "data/raw/transactions.csv": {
        "columns": ["TX_ID", "CUSTOMER_ID", "PRODUCT_ID", "TX_DATE", "AMOUNT_LOCAL", "CURRENCY"],
        "column_types": {
            "TX_ID": "double",
            "CUSTOMER_ID": "double",
            "PRODUCT_ID": "double",
            "TX_DATE": "character",
            "AMOUNT_LOCAL": "double",
            "CURRENCY": "character",
        },
        "column_labels": {
            "TX_ID": "Transaction Identifier",
            "CUSTOMER_ID": "Customer Identifier",
            "PRODUCT_ID": "Product Identifier",
            "TX_DATE": "Transaction Date",
            "AMOUNT_LOCAL": "Amount in Local Currency",
            "CURRENCY": "ISO Currency Code",
        },
        "column_formats": {
            "TX_DATE": "YYMMDD10.",
            "AMOUNT_LOCAL": "12.2",
        },
        "row_count": 52340,
    },
    "data/raw/exchange_rates.csv": {
        "columns": ["DATE", "CURRENCY", "RATE_TO_EUR"],
        "column_types": {
            "DATE": "character",
            "CURRENCY": "character",
            "RATE_TO_EUR": "double",
        },
        "column_labels": {
            "DATE": "Rate Date",
            "CURRENCY": "ISO Currency Code",
            "RATE_TO_EUR": "Exchange Rate to EUR",
        },
        "column_formats": {
            "DATE": "YYMMDD10.",
            "RATE_TO_EUR": "10.6",
        },
        "row_count": 1826,
    },
    "data/raw/products.xlsx": {
        "columns": ["PRODUCT_ID", "NAME", "CATEGORY", "UNIT_PRICE"],
        "column_types": {
            "PRODUCT_ID": "double",
            "NAME": "character",
            "CATEGORY": "character",
            "UNIT_PRICE": "double",
        },
        "column_labels": {
            "PRODUCT_ID": "Product Identifier",
            "NAME": "Product Name",
            "CATEGORY": "Product Category",
            "UNIT_PRICE": "Unit Price (EUR)",
        },
        "column_formats": {
            "UNIT_PRICE": "10.2",
        },
        "row_count": 248,
    },
    "data/raw/customers_clean.parquet": {
        "columns": [
            "CUSTOMER_ID",
            "NAME",
            "COUNTRY",
            "SEGMENT",
            "EMAIL",
            "IS_ACTIVE",
            "COUNTRY_CLEAN",
            "SEGMENT_CLEAN",
        ],
        "column_types": {
            "CUSTOMER_ID": "double",
            "NAME": "character",
            "COUNTRY": "character",
            "SEGMENT": "character",
            "EMAIL": "character",
            "IS_ACTIVE": "double",
            "COUNTRY_CLEAN": "character",
            "SEGMENT_CLEAN": "character",
        },
        "column_labels": {
            "COUNTRY_CLEAN": "Normalised Country (stripped, uppercased)",
            "SEGMENT_CLEAN": "Normalised Segment (stripped, uppercased)",
        },
        "column_formats": {},
        "row_count": 4793,
    },
    "data/raw/transactions_clean.parquet": {
        "columns": ["TX_ID", "CUSTOMER_ID", "PRODUCT_ID", "TX_DATE", "AMOUNT_LOCAL", "CURRENCY"],
        "column_types": {
            "TX_ID": "double",
            "CUSTOMER_ID": "double",
            "PRODUCT_ID": "double",
            "TX_DATE": "character",
            "AMOUNT_LOCAL": "double",
            "CURRENCY": "character",
        },
        "column_labels": {},
        "column_formats": {},
        "row_count": 51108,
    },
    "data/output/customer_revenue_daily.parquet": {
        "columns": [
            "CUSTOMER_ID",
            "DATE",
            "TOTAL_EUR",
            "COUNTRY_CLEAN",
            "SEGMENT_CLEAN",
            "IS_ACTIVE",
        ],
        "column_types": {
            "CUSTOMER_ID": "double",
            "DATE": "character",
            "TOTAL_EUR": "double",
            "COUNTRY_CLEAN": "character",
            "SEGMENT_CLEAN": "character",
            "IS_ACTIVE": "double",
        },
        "column_labels": {
            "DATE": "Revenue Date",
            "TOTAL_EUR": "Total Revenue (EUR)",
        },
        "column_formats": {
            "DATE": "YYMMDD10.",
            "TOTAL_EUR": "12.2",
        },
        "row_count": 39874,
    },
    "data/output/category_revenue.parquet": {
        "columns": ["CATEGORY", "TOTAL_EUR"],
        "column_types": {
            "CATEGORY": "character",
            "TOTAL_EUR": "double",
        },
        "column_labels": {
            "TOTAL_EUR": "Total Revenue by Category (EUR)",
        },
        "column_formats": {
            "TOTAL_EUR": "12.2",
        },
        "row_count": 12,
    },
    "data/output/customer_revenue_zscore.parquet": {
        "columns": ["CUSTOMER_ID", "DATE", "TOTAL_EUR", "Z_SCORE"],
        "column_types": {
            "CUSTOMER_ID": "double",
            "DATE": "character",
            "TOTAL_EUR": "double",
            "Z_SCORE": "double",
        },
        "column_labels": {
            "Z_SCORE": "Standardised Revenue Score",
        },
        "column_formats": {
            "TOTAL_EUR": "12.2",
            "Z_SCORE": "8.4",
        },
        "row_count": 39874,
    },
    "data/output/revenue_summary.parquet": {
        "columns": [
            "SEGMENT_CLEAN",
            "COUNTRY_CLEAN",
            "N_ROWS",
            "MEAN_EUR",
            "SUM_EUR",
            "MIN_EUR",
            "MAX_EUR",
        ],
        "column_types": {
            "SEGMENT_CLEAN": "character",
            "COUNTRY_CLEAN": "character",
            "N_ROWS": "double",
            "MEAN_EUR": "double",
            "SUM_EUR": "double",
            "MIN_EUR": "double",
            "MAX_EUR": "double",
        },
        "column_labels": {
            "N_ROWS": "Row Count",
            "MEAN_EUR": "Mean Revenue (EUR)",
            "SUM_EUR": "Total Revenue (EUR)",
            "MIN_EUR": "Minimum Revenue (EUR)",
            "MAX_EUR": "Maximum Revenue (EUR)",
        },
        "column_formats": {
            "MEAN_EUR": "12.2",
            "SUM_EUR": "14.2",
        },
        "row_count": 42,
    },
}

RELATIONSHIPS = [
    # These use dataset_name values (matched by schemaResponseToCanvas against nodeIds)
    {
        "left_table": "customer_revenue_daily",
        "right_table": "customers_clean",
        "key_column": "CUSTOMER_ID",
        "via_block_id": "04_join_and_aggregate.sas:25",
        "relationship_type": "join",
    },
    {
        "left_table": "customer_revenue_zscore",
        "right_table": "customer_revenue_daily",
        "key_column": "CUSTOMER_ID",
        "via_block_id": "05_risk_scoring_iml.sas:3",
        "relationship_type": "merge",
    },
    {
        "left_table": "revenue_summary",
        "right_table": "customer_revenue_daily",
        "key_column": "CUSTOMER_ID",
        "via_block_id": "06_summary_stats.sas:8",
        "relationship_type": "join",
    },
    {
        "left_table": "category_revenue",
        "right_table": "customer_revenue_daily",
        "key_column": "DATE",
        "via_block_id": "04_join_and_aggregate.sas:37",
        "relationship_type": "join",
    },
]

MIGRATION_PLAN = {
    "summary": (
        "Monthly Revenue Pipeline migrates a 6-script SAS ETL into Python/pandas. "
        "The pipeline ingests four source files (CSV + XLSX), cleans and validates "
        "customer and transaction records, converts multi-currency amounts to EUR using "
        "daily exchange rates, aggregates daily revenue per customer, computes z-score "
        "outlier flags via PROC IML, and produces segment/country summary statistics. "
        "10 of 15 blocks are fully auto-translated. PROC IML (risk scoring) requires "
        "manual validation. Four translated_with_review blocks need targeted review: "
        "the XLSX import, two assert_rowcount macro expansions, and the PROC MEANS "
        "hierarchical output."
    ),
    "overall_risk": "medium",
    "risk_explanation": (
        "Medium overall risk. The majority of the pipeline consists of straightforward "
        "SQL joins and DATA step filters. The single high-risk block is PROC IML — "
        "SAS's proprietary matrix language has no direct equivalent; the NumPy "
        "reference implementation must be validated. The four medium-risk blocks "
        "require targeted review but are not blocking."
    ),
    "block_plans": BLOCK_PLANS,
    "recommended_review_blocks": [
        "05_risk_scoring_iml.sas:3",
        "06_summary_stats.sas:8",
        "02_clean_customers.sas:12",
        "03_clean_transactions.sas:12",
    ],
    "cross_file_dependencies": [
        "02_clean_customers.sas depends on macros/clean_string.sas",
        "02_clean_customers.sas depends on macros/assert_rowcount.sas",
        "03_clean_transactions.sas depends on macros/assert_rowcount.sas",
        "04_join_and_aggregate.sas reads rawdir.customers_clean from 02_clean_customers.sas",
        "04_join_and_aggregate.sas reads rawdir.transactions_clean from 03_clean_transactions.sas",
        (
            "05_risk_scoring_iml.sas reads outdir.customer_revenue_daily"
            " from 04_join_and_aggregate.sas"
        ),
        "06_summary_stats.sas reads outdir.customer_revenue_daily from 04_join_and_aggregate.sas",
    ],
    "missing_dependencies": [],
    "sensitive_data_findings": [
        {
            "column": "EMAIL",
            "matched_signal": "email",
            "source_type": "file",
            "source": "data/raw/customers.csv",
        },
        {
            "column": "NAME",
            "matched_signal": "name",
            "source_type": "file",
            "source": "data/raw/customers.csv",
        },
    ],
    "libname_map": LIBNAME_MAP,
    "data_schema": DATA_SCHEMA,
    "relationships": RELATIONSHIPS,
}

# ---------------------------------------------------------------------------
# Lineage
# ---------------------------------------------------------------------------

LINEAGE = {
    "nodes": [
        {
            "id": "01_load_sources.sas:4",
            "label": "PROC IMPORT — customers",
            "source_file": "sas/01_load_sources.sas",
            "block_type": "PROC_IMPORT",
            "status": "migrated",
        },
        {
            "id": "01_load_sources.sas:8",
            "label": "PROC IMPORT — transactions",
            "source_file": "sas/01_load_sources.sas",
            "block_type": "PROC_IMPORT",
            "status": "migrated",
        },
        {
            "id": "01_load_sources.sas:12",
            "label": "PROC IMPORT — exchange_rates",
            "source_file": "sas/01_load_sources.sas",
            "block_type": "PROC_IMPORT",
            "status": "migrated",
        },
        {
            "id": "01_load_sources.sas:16",
            "label": "PROC IMPORT — products (XLSX)",
            "source_file": "sas/01_load_sources.sas",
            "block_type": "PROC_IMPORT",
            "status": "migrated",
        },
        {
            "id": "02_clean_customers.sas:5",
            "label": "DATA customers_clean",
            "source_file": "sas/02_clean_customers.sas",
            "block_type": "DATA_STEP",
            "status": "migrated",
        },
        {
            "id": "02_clean_customers.sas:12",
            "label": "%assert_rowcount (customers_clean)",
            "source_file": "sas/02_clean_customers.sas",
            "block_type": "MACRO_CALL",
            "status": "migrated",
        },
        {
            "id": "03_clean_transactions.sas:4",
            "label": "DATA transactions_clean",
            "source_file": "sas/03_clean_transactions.sas",
            "block_type": "DATA_STEP",
            "status": "migrated",
        },
        {
            "id": "03_clean_transactions.sas:12",
            "label": "%assert_rowcount (transactions_clean)",
            "source_file": "sas/03_clean_transactions.sas",
            "block_type": "MACRO_CALL",
            "status": "migrated",
        },
        {
            "id": "04_join_and_aggregate.sas:4",
            "label": "PROC SQL — FX convert (tx_fx)",
            "source_file": "sas/04_join_and_aggregate.sas",
            "block_type": "PROC_SQL",
            "status": "migrated",
        },
        {
            "id": "04_join_and_aggregate.sas:18",
            "label": "PROC SQL — add category (tx_fx_cat)",
            "source_file": "sas/04_join_and_aggregate.sas",
            "block_type": "PROC_SQL",
            "status": "migrated",
        },
        {
            "id": "04_join_and_aggregate.sas:25",
            "label": "PROC SQL — customer_revenue_daily",
            "source_file": "sas/04_join_and_aggregate.sas",
            "block_type": "PROC_SQL",
            "status": "migrated",
        },
        {
            "id": "04_join_and_aggregate.sas:37",
            "label": "PROC SQL — category_revenue",
            "source_file": "sas/04_join_and_aggregate.sas",
            "block_type": "PROC_SQL",
            "status": "migrated",
        },
        {
            "id": "05_risk_scoring_iml.sas:3",
            "label": "PROC IML — z-score (manual)",
            "source_file": "sas/05_risk_scoring_iml.sas",
            "block_type": "PROC_IML",
            "status": "manual_review",
        },
        {
            "id": "06_summary_stats.sas:3",
            "label": "PROC SORT — by segment, country",
            "source_file": "sas/06_summary_stats.sas",
            "block_type": "PROC_SORT",
            "status": "migrated",
        },
        {
            "id": "06_summary_stats.sas:8",
            "label": "PROC MEANS — revenue_summary",
            "source_file": "sas/06_summary_stats.sas",
            "block_type": "PROC_MEANS",
            "status": "migrated",
        },
    ],
    "edges": [
        {
            "source": "01_load_sources.sas:4",
            "target": "02_clean_customers.sas:5",
            "dataset": "rawdir.customers",
            "inferred": False,
        },
        {
            "source": "01_load_sources.sas:8",
            "target": "03_clean_transactions.sas:4",
            "dataset": "rawdir.transactions",
            "inferred": False,
        },
        {
            "source": "01_load_sources.sas:12",
            "target": "04_join_and_aggregate.sas:4",
            "dataset": "rawdir.exchange_rates",
            "inferred": False,
        },
        {
            "source": "01_load_sources.sas:16",
            "target": "04_join_and_aggregate.sas:18",
            "dataset": "rawdir.products",
            "inferred": False,
        },
        {
            "source": "02_clean_customers.sas:5",
            "target": "02_clean_customers.sas:12",
            "dataset": "rawdir.customers_clean",
            "inferred": False,
        },
        {
            "source": "02_clean_customers.sas:5",
            "target": "04_join_and_aggregate.sas:25",
            "dataset": "rawdir.customers_clean",
            "inferred": False,
        },
        {
            "source": "03_clean_transactions.sas:4",
            "target": "03_clean_transactions.sas:12",
            "dataset": "rawdir.transactions_clean",
            "inferred": False,
        },
        {
            "source": "03_clean_transactions.sas:4",
            "target": "04_join_and_aggregate.sas:4",
            "dataset": "rawdir.transactions_clean",
            "inferred": False,
        },
        {
            "source": "04_join_and_aggregate.sas:4",
            "target": "04_join_and_aggregate.sas:18",
            "dataset": "work.tx_fx",
            "inferred": False,
        },
        {
            "source": "04_join_and_aggregate.sas:18",
            "target": "04_join_and_aggregate.sas:25",
            "dataset": "work.tx_fx_cat",
            "inferred": False,
        },
        {
            "source": "04_join_and_aggregate.sas:18",
            "target": "04_join_and_aggregate.sas:37",
            "dataset": "work.tx_fx_cat",
            "inferred": False,
        },
        {
            "source": "04_join_and_aggregate.sas:25",
            "target": "05_risk_scoring_iml.sas:3",
            "dataset": "outdir.customer_revenue_daily",
            "inferred": False,
        },
        {
            "source": "04_join_and_aggregate.sas:25",
            "target": "06_summary_stats.sas:3",
            "dataset": "outdir.customer_revenue_daily",
            "inferred": False,
        },
        {
            "source": "06_summary_stats.sas:3",
            "target": "06_summary_stats.sas:8",
            "dataset": "work.revenue_sorted",
            "inferred": False,
        },
    ],
    "file_nodes": [
        {"filename": "sas/autoexec.sas", "file_type": "AUTOEXEC", "blocks": [], "status": "OK"},
        {"filename": "macros/clean_string.sas", "file_type": "MACRO", "blocks": [], "status": "OK"},
        {
            "filename": "macros/assert_rowcount.sas",
            "file_type": "MACRO",
            "blocks": [],
            "status": "OK",
        },
        {
            "filename": "sas/01_load_sources.sas",
            "file_type": "PROGRAM",
            "blocks": [
                "01_load_sources.sas:4",
                "01_load_sources.sas:8",
                "01_load_sources.sas:12",
                "01_load_sources.sas:16",
            ],
            "status": "OK",
        },
        {
            "filename": "sas/02_clean_customers.sas",
            "file_type": "PROGRAM",
            "blocks": ["02_clean_customers.sas:5", "02_clean_customers.sas:12"],
            "status": "OK",
        },
        {
            "filename": "sas/03_clean_transactions.sas",
            "file_type": "PROGRAM",
            "blocks": ["03_clean_transactions.sas:4", "03_clean_transactions.sas:12"],
            "status": "OK",
        },
        {
            "filename": "sas/04_join_and_aggregate.sas",
            "file_type": "PROGRAM",
            "blocks": [
                "04_join_and_aggregate.sas:4",
                "04_join_and_aggregate.sas:18",
                "04_join_and_aggregate.sas:25",
                "04_join_and_aggregate.sas:37",
            ],
            "status": "OK",
        },
        {
            "filename": "sas/05_risk_scoring_iml.sas",
            "file_type": "PROGRAM",
            "blocks": ["05_risk_scoring_iml.sas:3"],
            "status": "ERROR_PRONE",
            "status_reason": (
                "PROC IML requires manual migration — no automatic translation available"
            ),
        },
        {
            "filename": "sas/06_summary_stats.sas",
            "file_type": "PROGRAM",
            "blocks": ["06_summary_stats.sas:3", "06_summary_stats.sas:8"],
            "status": "OK",
        },
    ],
    "file_edges": [
        {
            "source_file": "sas/01_load_sources.sas",
            "target_file": "sas/autoexec.sas",
            "reason": "INCLUDE",
            "via_block_id": "01_load_sources.sas:4",
        },
        {
            "source_file": "sas/02_clean_customers.sas",
            "target_file": "sas/autoexec.sas",
            "reason": "INCLUDE",
            "via_block_id": "02_clean_customers.sas:5",
        },
        {
            "source_file": "sas/02_clean_customers.sas",
            "target_file": "macros/clean_string.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "02_clean_customers.sas:5",
        },
        {
            "source_file": "sas/02_clean_customers.sas",
            "target_file": "macros/assert_rowcount.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "02_clean_customers.sas:12",
        },
        {
            "source_file": "sas/03_clean_transactions.sas",
            "target_file": "sas/autoexec.sas",
            "reason": "INCLUDE",
            "via_block_id": "03_clean_transactions.sas:4",
        },
        {
            "source_file": "sas/03_clean_transactions.sas",
            "target_file": "macros/assert_rowcount.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "03_clean_transactions.sas:12",
        },
        {
            "source_file": "sas/04_join_and_aggregate.sas",
            "target_file": "sas/autoexec.sas",
            "reason": "INCLUDE",
            "via_block_id": "04_join_and_aggregate.sas:4",
        },
        {
            "source_file": "sas/05_risk_scoring_iml.sas",
            "target_file": "sas/autoexec.sas",
            "reason": "INCLUDE",
            "via_block_id": "05_risk_scoring_iml.sas:3",
        },
        {
            "source_file": "sas/06_summary_stats.sas",
            "target_file": "sas/autoexec.sas",
            "reason": "INCLUDE",
            "via_block_id": "06_summary_stats.sas:3",
        },
        # Data flow edges
        {
            "source_file": "sas/01_load_sources.sas",
            "target_file": "sas/02_clean_customers.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "01_load_sources.sas:4",
        },
        {
            "source_file": "sas/01_load_sources.sas",
            "target_file": "sas/03_clean_transactions.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "01_load_sources.sas:8",
        },
        {
            "source_file": "sas/01_load_sources.sas",
            "target_file": "sas/04_join_and_aggregate.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "01_load_sources.sas:12",
        },
        {
            "source_file": "sas/02_clean_customers.sas",
            "target_file": "sas/04_join_and_aggregate.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "02_clean_customers.sas:5",
        },
        {
            "source_file": "sas/03_clean_transactions.sas",
            "target_file": "sas/04_join_and_aggregate.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "03_clean_transactions.sas:4",
        },
        {
            "source_file": "sas/04_join_and_aggregate.sas",
            "target_file": "sas/05_risk_scoring_iml.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "04_join_and_aggregate.sas:25",
        },
        {
            "source_file": "sas/04_join_and_aggregate.sas",
            "target_file": "sas/06_summary_stats.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "04_join_and_aggregate.sas:25",
        },
    ],
    "pipeline_steps": [
        {
            "step_id": "step_01",
            "name": "Ingest source data",
            "description": (
                "Import four raw source files — three CSVs (customers, transactions,"
                " exchange rates) and one XLSX (product catalogue) — into the staging area."
            ),
            "files": ["sas/01_load_sources.sas"],
            "blocks": [
                "01_load_sources.sas:4",
                "01_load_sources.sas:8",
                "01_load_sources.sas:12",
                "01_load_sources.sas:16",
            ],
            "inputs": ["customers.csv", "transactions.csv", "exchange_rates.csv", "products.xlsx"],
            "outputs": ["customers", "transactions", "exchange_rates", "products"],
        },
        {
            "step_id": "step_02",
            "name": "Clean and validate",
            "description": (
                "Remove records with missing mandatory keys and invalid amounts."
                " Normalise COUNTRY and SEGMENT to uppercase stripped strings."
                " Assert minimum row counts — pipeline aborts if either clean table is empty."
            ),
            "files": ["sas/02_clean_customers.sas", "sas/03_clean_transactions.sas"],
            "blocks": [
                "02_clean_customers.sas:5",
                "02_clean_customers.sas:12",
                "03_clean_transactions.sas:4",
                "03_clean_transactions.sas:12",
            ],
            "inputs": ["customers", "transactions"],
            "outputs": ["customers_clean", "transactions_clean"],
        },
        {
            "step_id": "step_03",
            "name": "Currency conversion and enrichment",
            "description": (
                "Join transactions with daily exchange rates to compute AMOUNT_EUR."
                " Add product CATEGORY via a second join."
                " Outputs the enriched transaction table used by all downstream aggregations."
            ),
            "files": ["sas/04_join_and_aggregate.sas"],
            "blocks": ["04_join_and_aggregate.sas:4", "04_join_and_aggregate.sas:18"],
            "inputs": ["transactions_clean", "exchange_rates", "products"],
            "outputs": ["tx_fx_cat"],
        },
        {
            "step_id": "step_04",
            "name": "Aggregate customer revenue",
            "description": (
                "Group enriched transactions by customer, date, country, and segment"
                " to produce daily revenue totals."
                " Also compute total revenue by product category."
            ),
            "files": ["sas/04_join_and_aggregate.sas"],
            "blocks": ["04_join_and_aggregate.sas:25", "04_join_and_aggregate.sas:37"],
            "inputs": ["tx_fx_cat", "customers_clean"],
            "outputs": ["customer_revenue_daily", "category_revenue"],
        },
        {
            "step_id": "step_05",
            "name": "Risk scoring (manual)",
            "description": (
                "Compute z-score on daily customer revenue using mean and sample standard"
                " deviation. A zero guard prevents division by zero when all revenues are"
                " identical. This step uses PROC IML and requires manual validation."
            ),
            "files": ["sas/05_risk_scoring_iml.sas"],
            "blocks": ["05_risk_scoring_iml.sas:3"],
            "inputs": ["customer_revenue_daily"],
            "outputs": ["customer_revenue_zscore"],
        },
        {
            "step_id": "step_06",
            "name": "Summary statistics",
            "description": (
                "Sort revenue by segment and country, then produce a summary table of count,"
                " mean, sum, min, and max revenue per segment-country combination."
            ),
            "files": ["sas/06_summary_stats.sas"],
            "blocks": ["06_summary_stats.sas:3", "06_summary_stats.sas:8"],
            "inputs": ["customer_revenue_daily"],
            "outputs": ["revenue_summary"],
        },
    ],
    "block_confidence": {
        "01_load_sources.sas:4": {"confidence": "high", "verified_confidence": "high"},
        "01_load_sources.sas:8": {"confidence": "high", "verified_confidence": "high"},
        "01_load_sources.sas:12": {"confidence": "high", "verified_confidence": "high"},
        "01_load_sources.sas:16": {"confidence": "medium", "verified_confidence": "medium"},
        "02_clean_customers.sas:5": {"confidence": "high", "verified_confidence": "high"},
        "02_clean_customers.sas:12": {"confidence": "medium", "verified_confidence": "medium"},
        "03_clean_transactions.sas:4": {"confidence": "high", "verified_confidence": "high"},
        "03_clean_transactions.sas:12": {"confidence": "medium", "verified_confidence": "medium"},
        "04_join_and_aggregate.sas:4": {"confidence": "high", "verified_confidence": "high"},
        "04_join_and_aggregate.sas:18": {"confidence": "high", "verified_confidence": "high"},
        "04_join_and_aggregate.sas:25": {"confidence": "high", "verified_confidence": "high"},
        "04_join_and_aggregate.sas:37": {"confidence": "high", "verified_confidence": "high"},
        "05_risk_scoring_iml.sas:3": {"confidence": "low", "verified_confidence": None},
        "06_summary_stats.sas:3": {"confidence": "high", "verified_confidence": "high"},
        "06_summary_stats.sas:8": {"confidence": "medium", "verified_confidence": "medium"},
    },
    "cross_file_edges": [
        {
            "source": "04_join_and_aggregate.sas:25",
            "target": "05_risk_scoring_iml.sas:3",
            "dataset": "outdir.customer_revenue_daily",
        },
        {
            "source": "04_join_and_aggregate.sas:25",
            "target": "06_summary_stats.sas:8",
            "dataset": "outdir.customer_revenue_daily",
        },
        {
            "source": "04_join_and_aggregate.sas:37",
            "target": "06_summary_stats.sas:8",
            "dataset": "outdir.category_revenue",
        },
    ],
    "column_flows": [
        {
            "column": "CUSTOMER_ID",
            "source_dataset": "rawdir.customers",
            "target_dataset": "outdir.customer_revenue_daily",
            "via_block_id": "04_join_and_aggregate.sas:25",
        },
        {
            "column": "TOTAL_EUR",
            "source_dataset": "outdir.customer_revenue_daily",
            "target_dataset": "outdir.customer_revenue_zscore",
            "via_block_id": "05_risk_scoring_iml.sas:3",
        },
        {
            "column": "TOTAL_EUR",
            "source_dataset": "outdir.customer_revenue_daily",
            "target_dataset": "outdir.revenue_summary",
            "via_block_id": "06_summary_stats.sas:8",
        },
    ],
    "dataset_summaries": {
        "rawdir.customers": "Raw customer master — 4,821 records",
        "rawdir.transactions": "Raw transaction log — 52,340 records across 12 currencies",
        "rawdir.exchange_rates": "Daily EUR exchange rates — 1,826 date x currency pairs",
        "rawdir.products": "Product catalogue — 248 SKUs across 12 categories",
        "rawdir.customers_clean": "Validated customers — 4,793 records (28 dropped, missing key)",
        "rawdir.transactions_clean": (
            "Validated transactions — 51,108 records (1,232 dropped, bad amount or key)"
        ),
        "outdir.customer_revenue_daily": "Daily revenue per customer in EUR — 39,874 rows",
        "outdir.category_revenue": "Total EUR revenue by product category — 12 rows",
        "outdir.customer_revenue_zscore": "Daily revenue with z-score outlier flag — 39,874 rows",
        "outdir.revenue_summary": "Segment x country revenue summary — 42 rows",
    },
}

# ---------------------------------------------------------------------------
# Block revisions — provide reconciliation_status for each block
# ---------------------------------------------------------------------------


def _block_revisions(job_id: str) -> list[dict[str, object]]:
    """One BlockRevision per block; manual block has no reconciliation."""
    revisions = []
    rev_num = 1
    for bp in BLOCK_PLANS:
        bid = bp["block_id"]
        recon = None if bp["strategy"] == "manual" else "pass"
        revisions.append(
            {
                "id": str(uuid.uuid4()),
                "job_id": job_id,
                "block_id": bid,
                "revision_number": rev_num,
                "python_code": f"# generated code for {bid}",
                "strategy": bp["strategy"],
                "confidence": bp["confidence_band"],
                "uncertainty_notes": [],
                "reconciliation_status": recon,
                "recon_checks": None,
                "trigger": "agent",
                "notes": None,
                "hint": None,
                "diff_vs_previous": None,
            }
        )
        rev_num += 1
    return revisions


# ---------------------------------------------------------------------------
# Seed runner
# ---------------------------------------------------------------------------


async def seed(drop_existing: bool = True) -> None:
    """Insert the demo job and all block revisions into the database.

    Args:
        drop_existing: When True, delete any existing job with DEMO_JOB_ID first.
    """
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    input_hash = hashlib.sha256("\n".join(sorted(SAS_FILES.keys())).encode()).hexdigest()

    now = datetime.now(UTC)

    async with async_session() as session:
        # Remove existing demo job if present
        if drop_existing:
            existing = await session.get(Job, DEMO_JOB_ID)
            if existing is not None:
                await session.delete(existing)
                await session.commit()

        # Insert Job via ORM so JSON columns are handled correctly
        job = Job(
            id=DEMO_JOB_ID,
            status="accepted",
            input_hash=input_hash,
            name=DEMO_JOB_NAME,
            files=SAS_FILES,
            migration_plan=MIGRATION_PLAN,
            lineage=LINEAGE,
            generated_files=GENERATED_FILES,
            python_code=GENERATED_FILES["pipeline.py"],
            report={"non_technical_doc": None},
            llm_model="anthropic:claude-sonnet-4-6",
            skip_llm=False,
            cancellation_requested=False,
            trigger="agent",
            accepted_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        await session.flush()

        # Insert BlockRevisions
        for rev in _block_revisions(DEMO_JOB_ID):
            br = BlockRevision(
                id=rev["id"],
                job_id=rev["job_id"],
                block_id=rev["block_id"],
                revision_number=rev["revision_number"],
                python_code=rev["python_code"],
                strategy=rev["strategy"],
                confidence=rev["confidence"],
                uncertainty_notes=rev["uncertainty_notes"],
                reconciliation_status=rev["reconciliation_status"],
                recon_checks=rev["recon_checks"],
                trigger=rev["trigger"],
                notes=rev["notes"],
                hint=rev["hint"],
                diff_vs_previous=rev["diff_vs_previous"],
                created_at=now,
            )
            session.add(br)

        await session.commit()

    await engine.dispose()

    print(f"✓ Demo job seeded: {DEMO_JOB_ID}")
    print(f"  Name:   {DEMO_JOB_NAME}")
    n_auto = sum(1 for b in BLOCK_PLANS if b["strategy"] == "translated")
    n_review = sum(1 for b in BLOCK_PLANS if b["strategy"] == "translated_with_review")
    n_manual = sum(1 for b in BLOCK_PLANS if b["strategy"] == "manual")
    print(
        f"  Blocks: {len(BLOCK_PLANS)} total — {n_auto} auto, {n_review} review, {n_manual} manual"
    )
    print(f"  Tables: {len(DATA_SCHEMA)} in data model")
    print(f"  Open:   http://localhost:5173/jobs/{DEMO_JOB_ID}")


if __name__ == "__main__":
    asyncio.run(seed())
