#!/usr/bin/env python3
# ruff: noqa: E501
r"""Seed a demo migration job for the FINREP regulatory exposure reporting showcase.

Creates a complete "Regulatory Exposure Reporting (FINREP)" job that demonstrates:
- Clear 5-step ETL lineage (Source Pipeline view)
- Mix of translated, translated_with_review, and manual-review blocks
- Populated data model with input/output tables (Data Storage tab)

Usage:
    DATABASE_URL=postgresql+asyncpg://rosetta:rosetta@localhost:5432/rosetta \
        uv run python scripts/seed_finrep_job.py

    # Or with Docker running:
    uv run python scripts/seed_finrep_job.py
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

DEMO_JOB_ID = "dec0de00-0000-4000-8000-000000000002"
DEMO_JOB_NAME = "Regulatory Exposure Reporting (FINREP)"

# ---------------------------------------------------------------------------
# SAS source files
# ---------------------------------------------------------------------------

SAS_FILES = {
    "autoexec.sas": """\
/* autoexec.sas — Apex Capital Management FinRep batch environment
   Infrastructure: J. Kowalski / Platform Engineering
   Last revised: 2019-04-02
*/
OPTIONS COMPRESS=YES NOFMTERR NOSYMBOLGEN MPRINT NOMLOGIC;
OPTIONS LINESIZE=132 PAGESIZE=MAX CENTER NODATE;

%LET RUN_ENV    = PRD;
%LET BATCH_ROOT = \\\\apx-sas-prod\\data;

LIBNAME RAWLIB  "&BATCH_ROOT.\\raw\\&RUN_DT.";
LIBNAME STAGLIB "&BATCH_ROOT.\\staging";
LIBNAME OUTLIB  "&BATCH_ROOT.\\output\\&RUN_DT.";
LIBNAME FMTLIB  "\\\\apx-sas-prod\\formats";

OPTIONS FMTSEARCH=(FMTLIB WORK);
""",
    "sas/run_all.sas": """\
/* run_all.sas — FinRep Exposure Batch Entry Point
   Apex Capital Management — Fixed Income & Credit
   Owner: D. Sinclair / Batch Infrastructure
   Usage: Submit this file to run the full month-end exposure pipeline.
          Set RUN_DT before submitting (YYYYMMDD format).
*/

OPTIONS MPRINT MLOGIC SYMBOLGEN;   /* left from last debug session — should be removed before UAT */

/* ── Run parameters ── */
%LET RUN_DT = 20241231;

/* Derive period labels from run date */
%m_set_run_period;

/* ── Pipeline steps ── */
%INCLUDE "\\\\apx-sas-prod\\batch\\finrep\\sas\\01_load_positions.sas";
%INCLUDE "\\\\apx-sas-prod\\batch\\finrep\\sas\\02_load_reference.sas";
%INCLUDE "\\\\apx-sas-prod\\batch\\finrep\\sas\\03_enrich_positions.sas";
%INCLUDE "\\\\apx-sas-prod\\batch\\finrep\\sas\\04_aggregate_exposure.sas";
%INCLUDE "\\\\apx-sas-prod\\batch\\finrep\\sas\\05_produce_output.sas";

%PUT NOTE: [run_all] FinRep batch complete. Period: &PERIOD_LABEL.;
""",
    "sas/01_load_positions.sas": """\
/* 01_load_positions.sas
   Load raw position file from network share.
   Author: R. Thornton / Fixed Income Systems  (2017)
   Revised: P. Okafor / FinRep Team (2021) — added load_dttm column
*/

%m_log_step(STEP_NAME=01_load_positions);

/* Read raw CSV using old-school INFILE/INPUT */
/* Note: PROC IMPORT was tried but had issues with the dirty_px column in 2019 */
DATA work.positions_raw;
  INFILE RAWLIB('positions.csv')
    DSD DELIMITER=',' FIRSTOBS=2 MISSOVER TRUNCOVER
    LRECL=500;

  INPUT
    trade_id    : $15.
    pos_dt      : yymmdd8.
    book_cd     : $20.
    desk_cd     : $15.
    instmt_id   : $15.
    qty_nom     : BEST12.
    dirty_px    : BEST12.
    mkt_val_lcy : BEST20.
    ccy_cd      : $3.
    load_dttm   : DATETIME20.
  ;

  FORMAT pos_dt DATE9. load_dttm DATETIME20.;

RUN;

%m_check_obs(DSN=work.positions_raw, CONTEXT=01_load_positions raw read);

/* Filter to current run date only.
   TODO: this should use &RUN_DT. but the date literal was hardcoded in 2020
   and nobody has touched it since. Works fine for December runs. */
DATA work.positions;
  SET work.positions_raw;
  WHERE pos_dt >= '01DEC2024'd;
RUN;

%m_check_obs(DSN=work.positions, CONTEXT=01_load_positions after date filter);

%PUT NOTE: [01_load_positions] Loaded %SYSFUNC(attrn(%SYSFUNC(open(work.positions)),NOBS)) positions.;
""",
    "sas/02_load_reference.sas": """\
/* 02_load_reference.sas
   Load instrument reference data and counterparty master.
   C. Brennan / Reference Data Team  2022-01-15
*/

%m_log_step(STEP_NAME=02_load_reference);

/* Load instrument reference — PROC IMPORT (migrated from INFILE 2022) */
PROC IMPORT
  DATAFILE=RAWLIB('instrument_ref.csv')
  OUT=work.instrument_ref
  DBMS=CSV
  REPLACE;
  GETNAMES=YES;
  GUESSINGROWS=50;
RUN;

%m_check_obs(DSN=work.instrument_ref, CONTEXT=02_load_reference instrument_ref);

/* Counterparty is pre-staged — just assign from staging library */
DATA work.counterparty;
  SET STAGLIB.counterparty;
RUN;

%m_check_obs(DSN=work.counterparty, CONTEXT=02_load_reference counterparty);

%PUT NOTE: [02_load_reference] Instrument ref: %SYSFUNC(attrn(%SYSFUNC(open(work.instrument_ref)),NOBS)) rows.;
%PUT NOTE: [02_load_reference] Counterparty:   %SYSFUNC(attrn(%SYSFUNC(open(work.counterparty)),NOBS)) rows.;
""",
    "sas/03_enrich_positions.sas": """\
/* 03_enrich_positions.sas
   Enrich position records with instrument and counterparty attributes.
   Compute DV01 and EUR-equivalent market value.
   A. Mehta / Quant Analytics  2020-03-15
   Updated 2022-11 to add watchlist_flg join.
*/

%m_log_step(STEP_NAME=03_enrich_positions);

/* Current join: positions + instrument ref + counterparty */
PROC SQL;
  CREATE TABLE work.pos_enriched AS
  SELECT
    /* Position fields */
    p.trade_id,
    p.pos_dt,
    p.book_cd,
    p.desk_cd,
    p.instmt_id,
    p.qty_nom,
    p.dirty_px,
    p.mkt_val_lcy,
    p.ccy_cd,

    /* Instrument attributes */
    i.isin,
    i.issuer_id,
    i.asset_cls_cd,
    i.maturity_dt,
    i.cpn_rt,
    i.ext_rating_cd,
    i.duration,

    /* Counterparty attributes */
    c.cpty_nm,
    c.country_cd,
    c.sector_cd,
    c.int_rating_cd,
    c.watchlist_flg,

    /* DV01: standard fixed-income sensitivity formula */
    (p.qty_nom * i.duration * p.dirty_px / 10000) AS dv01,

    /* EUR-equivalent market value — hardcoded FX rates (legacy, updated quarterly by hand) */
    CASE p.ccy_cd
      WHEN 'EUR' THEN p.mkt_val_lcy * 1.00
      WHEN 'USD' THEN p.mkt_val_lcy * 0.92
      WHEN 'GBP' THEN p.mkt_val_lcy * 1.17
      ELSE             p.mkt_val_lcy * 1.00   /* default to par if ccy unknown */
    END AS mkt_val_eur,

    /* Rating band — applied from format */
    PUT(i.ext_rating_cd, $RATINGBAND.) AS rating_band

  FROM work.positions p
  LEFT JOIN work.instrument_ref i
    ON p.instmt_id = i.instmt_id
  LEFT JOIN work.counterparty c
    ON i.issuer_id = c.issuer_id

  /* Exclude positions with no market value at all (data quality filter) */
  WHERE p.mkt_val_lcy IS NOT MISSING
    AND p.mkt_val_lcy NE .
  ;
QUIT;

%m_check_obs(DSN=work.pos_enriched, CONTEXT=03_enrich_positions after join);

%PUT NOTE: [03_enrich_positions] Enriched position count: %SYSFUNC(attrn(%SYSFUNC(open(work.pos_enriched)),NOBS)).;
""",
    "sas/04_aggregate_exposure.sas": """\
/* 04_aggregate_exposure.sas
   Aggregate enriched positions to desk / asset class / rating band grain.
   Compute running desk totals and pivot rating buckets.
   B. Larsson / Risk Analytics  2018-09-04
   Minor fix 2023-02: corrected RETAIN initialisation for new desk codes.
*/

%m_log_step(STEP_NAME=04_aggregate_exposure);

/* Sort before BY-group processing */
PROC SORT DATA=work.pos_enriched;
  BY desk_cd asset_cls_cd rating_band;
RUN;

/* Running desk totals using RETAIN */
DATA work.pos_enriched_cum;
  SET work.pos_enriched;
  BY desk_cd;

  RETAIN cum_dv01_desk cum_mktval_desk 0;

  IF FIRST.desk_cd THEN DO;
    cum_dv01_desk   = 0;
    cum_mktval_desk = 0;
  END;

  cum_dv01_desk   + dv01;
  cum_mktval_desk + mkt_val_eur;

RUN;

/* Summary aggregation at desk / asset class / rating band grain */
PROC SUMMARY DATA=work.pos_enriched_cum NWAY MISSING;
  CLASS desk_cd asset_cls_cd rating_band;
  VAR qty_nom mkt_val_eur dv01;
  OUTPUT OUT=work.exposure_agg (DROP=_TYPE_ _FREQ_)
    SUM(qty_nom)     = tot_qty_nom
    SUM(mkt_val_eur) = tot_mkt_val_eur
    SUM(dv01)        = tot_dv01
    N(trade_id)      = trade_count
  ;
RUN;

%m_check_obs(DSN=work.exposure_agg, CONTEXT=04_aggregate_exposure PROC SUMMARY);

/* Pivot rating bands across columns for the wide report format */
PROC TRANSPOSE
  DATA=work.exposure_agg
  OUT=work.exposure_pivot (DROP=_NAME_ _LABEL_)
  PREFIX=dv01_
  ;
  BY desk_cd asset_cls_cd;
  ID rating_band;
  VAR tot_dv01;
RUN;

/* Bring back all rating columns and fill missing with zero */
DATA work.exposure_pivot;
  SET work.exposure_pivot;
  ARRAY _dv01cols {*} dv01_: ;
  DO _i = 1 TO DIM(_dv01cols);
    IF _dv01cols{_i} = . THEN _dv01cols{_i} = 0;
  END;
  DROP _i;
RUN;

/* Final summary — rejoin totals to pivot */
PROC SQL;
  CREATE TABLE work.exposure_summary AS
  SELECT
    a.desk_cd,
    a.asset_cls_cd,
    a.rating_band,
    a.tot_qty_nom,
    a.tot_mkt_val_eur,
    a.tot_dv01,
    a.trade_count
  FROM work.exposure_agg a
  ORDER BY a.desk_cd, a.asset_cls_cd, a.rating_band
  ;
QUIT;

%m_check_obs(DSN=work.exposure_summary, CONTEXT=04_aggregate_exposure final);

%PUT NOTE: [04_aggregate_exposure] Summary rows: %SYSFUNC(attrn(%SYSFUNC(open(work.exposure_summary)),NOBS)).;
""",
    "sas/05_produce_output.sas": """\
/* 05_produce_output.sas
   Write final output datasets to output library and export CSV.
   Mixed authorship — originally R. Thornton 2017, updated A. Mehta 2022.
*/

%m_log_step(STEP_NAME=05_produce_output);

/* Write detail dataset to output library */
DATA OUTLIB.pos_enriched;
  SET work.pos_enriched;
RUN;

/* Write summary dataset */
DATA OUTLIB.exposure_summary;
  SET work.exposure_summary;
RUN;

/* Export summary to CSV for downstream consumption */
PROC EXPORT
  DATA=work.exposure_summary
  OUTFILE="\\\\apx-sas-prod\\reports\\&PERIOD_LABEL.\\exposure_summary_&RUN_DT..csv"
  DBMS=CSV
  REPLACE;
RUN;

/* Export enriched positions detail */
PROC EXPORT
  DATA=work.pos_enriched
  OUTFILE="\\\\apx-sas-prod\\reports\\&PERIOD_LABEL.\\pos_enriched_&RUN_DT..csv"
  DBMS=CSV
  REPLACE;
RUN;

/* TODO: remove before prod */
PROC PRINT DATA=work.pos_enriched (OBS=20);
  TITLE "DEBUG: pos_enriched sample — &PERIOD_LABEL.";
  VAR trade_id desk_cd instmt_id qty_nom dirty_px dv01 mkt_val_eur rating_band;
RUN;

%PUT NOTE: [05_produce_output] Output written to OUTLIB and CSV export complete.;
""",
    "macros/m_set_run_period.sas": """\
/* ============================================================
   m_set_run_period.sas
   Derives period labels and date boundaries from RUN_DT.

   Parameters:
     RUN_DT  (global) — run date in YYYYMMDD format

   Outputs (global macro variables):
     PERIOD_LABEL    e.g. "2024-Q4-DEC"
     RUN_DT_SAS      SAS numeric date of RUN_DT
     PRIOR_MONTH_END SAS numeric date of prior month-end
     RUN_YEAR        4-digit year
     RUN_MONTH       2-digit month (zero-padded)
   ============================================================ */
%MACRO m_set_run_period;

  %GLOBAL PERIOD_LABEL RUN_DT_SAS PRIOR_MONTH_END RUN_YEAR RUN_MONTH;

  /* Parse RUN_DT into components */
  %LET RUN_YEAR  = %SUBSTR(&RUN_DT., 1, 4);
  %LET RUN_MONTH = %SUBSTR(&RUN_DT., 5, 2);

  /* Convert character date to SAS numeric */
  %LET RUN_DT_SAS = %SYSFUNC(inputn(&RUN_DT., yymmdd8.));

  /* Prior month-end via intnx */
  %LET PRIOR_MONTH_END = %SYSFUNC(intnx(MONTH, &RUN_DT_SAS., -1, END));

  /* Quarter label */
  %LET _QTR = %SYSFUNC(qtr(&RUN_DT_SAS.));
  %LET PERIOD_LABEL = &RUN_YEAR.-Q&_QTR.-%SYSFUNC(upcase(%SYSFUNC(putn(&RUN_DT_SAS., monname3.))));

  %PUT NOTE: [m_set_run_period] RUN_DT=&RUN_DT. LABEL=&PERIOD_LABEL. PRIOR_END=&PRIOR_MONTH_END.;

%MEND m_set_run_period;
""",
    "macros/m_log_step.sas": """\
/* ====================================================================
   m_log_step.sas
   Utility macro to write a step name and timestamp to the SAS log
   and also to the batch log file on the network share.

   How to use:
     %m_log_step(STEP_NAME=01_load_positions)

   Parameters:
     STEP_NAME = the name of the current step being executed

   Notes:
     - This macro is called at the start of every pipeline script.
     - The log file path is hardcoded to the prod log server.
       If you need to change it, talk to Platform Engineering.
     - Do NOT call this macro inside a DATA step or PROC SQL block.
       It must be called at the top level of your SAS program.
   ==================================================================== */

%MACRO m_log_step(STEP_NAME=);

  /* Get the current date and time as a formatted string */
  %LET _NOW = %SYSFUNC(datetime(), datetime20.);

  /* Write the step name and timestamp to the SAS log */
  %PUT NOTE: ============================================================;
  %PUT NOTE: STEP START : &STEP_NAME.;
  %PUT NOTE: TIMESTAMP  : &_NOW.;
  %PUT NOTE: RUN DATE   : &RUN_DT.;
  %PUT NOTE: ============================================================;

  /* Also write to the shared batch log file (hardcoded path) */
  /* Note: This will fail if the network share is unavailable */
  DATA _NULL_;
    FILE "\\\\apx-sas-prod\\logs\\finrep.log" MOD;
    PUT "STEP=&STEP_NAME. TS=&_NOW. RUN_DT=&RUN_DT.";
  RUN;

%MEND m_log_step;
""",
    "macros/m_check_obs.sas": """\
/* m_check_obs.sas — Warn if a dataset is empty.
   Known limitation: does not work correctly on views;
   NOBS returns 0 for all views regardless of content. */
%MACRO m_check_obs(DSN=, CONTEXT=);
  %LOCAL _NOBS _DSID _RC;
  %LET _DSID = %SYSFUNC(open(&DSN.));
  %LET _NOBS = %SYSFUNC(attrn(&_DSID., NOBS));
  %LET _RC   = %SYSFUNC(close(&_DSID.));
  %IF &_NOBS. = 0 %THEN %DO;
    %PUT WARNING: [m_check_obs] &DSN. has 0 observations. Context: &CONTEXT.;
  %END;
%MEND m_check_obs;
""",
    "formats/finrep_formats.sas": """\
/* finrep_formats.sas — FinRep value formats for Apex Capital
   Standard PROC FORMAT definitions for regulatory exposure reporting.
*/
PROC FORMAT LIBRARY=FMTLIB;

  /* External rating to rating band */
  VALUE $RATINGBAND
    'AAA', 'AA'        = 'IG_PRIME'
    'A', 'BBB'         = 'IG_STANDARD'
    'SUB_IG'           = 'NON_IG'
    'NR'               = 'UNRATED'
    OTHER              = 'UNKNOWN'
  ;

  /* Asset class display labels */
  VALUE $ASSETLBL
    'CORP'    = 'Corporate Bond'
    'SVRN'    = 'Sovereign'
    'ABS'     = 'Asset-Backed Security'
    'CVRDBND' = 'Covered Bond'
    OTHER     = 'Other'
  ;

  /* Desk display names */
  VALUE $DESKLBL
    'DESK-IG' = 'Investment Grade'
    'DESK-HY' = 'High Yield'
    'DESK-EM' = 'Emerging Markets'
    OTHER     = 'Other'
  ;

  /* DV01 risk bucket — range-based */
  VALUE DV01BUCK
    LOW   -< 1000   = 'MICRO'
    1000  -< 10000  = 'SMALL'
    10000 -< 100000 = 'MEDIUM'
    100000 - HIGH   = 'LARGE'
    OTHER           = 'UNKNOWN'
  ;

  /* Sector labels for counterparty */
  VALUE $SECTORLBL
    'FINAN' = 'Financial Institution'
    'CORP'  = 'Corporate'
    'SOVGN' = 'Sovereign / Supranational'
    'SUPRA' = 'Supranational'
    OTHER   = 'Other'
  ;

RUN;
""",
}

# ---------------------------------------------------------------------------
# Generated Python files
# ---------------------------------------------------------------------------

GENERATED_FILES = {
    "pipeline.py": """\
\"\"\"Regulatory Exposure Reporting (FINREP) — generated by Rosetta Decode.\"\"\"
# Run each step in order.
# Review step_03_enrich_positions.py (hardcoded FX rates) and
# step_04_aggregate_exposure.py (RETAIN + PROC TRANSPOSE pattern) before production.
import step_01_load_positions
import step_02_load_reference
import step_03_enrich_positions   # REVIEW — hardcoded FX rates
import step_04_aggregate_exposure  # REVIEW — RETAIN + PROC TRANSPOSE
import step_05_produce_output


def run() -> None:
    step_01_load_positions.run()
    step_02_load_reference.run()
    step_03_enrich_positions.run()
    step_04_aggregate_exposure.run()
    step_05_produce_output.run()


if __name__ == "__main__":
    run()
""",
    "step_01_load_positions.py": """\
\"\"\"Step 1: ingest raw positions CSV using INFILE/INPUT equivalent.\"\"\"
import pandas as pd


# Column dtypes matching INFILE/INPUT specification
_DTYPES = {
    "trade_id": str,
    "book_cd": str,
    "desk_cd": str,
    "instmt_id": str,
    "ccy_cd": str,
}


def run() -> None:
    # SAS: sas/01_load_positions.sas:11
    # REVIEW REQUIRED: SAS INFILE uses YYMMDD8. for pos_dt and DATETIME20. for load_dttm;
    # confirm parse formats against actual file before deployment.
    positions_raw = pd.read_csv(
        "data/raw/positions.csv",
        dtype=_DTYPES,
        parse_dates=["pos_dt", "load_dttm"],
    )
    positions_raw.to_parquet("data/staging/positions_raw.parquet", index=False)

    # SAS: sas/01_load_positions.sas:39 — hardcoded date filter
    # REVIEW REQUIRED: SAS code uses hardcoded '01DEC2024'd — should be driven by RUN_DT.
    # The pandas filter below preserves the same literal boundary.
    cutoff = pd.Timestamp("2024-12-01")
    positions = positions_raw[positions_raw["pos_dt"] >= cutoff].copy()
    positions.to_parquet("data/staging/positions.parquet", index=False)
""",
    "step_02_load_reference.py": """\
\"\"\"Step 2: load instrument reference and counterparty master.\"\"\"
import pandas as pd


def run() -> None:
    # SAS: sas/02_load_reference.sas:9 — PROC IMPORT for instrument reference
    instrument_ref = pd.read_csv("data/raw/instrument_ref.csv")
    instrument_ref.to_parquet("data/staging/instrument_ref.parquet", index=False)

    # SAS: sas/02_load_reference.sas:39 — counterparty pre-staged in STAGLIB
    counterparty = pd.read_csv("data/staging/counterparty.csv")
    counterparty.to_parquet("data/staging/counterparty.parquet", index=False)
""",
    "step_03_enrich_positions.py": """\
\"\"\"Step 3: enrich positions with instrument/counterparty attrs; compute DV01 and mkt_val_eur.\"\"\"
# ============================================================
# REVIEW REQUIRED — hardcoded FX rates
# ============================================================
# The original SAS uses quarterly hard-coded rates (EUR=1.00, USD=0.92, GBP=1.17).
# These are deliberately NOT replaced with live FX in this translation;
# the business must decide whether to use live rates before production.
# ============================================================
import pandas as pd

# SAS: sas/03_enrich_positions.sas:60 — hardcoded FX rates (legacy quarterly constants)
_FX_TO_EUR: dict[str, float] = {
    "EUR": 1.00,
    "USD": 0.92,
    "GBP": 1.17,
}

# SAS: formats/finrep_formats.sas — $RATINGBAND format
_RATING_BAND: dict[str, str] = {
    "AAA": "IG_PRIME",
    "AA": "IG_PRIME",
    "A": "IG_STANDARD",
    "BBB": "IG_STANDARD",
    "SUB_IG": "NON_IG",
    "NR": "UNRATED",
}


def _apply_rating_band(rating: str) -> str:
    # SAS: sas/03_enrich_positions.sas:68 — PUT(i.ext_rating_cd, $RATINGBAND.)
    return _RATING_BAND.get(str(rating), "UNKNOWN")


def run() -> None:
    # SAS: sas/03_enrich_positions.sas:26 — PROC SQL multi-join
    positions = pd.read_parquet("data/staging/positions.parquet")
    instrument_ref = pd.read_parquet("data/staging/instrument_ref.parquet")
    counterparty = pd.read_parquet("data/staging/counterparty.parquet")

    # Filter: exclude rows with no market value (SAS WHERE clause)
    positions = positions.dropna(subset=["mkt_val_lcy"])
    positions = positions[positions["mkt_val_lcy"] != 0]

    # LEFT JOIN positions → instrument_ref on instmt_id
    pos_enr = positions.merge(instrument_ref, on="instmt_id", how="left")

    # LEFT JOIN → counterparty on issuer_id
    pos_enr = pos_enr.merge(counterparty, on="issuer_id", how="left")

    # DV01: qty_nom * duration * dirty_px / 10000
    pos_enr["dv01"] = pos_enr["qty_nom"] * pos_enr["duration"] * pos_enr["dirty_px"] / 10000

    # EUR-equivalent market value via hardcoded FX map
    pos_enr["mkt_val_eur"] = pos_enr.apply(
        lambda r: r["mkt_val_lcy"] * _FX_TO_EUR.get(str(r["ccy_cd"]), 1.00),
        axis=1,
    )

    # Rating band from $RATINGBAND format
    pos_enr["rating_band"] = pos_enr["ext_rating_cd"].apply(_apply_rating_band)

    pos_enr.to_parquet("data/staging/pos_enriched.parquet", index=False)
""",
    "step_04_aggregate_exposure.py": """\
\"\"\"Step 4: aggregate exposure by desk/asset class/rating band using RETAIN + PROC SUMMARY.\"\"\"
# ============================================================
# REVIEW REQUIRED — RETAIN running totals and PROC TRANSPOSE
# ============================================================
# SAS RETAIN computes cumulative desk totals within a BY group.
# The pandas equivalent uses groupby cumsum — verify that sort order
# matches the SAS PROC SORT (BY desk_cd asset_cls_cd rating_band) before
# comparing outputs.
#
# PROC TRANSPOSE pivots rating_band → columns.  The translation uses
# pivot_table which drops combinations with no data; the SAS code fills
# missing DV01 columns with zero.  Confirm whether downstream consumers
# require the pivoted wide format.
# ============================================================
import pandas as pd


def run() -> None:
    pos_enriched = pd.read_parquet("data/staging/pos_enriched.parquet")

    # SAS: sas/04_aggregate_exposure.sas:11 — PROC SORT
    pos_sorted = pos_enriched.sort_values(["desk_cd", "asset_cls_cd", "rating_band"])

    # SAS: sas/04_aggregate_exposure.sas:16 — DATA step RETAIN cum_dv01_desk / cum_mktval_desk
    pos_sorted = pos_sorted.copy()
    pos_sorted["cum_dv01_desk"] = (
        pos_sorted.groupby("desk_cd")["dv01"].cumsum()
    )
    pos_sorted["cum_mktval_desk"] = (
        pos_sorted.groupby("desk_cd")["mkt_val_eur"].cumsum()
    )
    pos_sorted.to_parquet("data/staging/pos_enriched_cum.parquet", index=False)

    # SAS: sas/04_aggregate_exposure.sas:33 — PROC SUMMARY NWAY
    exposure_agg = (
        pos_sorted
        .groupby(["desk_cd", "asset_cls_cd", "rating_band"], as_index=False)
        .agg(
            tot_qty_nom=("qty_nom", "sum"),
            tot_mkt_val_eur=("mkt_val_eur", "sum"),
            tot_dv01=("dv01", "sum"),
            trade_count=("trade_id", "count"),
        )
    )
    exposure_agg.to_parquet("data/staging/exposure_agg.parquet", index=False)

    # SAS: sas/04_aggregate_exposure.sas:47 — PROC TRANSPOSE (wide pivot, fill 0)
    exposure_pivot = exposure_agg.pivot_table(
        index=["desk_cd", "asset_cls_cd"],
        columns="rating_band",
        values="tot_dv01",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    exposure_pivot.columns = [
        f"dv01_{c}" if c not in ("desk_cd", "asset_cls_cd") else c
        for c in exposure_pivot.columns
    ]
    exposure_pivot.to_parquet("data/staging/exposure_pivot.parquet", index=False)

    # SAS: sas/04_aggregate_exposure.sas:68 — final PROC SQL summary ordered
    exposure_summary = exposure_agg.sort_values(
        ["desk_cd", "asset_cls_cd", "rating_band"]
    ).reset_index(drop=True)
    exposure_summary.to_parquet("data/output/exposure_summary.parquet", index=False)
""",
    "step_05_produce_output.py": """\
\"\"\"Step 5: write output datasets and export CSVs for downstream submission.\"\"\"
import pandas as pd


def run() -> None:
    # SAS: sas/05_produce_output.sas:9 — DATA OUTLIB.pos_enriched
    pos_enriched = pd.read_parquet("data/staging/pos_enriched.parquet")
    pos_enriched.to_parquet("data/output/pos_enriched.parquet", index=False)

    # SAS: sas/05_produce_output.sas:14 — DATA OUTLIB.exposure_summary
    exposure_summary = pd.read_parquet("data/output/exposure_summary.parquet")

    # SAS: sas/05_produce_output.sas:19 — PROC EXPORT exposure_summary
    exposure_summary.to_csv("data/output/exposure_summary_20241231.csv", index=False)

    # SAS: sas/05_produce_output.sas:27 — PROC EXPORT pos_enriched
    pos_enriched.to_csv("data/output/pos_enriched_20241231.csv", index=False)

    # NOTE: SAS code contains an orphaned PROC PRINT (OBS=20) for debug output.
    # That has been intentionally omitted from the Python translation.
""",
}

# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

PIPELINE_STEPS = [
    {
        "step_id": "step_01",
        "label": "Load positions",
        "source_file": "sas/01_load_positions.sas",
        "inputs": ["positions.csv"],
        "outputs": ["positions_raw", "positions"],
    },
    {
        "step_id": "step_02",
        "label": "Load reference data",
        "source_file": "sas/02_load_reference.sas",
        "inputs": ["instrument_ref.csv", "counterparty.csv"],
        "outputs": ["instrument_ref", "counterparty"],
    },
    {
        "step_id": "step_03",
        "label": "Enrich positions",
        "source_file": "sas/03_enrich_positions.sas",
        "inputs": ["positions", "instrument_ref", "counterparty"],
        "outputs": ["pos_enriched"],
    },
    {
        "step_id": "step_04",
        "label": "Aggregate exposure",
        "source_file": "sas/04_aggregate_exposure.sas",
        "inputs": ["pos_enriched"],
        "outputs": ["pos_enriched_cum", "exposure_agg", "exposure_pivot", "exposure_summary"],
    },
    {
        "step_id": "step_05",
        "label": "Produce output",
        "source_file": "sas/05_produce_output.sas",
        "inputs": ["pos_enriched", "exposure_summary"],
        "outputs": ["pos_enriched", "exposure_summary"],
    },
]

# ---------------------------------------------------------------------------
# Block plans
# ---------------------------------------------------------------------------

BLOCK_PLANS = [
    # ── 01_load_positions.sas ────────────────────────────────────────────
    {
        "id": str(uuid.UUID("dec0de02-0001-4000-8000-000000000001")),
        "block_id": "01_load_positions",
        "source_file": "sas/01_load_positions.sas",
        "start_line": 11,
        "end_line": 43,
        "block_type": "DATA_STEP",
        "strategy": "translated",
        "risk": "low",
        "rationale": (
            "INFILE/INPUT raw CSV read with column type declarations and FIRSTOBS=2 skip-header."
            " Translated to pd.read_csv with explicit dtype map."
            " The hardcoded date filter ('01DEC2024'd) is flagged with a REVIEW comment"
            " so the analyst knows it should be driven by a run-date parameter."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.95,
        "confidence_band": "high",
        "input_datasets": ["positions.csv"],
        "output_datasets": ["work.positions_raw", "work.positions"],
    },
    # ── 02_load_reference.sas ─────────────────────────────────────────────
    {
        "id": str(uuid.UUID("dec0de02-0001-4000-8000-000000000002")),
        "block_id": "02_load_reference",
        "source_file": "sas/02_load_reference.sas",
        "start_line": 9,
        "end_line": 43,
        "block_type": "PROC_IMPORT",
        "strategy": "translated",
        "risk": "low",
        "rationale": (
            "PROC IMPORT from CSV maps directly to pd.read_csv."
            " The STAGLIB.counterparty DATA step copy maps to pd.read_csv from the staging path."
            " Both are straightforward translations with no ambiguity."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.92,
        "confidence_band": "high",
        "input_datasets": ["instrument_ref.csv", "STAGLIB.counterparty"],
        "output_datasets": ["work.instrument_ref", "work.counterparty"],
    },
    # ── 03_enrich_positions.sas ───────────────────────────────────────────
    {
        "id": str(uuid.UUID("dec0de02-0001-4000-8000-000000000003")),
        "block_id": "03_enrich_positions",
        "source_file": "sas/03_enrich_positions.sas",
        "start_line": 26,
        "end_line": 80,
        "block_type": "PROC_SQL",
        "strategy": "translated_with_review",
        "risk": "medium",
        "rationale": (
            "PROC SQL multi-join across three tables (positions, instrument_ref, counterparty)"
            " with computed columns: DV01 formula and hardcoded FX-rate CASE expression."
            " The $RATINGBAND format lookup is re-implemented as a Python dict."
            " Translation is mechanically correct but the hardcoded FX rates (EUR/USD/GBP)"
            " are a known legacy smell — the business must decide whether to replace them"
            " with live rates before production deployment."
        ),
        "estimated_effort": "medium",
        "confidence_score": 0.78,
        "confidence_band": "medium",
        "input_datasets": ["work.positions", "work.instrument_ref", "work.counterparty"],
        "output_datasets": ["work.pos_enriched"],
    },
    # ── 04_aggregate_exposure.sas ─────────────────────────────────────────
    {
        "id": str(uuid.UUID("dec0de02-0001-4000-8000-000000000004")),
        "block_id": "04_aggregate_exposure",
        "source_file": "sas/04_aggregate_exposure.sas",
        "start_line": 11,
        "end_line": 82,
        "block_type": "DATA_STEP",
        "strategy": "translated_with_review",
        "risk": "medium",
        "rationale": (
            "Three distinct SAS constructs: PROC SORT + DATA step RETAIN for running desk cumulative"
            " totals + PROC SUMMARY for group aggregation + PROC TRANSPOSE for wide pivot."
            " RETAIN running totals translated to pandas groupby cumsum — sort order must be"
            " verified against SAS PROC SORT to guarantee identical cumulative values."
            " PROC TRANSPOSE with fill-zero logic maps to pivot_table with fill_value=0,"
            " but column ordering may differ; validate against golden output."
        ),
        "estimated_effort": "medium",
        "confidence_score": 0.72,
        "confidence_band": "medium",
        "input_datasets": ["work.pos_enriched"],
        "output_datasets": [
            "work.pos_enriched_cum",
            "work.exposure_agg",
            "work.exposure_pivot",
            "work.exposure_summary",
        ],
    },
    # ── 05_produce_output.sas ─────────────────────────────────────────────
    {
        "id": str(uuid.UUID("dec0de02-0001-4000-8000-000000000005")),
        "block_id": "05_produce_output",
        "source_file": "sas/05_produce_output.sas",
        "start_line": 8,
        "end_line": 38,
        "block_type": "PROC_EXPORT",
        "strategy": "translated",
        "risk": "low",
        "rationale": (
            "DATA step writes to OUTLIB (mapped to parquet output path)."
            " PROC EXPORT to CSV translates directly to DataFrame.to_csv."
            " The orphaned PROC PRINT debug block is omitted from the translation"
            " with an explanatory comment."
            " PERIOD_LABEL global variable dependency (from m_set_run_period macro) is resolved"
            " by using the hardcoded run-date suffix in output filenames."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.88,
        "confidence_band": "high",
        "input_datasets": ["work.pos_enriched", "work.exposure_summary"],
        "output_datasets": ["OUTLIB.pos_enriched", "OUTLIB.exposure_summary"],
    },
]

# ---------------------------------------------------------------------------
# Libname map
# ---------------------------------------------------------------------------

LIBNAME_MAP = {
    "rawlib": "data/raw",
    "staglib": "data/staging",
    # outlib is intentionally omitted: output tables have no libname so they
    # appear in the ERD (Data Model view) and the "Migration output" sidebar section.
}

# ---------------------------------------------------------------------------
# Data schema
# ---------------------------------------------------------------------------

DATA_SCHEMA = {
    "data/raw/positions.csv": {
        "columns": [
            "trade_id",
            "pos_dt",
            "book_cd",
            "desk_cd",
            "instmt_id",
            "qty_nom",
            "dirty_px",
            "mkt_val_lcy",
            "ccy_cd",
            "load_dttm",
        ],
        "column_types": {
            "trade_id": "character",
            "pos_dt": "numeric",
            "book_cd": "character",
            "desk_cd": "character",
            "instmt_id": "character",
            "qty_nom": "double",
            "dirty_px": "double",
            "mkt_val_lcy": "double",
            "ccy_cd": "character",
            "load_dttm": "numeric",
        },
        "column_labels": {
            "trade_id": "Trade Identifier",
            "pos_dt": "Position Date",
            "book_cd": "Book Code",
            "desk_cd": "Desk Code",
            "instmt_id": "Instrument Identifier",
            "qty_nom": "Nominal Quantity",
            "dirty_px": "Dirty Price",
            "mkt_val_lcy": "Market Value (Local Currency)",
            "ccy_cd": "Currency Code (ISO 3)",
            "load_dttm": "Load Datetime",
        },
        "column_formats": {
            "pos_dt": "DATE9.",
            "load_dttm": "DATETIME20.",
            "qty_nom": "BEST12.",
            "dirty_px": "BEST12.",
            "mkt_val_lcy": "BEST20.",
        },
        "row_count": 180,  # 181 lines - 1 header
    },
    "data/raw/instrument_ref.csv": {
        "columns": [
            "instmt_id",
            "isin",
            "issuer_id",
            "asset_cls_cd",
            "maturity_dt",
            "cpn_rt",
            "ext_rating_cd",
            "duration",
            "ref_load_dt",
        ],
        "column_types": {
            "instmt_id": "character",
            "isin": "character",
            "issuer_id": "character",
            "asset_cls_cd": "character",
            "maturity_dt": "numeric",
            "cpn_rt": "double",
            "ext_rating_cd": "character",
            "duration": "double",
            "ref_load_dt": "numeric",
        },
        "column_labels": {
            "instmt_id": "Instrument Identifier",
            "isin": "ISIN",
            "issuer_id": "Issuer Identifier",
            "asset_cls_cd": "Asset Class Code",
            "maturity_dt": "Maturity Date",
            "cpn_rt": "Coupon Rate",
            "ext_rating_cd": "External Rating Code",
            "duration": "Modified Duration",
            "ref_load_dt": "Reference Load Date",
        },
        "column_formats": {
            "maturity_dt": "DATE9.",
            "ref_load_dt": "DATE9.",
            "cpn_rt": "BEST8.",
            "duration": "BEST8.",
        },
        "row_count": 60,  # 61 lines - 1 header
    },
    "data/staging/counterparty.csv": {
        "columns": [
            "issuer_id",
            "cpty_nm",
            "country_cd",
            "sector_cd",
            "int_rating_cd",
            "watchlist_flg",
        ],
        "column_types": {
            "issuer_id": "character",
            "cpty_nm": "character",
            "country_cd": "character",
            "sector_cd": "character",
            "int_rating_cd": "double",
            "watchlist_flg": "character",
        },
        "column_labels": {
            "issuer_id": "Issuer Identifier",
            "cpty_nm": "Counterparty Name",
            "country_cd": "ISO Country Code",
            "sector_cd": "Sector Code",
            "int_rating_cd": "Internal Rating Code",
            "watchlist_flg": "Watchlist Flag (Y/N)",
        },
        "column_formats": {
            "watchlist_flg": "$1.",
        },
        "row_count": 40,  # 41 lines - 1 header
    },
    # Output tables — no libname prefix, using dataset name as path
    "pos_enriched": {
        "columns": [
            "trade_id",
            "pos_dt",
            "book_cd",
            "desk_cd",
            "instmt_id",
            "qty_nom",
            "dirty_px",
            "mkt_val_lcy",
            "ccy_cd",
            "isin",
            "issuer_id",
            "asset_cls_cd",
            "maturity_dt",
            "cpn_rt",
            "ext_rating_cd",
            "duration",
            "cpty_nm",
            "country_cd",
            "sector_cd",
            "int_rating_cd",
            "watchlist_flg",
            "dv01",
            "mkt_val_eur",
            "rating_band",
        ],
        "column_types": {
            "trade_id": "character",
            "pos_dt": "numeric",
            "book_cd": "character",
            "desk_cd": "character",
            "instmt_id": "character",
            "qty_nom": "double",
            "dirty_px": "double",
            "mkt_val_lcy": "double",
            "ccy_cd": "character",
            "isin": "character",
            "issuer_id": "character",
            "asset_cls_cd": "character",
            "maturity_dt": "numeric",
            "cpn_rt": "double",
            "ext_rating_cd": "character",
            "duration": "double",
            "cpty_nm": "character",
            "country_cd": "character",
            "sector_cd": "character",
            "int_rating_cd": "double",
            "watchlist_flg": "character",
            "dv01": "double",
            "mkt_val_eur": "double",
            "rating_band": "character",
        },
        "column_labels": {
            "dv01": "DV01 (basis point sensitivity)",
            "mkt_val_eur": "Market Value (EUR equivalent)",
            "rating_band": "Rating Band (from $RATINGBAND format)",
        },
        "column_formats": {},
        "row_count": 165,  # 166 lines - 1 header
    },
    "exposure_summary": {
        "columns": [
            "desk_cd",
            "asset_cls_cd",
            "rating_band",
            "tot_qty_nom",
            "tot_mkt_val_eur",
            "tot_dv01",
            "trade_count",
        ],
        "column_types": {
            "desk_cd": "character",
            "asset_cls_cd": "character",
            "rating_band": "character",
            "tot_qty_nom": "double",
            "tot_mkt_val_eur": "double",
            "tot_dv01": "double",
            "trade_count": "double",
        },
        "column_labels": {
            "desk_cd": "Desk Code",
            "asset_cls_cd": "Asset Class Code",
            "rating_band": "Rating Band",
            "tot_qty_nom": "Total Nominal Quantity",
            "tot_mkt_val_eur": "Total Market Value (EUR)",
            "tot_dv01": "Total DV01",
            "trade_count": "Number of Trades",
        },
        "column_formats": {
            "tot_mkt_val_eur": "20.2",
            "tot_dv01": "16.2",
        },
        "row_count": 42,  # 43 lines - 1 header
    },
}

# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------

RELATIONSHIPS = [
    {
        "left_table": "pos_enriched",
        "right_table": "instrument_ref",
        "key_column": "instmt_id",
        "via_block_id": "03_enrich_positions",
        "relationship_type": "join",
    },
    {
        "left_table": "pos_enriched",
        "right_table": "counterparty",
        "key_column": "issuer_id",
        "via_block_id": "03_enrich_positions",
        "relationship_type": "join",
    },
    {
        "left_table": "exposure_summary",
        "right_table": "pos_enriched",
        "key_column": "desk_cd",
        "via_block_id": "04_aggregate_exposure",
        "relationship_type": "join",
    },
    {
        "left_table": "instrument_ref",
        "right_table": "counterparty",
        "key_column": "issuer_id",
        "via_block_id": "03_enrich_positions",
        "relationship_type": "join",
    },
]

# ---------------------------------------------------------------------------
# Migration plan
# ---------------------------------------------------------------------------

MIGRATION_PLAN = {
    "summary": (
        "Regulatory Exposure Reporting (FINREP) migrates a 5-script SAS batch pipeline into "
        "Python/pandas. The pipeline reads raw position data and reference tables, enriches "
        "positions with instrument and counterparty attributes, computes DV01 and EUR-equivalent "
        "market values using hardcoded FX rates, aggregates exposure to desk/asset-class/rating-band "
        "grain, and exports CSV outputs for regulatory submission. "
        "3 of 5 blocks are auto-translated. The enrich step (PROC SQL multi-join with "
        "hardcoded FX rates) and the aggregate step (RETAIN + PROC SUMMARY + PROC TRANSPOSE) "
        "require targeted review before production use."
    ),
    "overall_risk": "medium",
    "risk_explanation": (
        "Medium overall risk. The load and output steps are straightforward CSV ingestion and "
        "export. The medium-risk blocks are the PROC SQL multi-join with business-logic FX rates "
        "that the team must consciously keep or replace, and the RETAIN + PROC TRANSPOSE aggregate "
        "step where sort-order sensitivity and pivot column ordering must be validated against "
        "the golden output."
    ),
    "block_plans": BLOCK_PLANS,
    "recommended_review_blocks": [
        "03_enrich_positions",
        "04_aggregate_exposure",
    ],
    "cross_file_dependencies": [
        "sas/run_all.sas drives RUN_DT before autoexec.sas LIBNAME expansion (ordering bug)",
        "macros/m_set_run_period.sas sets PERIOD_LABEL global consumed by 05_produce_output.sas",
        "formats/finrep_formats.sas defines $RATINGBAND used in 03_enrich_positions.sas",
        "macros/m_log_step.sas called at the top of every pipeline script",
        "macros/m_check_obs.sas called after each DATA step / PROC output",
        "03_enrich_positions.sas reads work.positions from 01_load_positions.sas",
        "03_enrich_positions.sas reads work.instrument_ref from 02_load_reference.sas",
        "03_enrich_positions.sas reads work.counterparty from 02_load_reference.sas",
        "04_aggregate_exposure.sas reads work.pos_enriched from 03_enrich_positions.sas",
        "05_produce_output.sas reads work.pos_enriched from 03_enrich_positions.sas",
        "05_produce_output.sas reads work.exposure_summary from 04_aggregate_exposure.sas",
    ],
    "missing_dependencies": [],
    "sensitive_data_findings": [
        {
            "column": "cpty_nm",
            "matched_signal": "name",
            "source_type": "file",
            "source": "data/staging/counterparty.csv",
        },
        {
            "column": "issuer_id",
            "matched_signal": "id",
            "source_type": "file",
            "source": "data/staging/counterparty.csv",
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
            "id": "01_load_positions",
            "label": "INFILE/INPUT — positions",
            "source_file": "sas/01_load_positions.sas",
            "block_type": "DATA_STEP",
            "status": "migrated",
        },
        {
            "id": "02_load_reference",
            "label": "PROC IMPORT — instrument_ref + counterparty",
            "source_file": "sas/02_load_reference.sas",
            "block_type": "PROC_IMPORT",
            "status": "migrated",
        },
        {
            "id": "03_enrich_positions",
            "label": "PROC SQL — enrich (3-way join)",
            "source_file": "sas/03_enrich_positions.sas",
            "block_type": "PROC_SQL",
            "status": "needs_review",
        },
        {
            "id": "04_aggregate_exposure",
            "label": "RETAIN + PROC SUMMARY + PROC TRANSPOSE",
            "source_file": "sas/04_aggregate_exposure.sas",
            "block_type": "DATA_STEP",
            "status": "needs_review",
        },
        {
            "id": "05_produce_output",
            "label": "PROC EXPORT — CSV outputs",
            "source_file": "sas/05_produce_output.sas",
            "block_type": "PROC_EXPORT",
            "status": "migrated",
        },
    ],
    "edges": [
        {
            "source": "01_load_positions",
            "target": "03_enrich_positions",
            "dataset": "work.positions",
            "inferred": False,
        },
        {
            "source": "02_load_reference",
            "target": "03_enrich_positions",
            "dataset": "work.instrument_ref",
            "inferred": False,
        },
        {
            "source": "02_load_reference",
            "target": "03_enrich_positions",
            "dataset": "work.counterparty",
            "inferred": False,
        },
        {
            "source": "03_enrich_positions",
            "target": "04_aggregate_exposure",
            "dataset": "work.pos_enriched",
            "inferred": False,
        },
        {
            "source": "03_enrich_positions",
            "target": "05_produce_output",
            "dataset": "work.pos_enriched",
            "inferred": False,
        },
        {
            "source": "04_aggregate_exposure",
            "target": "05_produce_output",
            "dataset": "work.exposure_summary",
            "inferred": False,
        },
    ],
    "pipeline_steps": PIPELINE_STEPS,
}

# ---------------------------------------------------------------------------
# Block revisions — provide reconciliation_status for each block
# ---------------------------------------------------------------------------


def _block_revisions(job_id: str) -> list[dict[str, object]]:
    """One BlockRevision per block; translated_with_review blocks have pass reconciliation."""
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
    """Insert the FINREP demo job and all block revisions into the database.

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

    print(f"Seeded FINREP demo job: {DEMO_JOB_ID}")
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
