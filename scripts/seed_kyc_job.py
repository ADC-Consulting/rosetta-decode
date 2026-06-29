#!/usr/bin/env python3
# ruff: noqa: E501
r"""Seed a demo migration job for the KYC/AML client screening showcase.

Creates a complete "KYC / AML Client Screening" job that demonstrates:
- Clear 6-step compliance pipeline lineage (Source Pipeline view)
- Mix of auto-verified, needs-review, and manual blocks
- Populated data model with 6 tables (Data Storage tab)

Usage:
    DATABASE_URL=postgresql+asyncpg://rosetta:rosetta@localhost:5432/rosetta \
        uv run python scripts/seed_kyc_job.py

    # Or with Docker running:
    uv run python scripts/seed_kyc_job.py
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

DEMO_JOB_ID = "dec0de00-0000-4000-8000-000000000003"
DEMO_JOB_NAME = "KYC / AML Client Screening"

# ---------------------------------------------------------------------------
# SAS source files
# ---------------------------------------------------------------------------

SAS_FILES = {
    "autoexec.sas": """\
/* autoexec.sas — Meridian Asset Partners KYC/AML batch environment
   Platform Engineering / K. Ostrowski
   Last updated: 2020-08-11
*/
OPTIONS COMPRESS=YES NOFMTERR NOSYMBOLGEN MPRINT NOMLOGIC;
OPTIONS LINESIZE=132 PAGESIZE=MAX CENTER NODATE;

%LET AS_OF_DT   = 20241231;
%LET RUN_ENV    = PRD;
%LET BATCH_ROOT = \\mer-sas-prod\\data;

LIBNAME RAWLIB  "&BATCH_ROOT.\\raw\\&AS_OF_DT.";
LIBNAME STAGLIB "&BATCH_ROOT.\\staging";
LIBNAME REFLIB  "&BATCH_ROOT.\\ref";
LIBNAME OUTLIB  "&BATCH_ROOT.\\output\\&AS_OF_DT.";
LIBNAME FMTLIB  "\\\\mer-sas-prod\\formats";

OPTIONS FMTSEARCH=(FMTLIB WORK);
""",
    "macros/m_log_step.sas": """\
/* ====================================================================
   m_log_step.sas
   Utility macro to log a step name and timestamp to the SAS log
   and to the batch log file on the network share.

   How to use:
     %m_log_step(STEP_NAME=01_ingest_clients)

   Parameters:
     STEP_NAME = the name of the current step being executed

   Notes:
     - This macro must be called at the very start of every pipeline step.
     - The log file path (\\\\mer-sas-prod\\logs\\kyc.log) is hardcoded.
       Do not change it without talking to Platform Engineering first.
     - Do NOT call this macro from inside a DATA step or PROC block.
   ==================================================================== */

%MACRO m_log_step(STEP_NAME=);

  /* Get the current datetime as a formatted string */
  %LET _NOW = %SYSFUNC(datetime(), datetime20.);

  /* Write to SAS log */
  %PUT NOTE: ============================================================;
  %PUT NOTE: STEP START : &STEP_NAME.;
  %PUT NOTE: TIMESTAMP  : &_NOW.;
  %PUT NOTE: AS OF DATE : &AS_OF_DT.;
  %PUT NOTE: ============================================================;

  /* Write to shared log file (hardcoded to production server) */
  /* WARNING: This will silently fail if the network share is down */
  DATA _NULL_;
    FILE "\\\\mer-sas-prod\\logs\\kyc.log" MOD;
    PUT "STEP=&STEP_NAME. TS=&_NOW. AS_OF_DT=&AS_OF_DT.";
  RUN;

%MEND m_log_step;
""",
    "macros/m_assert_nonempty.sas": """\
/* m_assert_nonempty.sas — Abort if a critical dataset is empty.
   Known limitation: does not work on views (NOBS = 0 for all views).
   Use only on physical datasets. */
%MACRO m_assert_nonempty(DSN=, CONTEXT=);
  %LOCAL _NOBS _DSID _RC;
  %LET _DSID = %SYSFUNC(open(&DSN.));
  %LET _NOBS = %SYSFUNC(attrn(&_DSID., NOBS));
  %LET _RC   = %SYSFUNC(close(&_DSID.));
  %IF &_NOBS. = 0 %THEN %DO;
    %PUT ERROR: [m_assert_nonempty] &DSN. is empty — aborting. Context: &CONTEXT.;
    %ABORT CANCEL;
  %END;
%MEND m_assert_nonempty;
""",
    "macros/m_set_review_window.sas": """\
/* ============================================================
   m_set_review_window.sas
   Derives review-due cutoff dates per CRR band from AS_OF_DT.

   Parameters:
     AS_OF_DT  (global) — run date in YYYYMMDD format

   Outputs (global macro variables):
     AS_OF_DT_SAS       SAS numeric date of AS_OF_DT
     REVIEW_CUTOFF_HIGH Review due if last review < this (HIGH band = 12mo)
     REVIEW_CUTOFF_MED  Review due if last review < this (MED band = 24mo)
     REVIEW_CUTOFF_LOW  Review due if last review < this (LOW band = 36mo)
   ============================================================ */
%MACRO m_set_review_window;

  %GLOBAL AS_OF_DT_SAS REVIEW_CUTOFF_HIGH REVIEW_CUTOFF_MED REVIEW_CUTOFF_LOW;

  %LET AS_OF_DT_SAS = %SYSFUNC(inputn(&AS_OF_DT., yymmdd8.));

  /* global intentionally — read by 06_build_edd_queue */
  %LET REVIEW_CUTOFF_HIGH = %SYSFUNC(intnx(MONTH, &AS_OF_DT_SAS., -12,  SAME));
  %LET REVIEW_CUTOFF_MED  = %SYSFUNC(intnx(MONTH, &AS_OF_DT_SAS., -24,  SAME));
  %LET REVIEW_CUTOFF_LOW  = %SYSFUNC(intnx(MONTH, &AS_OF_DT_SAS., -36,  SAME));

  %PUT NOTE: [m_set_review_window] AS_OF_DT=&AS_OF_DT. HIGH_CUTOFF=&REVIEW_CUTOFF_HIGH.;

%MEND m_set_review_window;
""",
    "macros/m_screen_pass.sas": """\
/* m_screen_pass.sas
   Parameterised screening macro.
   Runs one pass of name-matching for a given watchlist type.
   Appends results to work.screen_results.
   T. Bergstrom / Financial Crime Technology  2021-06-30
*/

%MACRO m_screen_pass(WL_TYPE=, THRESHOLD=);

  %m_log_step(STEP_NAME=m_screen_pass_&WL_TYPE.);

  /* Set threshold based on watchlist type if not passed explicitly */
  %IF &THRESHOLD. = %THEN %DO;
    %IF &WL_TYPE. = SANCTION %THEN %LET THRESHOLD = 80;
    %ELSE %IF &WL_TYPE. = PEP    %THEN %LET THRESHOLD = 100;
    %ELSE                               %LET THRESHOLD = 120;
  %END;

  /* Screen onboarding records against this watchlist type */
  DATA work.screen_&WL_TYPE.;
    SET work.clients_std;

    /* Load watchlist subset for this type into hash */
    IF _N_ = 1 THEN DO;
      DECLARE HASH hwl(DATASET: "work.watchlist_&WL_TYPE.");
      hwl.DefineKey('wl_id');
      hwl.DefineData('wl_nm', 'wl_cntry_cd', 'list_src_cd');
      hwl.DefineDone();

      DECLARE HITER hwl_iter('hwl');
    END;

    /* Iterate over watchlist entries and score */
    match_flg    = 'N';
    best_wl_id   = '';
    best_sim     = 0;
    match_method = '';

    RC = hwl_iter.First();
    DO WHILE (RC = 0);
      /* Compute generalised edit distance */
      _ged = COMPGED(full_nm_upper, wl_nm, 'LN');
      _lev = COMPLEV(full_nm_upper, wl_nm, 'LN');
      _sdx = (SOUNDEX(full_nm_upper) = SOUNDEX(wl_nm));

      /* Similarity score: lower GED = better match (invert to 0-200 scale) */
      _sim = MAX(0, 200 - _ged);

      IF _sim >= &THRESHOLD. THEN DO;
        IF _sim > best_sim THEN DO;
          best_sim     = _sim;
          best_wl_id   = wl_id;
          match_flg    = 'Y';
          match_method = "COMPGED";
        END;
      END;
      ELSE IF _sdx = 1 AND _lev <= 3 THEN DO;
        IF _sim > best_sim THEN DO;
          best_sim     = _sim;
          best_wl_id   = wl_id;
          match_flg    = 'P';   /* possible match */
          match_method = "SOUNDEX+LEV";
        END;
      END;

      RC = hwl_iter.Next();
    END;

    wl_type_screened = "&WL_TYPE.";
    KEEP cust_id full_nm_upper match_flg best_wl_id best_sim match_method wl_type_screened;
  RUN;

  /* Append this pass to cumulative results */
  PROC APPEND BASE=work.screen_results DATA=work.screen_&WL_TYPE. FORCE;
  RUN;

%MEND m_screen_pass;
""",
    "formats/kyc_formats.sas": """\
/* kyc_formats.sas — KYC/AML value formats for Meridian Asset Partners
*/
PROC FORMAT LIBRARY=FMTLIB;

  /* Country risk tier — INVALUE (numeric input) */
  INVALUE CNTRY_RISK_IN
    'AF', 'IR', 'IQ', 'KP', 'SY', 'YE', 'LY', 'MM', 'SS'  = 5  /* FATF High Risk */
    'PK', 'JO', 'TN', 'NG', 'GH', 'UG', 'ZW', 'ML', 'NI'  = 4  /* Elevated */
    'RU', 'BY', 'CN', 'VN', 'TH', 'BR', 'MX', 'TR', 'ZA'  = 3  /* Medium-High */
    'IN', 'ID', 'PH', 'EG', 'MA', 'SA', 'AE', 'QA', 'KW'  = 2  /* Medium */
    OTHER                                                    = 1  /* Standard */
  ;

  /* Country risk label */
  VALUE $CNTRY_RISK_LBL
    'HIGH'     = 'High Risk Jurisdiction'
    'ELEVATED' = 'Elevated Risk'
    'MEDIUM'   = 'Medium Risk'
    'STANDARD' = 'Standard Risk'
    OTHER      = 'Unknown'
  ;

  /* Customer risk rating band */
  VALUE $CRRBAND
    'HIGH' = 'Enhanced Due Diligence Required'
    'MED'  = 'Standard Due Diligence'
    'LOW'  = 'Simplified Due Diligence'
    OTHER  = 'Unrated'
  ;

  /* Occupation cash-intensity flag */
  VALUE $CASHOCC
    'DEAL', 'GAMB', 'CASI', 'PAWN', 'CURR', 'REAG' = 'Y'
    OTHER                                            = 'N'
  ;

  /* Onboarding channel risk score */
  VALUE $CHNL_RISK
    'INTRO'   = '3'   /* Introduced via third party — highest channel risk */
    'DIGITAL' = '2'   /* Online onboarding — no in-person verification */
    'BRANCH'  = '1'   /* Face-to-face — lowest channel risk */
    OTHER     = '2'
  ;

  /* Source of wealth display labels */
  VALUE $SOWLBL
    'SAL'    = 'Salary / Employment'
    'INHRT'  = 'Inheritance'
    'BUSPRT' = 'Business Profits'
    'INVST'  = 'Investment Returns'
    'OTHR'   = 'Other / Not Stated'
    OTHER    = 'Unknown'
  ;

RUN;
""",
    "sas/01_ingest_clients.sas": """\
/* 01_ingest_clients.sas
   Ingest new/amended client onboarding records from the daily delta file.
   Author: W. Hargreaves / Client Onboarding Systems  2016
   Revised: F. Morel / Financial Crime Tech  2021-03 — added PRX cleansing
*/

%m_log_step(STEP_NAME=01_ingest_clients);

/* Read raw delta using INFILE/INPUT (PROC IMPORT rejected — encoding issues 2016) */
DATA work.clients_raw;
  INFILE RAWLIB('client_onboarding.csv')
    DSD DELIMITER=',' FIRSTOBS=2 MISSOVER TRUNCOVER
    LRECL=1000 ENCODING='UTF-8';

  INPUT
    cust_id          : $15.
    eff_dt           : yymmdd8.
    full_nm          : $100.
    dob              : yymmdd8.
    cntry_resdnc_cd  : $2.
    cntry_ctznshp_cd : $2.
    cust_typ_cd      : $6.
    occ_cd           : $8.
    pep_self_decl_flg: $1.
    src_of_wlth_cd   : $8.
    onbrd_chnl_cd    : $8.
    load_dttm        : DATETIME20.
  ;

  FORMAT eff_dt DATE9. dob DATE9. load_dttm DATETIME20.;

  /* Strip stray punctuation and Unicode noise from name field using regex */
  full_nm_clean = PRXCHANGE('s/[^\\w\\s\\-]//oi', -1, full_nm);
  full_nm_clean = PRXCHANGE('s/\\s+/ /o',        -1, STRIP(full_nm_clean));

RUN;

%m_check_obs(DSN=work.clients_raw);

/* Filter to current delta window.
   TODO: this should use &AS_OF_DT. macro but the literal was hardcoded in 2018
   and nobody has updated it. Works fine for December runs. */
DATA work.clients_delta;
  SET work.clients_raw;
  WHERE eff_dt >= '01DEC2024'd;
RUN;

%m_check_obs(DSN=work.clients_delta);

%PUT NOTE: [01_ingest_clients] Delta records: %SYSFUNC(attrn(%SYSFUNC(open(work.clients_delta)),NOBS)).;

/* Macro defined in macros/m_check_obs.sas */
%MACRO m_check_obs(DSN=);
  /* inline version kept for backward compat — original in macros/ */
  %IF %SYSFUNC(exist(&DSN.)) %THEN %DO;
    %IF %SYSFUNC(attrn(%SYSFUNC(open(&DSN.)),NOBS)) = 0 %THEN
      %PUT WARNING: [01_ingest_clients] &DSN. is empty.;
  %END;
%MEND;
""",
    "sas/02_standardise_identity.sas": """\
/* 02_standardise_identity.sas
   Standardise identity attributes for downstream matching.
   N. Johansson / Data Quality  2020-04-08
*/

%m_log_step(STEP_NAME=02_standardise_identity);

DATA work.clients_std;
  SET work.clients_delta;

  /* Standardise name: upper, compress spaces, remove double-spaces */
  full_nm_upper = UPCASE(COMPRESS(full_nm_clean, , 'S'));

  /* Derive SOUNDEX blocking key for name matching */
  soundex_key = SOUNDEX(full_nm_upper);

  /* Proper-case version for display */
  full_nm_display = PROPCASE(full_nm_clean);

  /* DOB plausibility check — flag implausible dates */
  IF dob > TODAY() THEN DO;
    dob_flag = 'FUTURE';
    %PUT WARNING: [02_standardise_identity] Future DOB found for &cust_id.;
  END;
  ELSE IF (TODAY() - dob) / 365.25 > 120 THEN dob_flag = 'IMPLAUSIBLE';
  ELSE dob_flag = '';

  /* Derive age band */
  IF dob NE . THEN DO;
    _age = INT((TODAY() - dob) / 365.25);
    IF      _age < 25  THEN age_band = 'U25';
    ELSE IF _age < 40  THEN age_band = 'U40';
    ELSE IF _age < 60  THEN age_band = 'U60';
    ELSE                    age_band = 'O60';
  END;
  DROP _age;

RUN;

%m_check_obs(DSN=work.clients_std, CONTEXT=02_standardise_identity);

%PUT NOTE: [02_standardise_identity] Standardised %SYSFUNC(attrn(%SYSFUNC(open(work.clients_std)),NOBS)) records.;
""",
    "sas/03_screen_watchlist.sas": """\
/* 03_screen_watchlist.sas
   Screen onboarding records against the consolidated sanctions / PEP / adverse-media watchlist.
   Uses in-memory hash objects for performance — avoids SQL join overhead at scale.
   T. Bergstrom / Financial Crime Technology  2021-06-30

   Matching approach:
     - Primary: COMPGED (generalised edit distance, language-normalised)
     - Secondary: SOUNDEX + COMPLEV (phonetic blocking + character-level distance)
     - Sanction threshold: 100, PEP threshold: 120, AdvMedia threshold: 150
*/

%m_log_step(STEP_NAME=03_screen_watchlist);

/* v1 SQL screen — replaced by hash 2023-06, kept for audit
PROC SQL;
  CREATE TABLE work.screen_v1 AS
  SELECT
    c.cust_id,
    c.full_nm_upper,
    w.wl_id,
    w.wl_nm,
    COMPGED(c.full_nm_upper, w.wl_nm) AS ged_score
  FROM work.clients_std c
  CROSS JOIN work.watchlist w
  WHERE COMPGED(c.full_nm_upper, w.wl_nm) < 100
  ;
QUIT;
*/

/* Pre-split watchlist by type for hash loading */
DATA work.watchlist_SANCTION work.watchlist_PEP work.watchlist_ADVMEDIA;
  SET work.watchlist_all;
  IF wl_typ_cd = 'SANCTION' THEN OUTPUT work.watchlist_SANCTION;
  ELSE IF wl_typ_cd = 'PEP'     THEN OUTPUT work.watchlist_PEP;
  ELSE IF wl_typ_cd = 'ADVMEDIA' THEN OUTPUT work.watchlist_ADVMEDIA;
RUN;

/* Initialise results accumulator */
DATA work.screen_results;
  LENGTH cust_id $15 full_nm_upper $100 match_flg $1 best_wl_id $15
         best_sim 8 match_method $20 wl_type_screened $10;
  STOP;
RUN;

/* Run screening passes — thresholds set per watchlist type
   Note: SANCTION threshold deliberately set lower (stricter) than PEP */
%m_screen_pass(WL_TYPE=SANCTION,  THRESHOLD=100);  /* strict: any near-match escalated */
%m_screen_pass(WL_TYPE=PEP,       THRESHOLD=120);
%m_screen_pass(WL_TYPE=ADVMEDIA,  THRESHOLD=120);

/* Keep best match per customer across all watchlist types */
PROC SORT DATA=work.screen_results;
  BY cust_id DESCENDING best_sim;
RUN;

DATA work.screen_best;
  SET work.screen_results;
  BY cust_id;
  IF FIRST.cust_id;
RUN;

%m_check_obs(DSN=work.screen_best, CONTEXT=03_screen_watchlist);

%PUT NOTE: [03_screen_watchlist] Screening complete. Matches: %SYSFUNC(attrn(%SYSFUNC(open(work.screen_best)),NOBS)).;
""",
    "sas/04_score_risk.sas": """\
/* 04_score_risk.sas
   Compute composite Customer Risk Rating (CRR) from weighted rules model.
   H. Nakamura / Financial Crime Rules  2019-11-22
   Updated 2023-02: added source-of-wealth factor, revised channel weights.
*/

%m_log_step(STEP_NAME=04_score_risk);

/* Load risk weight parameters from reference library */
DATA work.risk_weights;
  SET REFLIB.risk_weights;
RUN;

%m_assert_nonempty(DSN=work.risk_weights, CONTEXT=04_score_risk risk weights missing);

/* Join screening results back to standardised clients */
DATA work.clients_screened;
  MERGE work.clients_std (IN=a)
        work.screen_best (IN=b KEEP=cust_id match_flg best_wl_id best_sim match_method);
  BY cust_id;
  IF a;

  /* Default screening fields if no match record */
  IF NOT b THEN DO;
    match_flg    = 'N';
    best_wl_id   = '';
    best_sim     = 0;
    match_method = '';
  END;

RUN;

/* Score each client using the rules cascade */
DATA work.clients_scored;
  SET work.clients_screened;

  crr_score = 0;

  /* Factor 1: Country of residence risk */
  _cntry_pts = INPUT(cntry_resdnc_cd, CNTRY_RISK_IN.);
  IF _cntry_pts = . THEN _cntry_pts = 1;
  crr_score + (_cntry_pts * 10);

  /* Factor 2: PEP status — self-declared or screening match */
  IF pep_self_decl_flg = 'Y' THEN DO;
    crr_score + 40;
    pep_flag = 'Y';
  END;
  ELSE IF match_flg IN ('Y', 'P') AND best_sim >= 100 THEN DO;
    crr_score + 30;
    pep_flag = 'P';  /* possible PEP */
  END;
  ELSE pep_flag = 'N';

  /* Factor 3: Sanctions screening result */
  IF match_flg = 'Y' AND match_method = 'COMPGED' THEN crr_score + 50;
  ELSE IF match_flg = 'P' THEN crr_score + 20;

  /* Factor 4: Source of wealth */
  IF src_of_wlth_cd = 'OTHR' THEN crr_score + 15;
  ELSE IF src_of_wlth_cd = 'BUSPRT' THEN crr_score + 10;

  /* Factor 5: Onboarding channel */
  _chnl_pts = INPUT(PUT(onbrd_chnl_cd, $CHNL_RISK.), BEST2.);
  IF _chnl_pts = . THEN _chnl_pts = 2;
  crr_score + (_chnl_pts * 5);

  /* Factor 6: Customer type */
  IF cust_typ_cd IN ('TRUST', 'FUND') THEN crr_score + 20;
  ELSE IF cust_typ_cd = 'CORP' THEN crr_score + 10;

  /* Factor 7: Occupation cash intensity */
  IF PUT(occ_cd, $CASHOCC.) = 'Y' THEN crr_score + 25;

  /* Assign risk band from score */
  IF      crr_score >= 80 THEN crr_band_cd = 'HIGH';
  ELSE IF crr_score >= 40 THEN crr_band_cd = 'MED';
  ELSE                         crr_band_cd = 'LOW';

  DROP _cntry_pts _chnl_pts;

RUN;

%m_check_obs(DSN=work.clients_scored, CONTEXT=04_score_risk);

/* Write scored clients to output */
DATA OUTLIB.client_screened;
  SET work.clients_scored;
RUN;

%PUT NOTE: [04_score_risk] Scoring complete. HIGH band: %SYSFUNC(countw('X')) (approx — check output).;
""",
    "sas/05_maintain_scd.sas": """\
/* 05_maintain_scd.sas
   Maintain SCD Type 2 history on the client master.
   Closes out prior versions for amended clients, inserts new versions.
   P. Hartmann / Data Warehouse  2017-03-14
   NOTE: This step is order-dependent. Run AFTER 04_score_risk.
         The surrogate key (cust_sk) increments from the max existing value.
         If two runs overlap without a clean handoff, duplicates may result.
*/

%m_log_step(STEP_NAME=05_maintain_scd);

/* Load current client master */
DATA work.client_master;
  SET STAGLIB.client_master;
RUN;

%m_assert_nonempty(DSN=work.client_master, CONTEXT=05_maintain_scd master empty);

/* Find max surrogate key in current master */
PROC SQL NOPRINT;
  SELECT MAX(cust_sk) INTO: _MAX_SK TRIMMED
  FROM work.client_master;
QUIT;
%LET _MAX_SK = %EVAL(&_MAX_SK. + 0);

/* Close out existing current records for clients in today's delta */
DATA work.client_master_closed;
  MERGE work.client_master (IN=a)
        work.clients_scored (IN=b KEEP=cust_id RENAME=(cust_id=cust_id));
  BY cust_id;
  IF a;

  /* Close out current record if this customer has a new version today */
  IF b AND curr_flg = 'Y' THEN DO;
    valid_to_dt = INPUT("&AS_OF_DT.", yymmdd8.) - 1;
    curr_flg    = 'N';
  END;

RUN;

/* Insert new versions for amended/new clients */
DATA work.new_versions;
  SET work.clients_scored;

  RETAIN _SK_CTR;
  IF _N_ = 1 THEN _SK_CTR = &_MAX_SK.;
  _SK_CTR + 1;

  cust_sk         = _SK_CTR;
  full_nm_std     = full_nm_display;
  valid_from_dt   = INPUT("&AS_OF_DT.", yymmdd8.);
  valid_to_dt     = INPUT('99991231', yymmdd8.);
  curr_flg        = 'Y';
  last_review_dt  = INPUT("&AS_OF_DT.", yymmdd8.);

  KEEP cust_id cust_sk full_nm_std crr_band_cd crr_score
       valid_from_dt valid_to_dt curr_flg last_review_dt;
  DROP _SK_CTR;
RUN;

/* Combine closed-out history with new versions */
DATA work.client_master_scd;
  SET work.client_master_closed
      work.new_versions;
  BY cust_id;
RUN;

/* Write back to staging library (overwrites) */
DATA STAGLIB.client_master;
  SET work.client_master_scd;
RUN;

DATA OUTLIB.client_master_scd;
  SET work.client_master_scd;
RUN;

%m_check_obs(DSN=work.client_master_scd, CONTEXT=05_maintain_scd final master);

%PUT NOTE: [05_maintain_scd] SCD-2 maintenance complete. Total records: %SYSFUNC(attrn(%SYSFUNC(open(work.client_master_scd)),NOBS)).;
""",
    "sas/06_build_edd_queue.sas": """\
/* 06_build_edd_queue.sas
   Build EDD work queue and produce periodic review report.
   L. Fernandez / Compliance Reporting  2022-09-01
*/

%m_log_step(STEP_NAME=06_build_edd_queue);

/* Identify clients requiring Enhanced Due Diligence */
DATA work.edd_queue;
  SET work.clients_scored;

  /* EDD trigger conditions */
  edd_trigger_high   = (crr_band_cd = 'HIGH');
  edd_trigger_pep    = (pep_flag IN ('Y', 'P'));
  edd_trigger_sanc   = (match_flg = 'Y' AND match_method = 'COMPGED');
  edd_trigger_cntry  = (INPUT(cntry_resdnc_cd, CNTRY_RISK_IN.) >= 4);

  edd_required = (edd_trigger_high OR edd_trigger_pep OR edd_trigger_sanc OR edd_trigger_cntry);

  IF edd_required THEN DO;
    /* Assign case priority */
    IF match_flg = 'Y' AND edd_trigger_sanc THEN case_priority = 1;  /* Sanctions — urgent */
    ELSE IF pep_flag = 'Y'                  THEN case_priority = 2;  /* Confirmed PEP */
    ELSE IF crr_band_cd = 'HIGH'            THEN case_priority = 3;  /* High risk band */
    ELSE                                         case_priority = 4;  /* Other EDD trigger */

    /* Build reason text */
    edd_reason_txt = CATX('; ',
      IFC(edd_trigger_sanc,   'Sanctions near-match', ''),
      IFC(pep_flag = 'Y',     'Confirmed PEP',        ''),
      IFC(pep_flag = 'P',     'Possible PEP',         ''),
      IFC(edd_trigger_high AND NOT edd_trigger_sanc AND pep_flag = 'N',
                              'High CRR score',        ''),
      IFC(edd_trigger_cntry,  'High-risk jurisdiction', '')
    );
    edd_reason_txt = COMPBL(edd_reason_txt);

    OUTPUT;
  END;

RUN;

PROC SORT DATA=work.edd_queue;
  BY case_priority crr_score DESCENDING;
RUN;

/* Write EDD queue to output library */
DATA OUTLIB.edd_work_queue;
  SET work.edd_queue;
RUN;

/* TODO: remove before prod */
PROC PRINT DATA=work.edd_queue (OBS=10);
  TITLE "DEBUG: EDD Queue sample — AS_OF_DT=&AS_OF_DT.";
  VAR cust_id full_nm_display crr_band_cd crr_score case_priority edd_reason_txt;
RUN;

/* Clients past their periodic review due date */
DATA work.review_due;
  SET work.client_master_scd;
  WHERE curr_flg = 'Y';

  /* Compare last_review_dt against band-specific cutoff */
  IF crr_band_cd = 'HIGH' AND last_review_dt < &REVIEW_CUTOFF_HIGH. THEN review_due_flg = 'Y';
  ELSE IF crr_band_cd = 'MED' AND last_review_dt < &REVIEW_CUTOFF_MED. THEN review_due_flg = 'Y';
  ELSE IF crr_band_cd = 'LOW' AND last_review_dt < &REVIEW_CUTOFF_LOW. THEN review_due_flg = 'Y';
  ELSE review_due_flg = 'N';

  IF review_due_flg = 'Y';
RUN;

/* Periodic review report via PROC REPORT + ODS */
ODS RTF FILE="\\\\mer-sas-prod\\reports\\kyc_periodic_review_&AS_OF_DT..rtf"
        STYLE=JOURNAL;

PROC REPORT DATA=work.review_due NOWD HEADLINE;
  TITLE "Meridian Asset Partners — Periodic KYC Review Due Report";
  TITLE2 "As of &AS_OF_DT. — Generated by FinCrime Batch";

  COLUMN cust_id full_nm_std crr_band_cd crr_score last_review_dt;

  DEFINE cust_id        / DISPLAY 'Client ID';
  DEFINE full_nm_std    / DISPLAY 'Client Name';
  DEFINE crr_band_cd    / DISPLAY 'Risk Band';
  DEFINE crr_score      / DISPLAY 'CRR Score' FORMAT=BEST8.;
  DEFINE last_review_dt / DISPLAY 'Last Review' FORMAT=DATE9.;

  COMPUTE crr_band_cd / CHARACTER LENGTH=4;
    IF crr_band_cd = 'HIGH' THEN
      CALL DEFINE(_COL_, 'STYLE', 'STYLE=[BACKGROUND=SALMON]');
  ENDCOMP;

RUN;

ODS RTF CLOSE;

%PUT NOTE: [06_build_edd_queue] EDD queue: %SYSFUNC(attrn(%SYSFUNC(open(work.edd_queue)),NOBS)) cases.;
%PUT NOTE: [06_build_edd_queue] Review due: %SYSFUNC(attrn(%SYSFUNC(open(work.review_due)),NOBS)) clients.;
""",
    "sas/run_all.sas": """\
/* run_all.sas — KYC/AML Nightly Batch Entry Point
   Meridian Asset Partners — Financial Crime Compliance
   Owner: K. Ostrowski / Platform Engineering
   Usage: Set AS_OF_DT and submit this file.
*/

OPTIONS MPRINT MLOGIC SYMBOLGEN;   /* left from last debug session */

/* ── Run parameters ── */
%LET AS_OF_DT = 20241231;

/* Derive review window cutoffs from AS_OF_DT */
%m_set_review_window;

/* ── Pipeline steps ── */
%INCLUDE "\\\\mer-sas-prod\\batch\\kyc\\sas\\01_ingest_clients.sas";
%INCLUDE "\\\\mer-sas-prod\\batch\\kyc\\sas\\02_standardise_identity.sas";
%INCLUDE "\\\\mer-sas-prod\\batch\\kyc\\sas\\03_screen_watchlist.sas";
%INCLUDE "\\\\mer-sas-prod\\batch\\kyc\\sas\\04_score_risk.sas";
%INCLUDE "\\\\mer-sas-prod\\batch\\kyc\\sas\\05_maintain_scd.sas";
%INCLUDE "\\\\mer-sas-prod\\batch\\kyc\\sas\\06_build_edd_queue.sas";

%PUT NOTE: [run_all] KYC/AML batch complete. AS_OF_DT=&AS_OF_DT.;
""",
}

# ---------------------------------------------------------------------------
# Generated Python files
# ---------------------------------------------------------------------------

GENERATED_FILES = {
    "pipeline.py": """\
\"\"\"KYC / AML Client Screening Pipeline — generated by Rosetta Decode.\"\"\"
# Run each step in order. Review steps 03-06 before running in production.
import ingest_clients
import standardise_identity
import screen_watchlist    # REVIEW REQUIRED — DECLARE HASH + fuzzy matching
import score_risk          # REVIEW REQUIRED — rules cascade + MERGE
import maintain_scd        # REVIEW REQUIRED — SCD Type-2 logic
import build_edd_queue     # MANUAL — PROC REPORT + ODS RTF


def run() -> None:
    ingest_clients.run()
    standardise_identity.run()
    screen_watchlist.run()
    score_risk.run()
    maintain_scd.run()
    build_edd_queue.run()


if __name__ == "__main__":
    run()
""",
    "ingest_clients.py": """\
\"\"\"Step 1: ingest daily client onboarding delta from CSV.\"\"\"
import re

import pandas as pd


def run() -> None:
    # SAS: sas/01_ingest_clients.sas:10
    clients_raw = pd.read_csv(
        "data/raw/client_onboarding.csv",
        dtype=str,
        encoding="utf-8",
    )
    clients_raw["eff_dt"] = pd.to_datetime(clients_raw["eff_dt"], format="%Y%m%d")
    clients_raw["dob"] = pd.to_datetime(clients_raw["dob"], format="%Y%m%d", errors="coerce")

    # SAS: sas/01_ingest_clients.sas:33 (PRXCHANGE name cleansing)
    clients_raw["full_nm_clean"] = clients_raw["full_nm"].str.replace(
        r"[^\\w\\s\\-]", "", regex=True
    )
    clients_raw["full_nm_clean"] = clients_raw["full_nm_clean"].str.strip().str.replace(
        r"\\s+", " ", regex=True
    )

    # SAS: sas/01_ingest_clients.sas:44 (hardcoded date filter — known issue)
    # REVIEW REQUIRED: hardcoded '01DEC2024' cutoff; should be parameterised via AS_OF_DT
    cutoff = pd.Timestamp("2024-12-01")
    clients_delta = clients_raw[clients_raw["eff_dt"] >= cutoff].copy()

    clients_delta.to_parquet("data/staging/clients_delta.parquet", index=False)
""",
    "standardise_identity.py": """\
\"\"\"Step 2: standardise identity attributes for downstream name matching.\"\"\"
import pandas as pd


def _soundex(name: str) -> str:
    \"\"\"Basic SOUNDEX implementation matching SAS SOUNDEX() behaviour.\"\"\"
    if not name:
        return ""
    name = name.upper()
    code_map = {
        "B": "1", "F": "1", "P": "1", "V": "1",
        "C": "2", "G": "2", "J": "2", "K": "2", "Q": "2", "S": "2", "X": "2", "Z": "2",
        "D": "3", "T": "3",
        "L": "4",
        "M": "5", "N": "5",
        "R": "6",
    }
    first = name[0]
    coded = first
    prev = code_map.get(first, "0")
    for ch in name[1:]:
        c = code_map.get(ch, "0")
        if c != "0" and c != prev:
            coded += c
        prev = c
    return (coded + "000")[:4]


def run() -> None:
    # SAS: sas/02_standardise_identity.sas:8
    clients = pd.read_parquet("data/staging/clients_delta.parquet")

    # SAS: sas/02_standardise_identity.sas:12 (UPCASE + COMPRESS spaces)
    clients["full_nm_upper"] = clients["full_nm_clean"].str.upper().str.replace(
        r"\\s+", " ", regex=True
    ).str.strip()

    # SAS: sas/02_standardise_identity.sas:15 (SOUNDEX blocking key)
    clients["soundex_key"] = clients["full_nm_upper"].fillna("").apply(_soundex)

    # SAS: sas/02_standardise_identity.sas:18 (PROPCASE display name)
    clients["full_nm_display"] = clients["full_nm_clean"].str.title()

    # SAS: sas/02_standardise_identity.sas:24 (DOB plausibility flags)
    today = pd.Timestamp.today().normalize()
    clients["dob_flag"] = ""
    future_mask = clients["dob"] > today
    old_mask = (today - clients["dob"]).dt.days / 365.25 > 120
    clients.loc[future_mask, "dob_flag"] = "FUTURE"
    clients.loc[old_mask & ~future_mask, "dob_flag"] = "IMPLAUSIBLE"

    # SAS: sas/02_standardise_identity.sas:32 (age band)
    age = ((today - clients["dob"]).dt.days / 365.25).fillna(-1)
    clients["age_band"] = ""
    clients.loc[age >= 0,   "age_band"] = "O60"
    clients.loc[age < 60,   "age_band"] = "U60"
    clients.loc[age < 40,   "age_band"] = "U40"
    clients.loc[age < 25,   "age_band"] = "U25"
    clients.loc[age < 0,    "age_band"] = ""

    clients.to_parquet("data/staging/clients_std.parquet", index=False)
""",
    "screen_watchlist.py": """\
\"\"\"Step 3: screen standardised clients against watchlist using fuzzy name matching.\"\"\"
# ============================================================
# REVIEW REQUIRED — DECLARE HASH + COMPGED / COMPLEV
# ============================================================
# The original SAS uses an in-memory HASH object to load each
# watchlist partition then iterates via HITER, computing:
#   COMPGED (generalised edit distance) — no direct Python equiv.
#   COMPLEV (character-level Levenshtein distance)
#   SOUNDEX phonetic blocking
#
# This translation uses rapidfuzz for edit-distance scoring.
# Validate threshold values (SANCTION=100, PEP/ADVMEDIA=120)
# against the SAS COMPGED scale (0-200 inverted similarity)
# before using in production.
#
# Note: COMPGED threshold drift (100 vs 120 for SANCTION) is
# preserved from the original — see README known issues.
# ============================================================
import pandas as pd

THRESHOLDS = {"SANCTION": 100, "PEP": 120, "ADVMEDIA": 120}


def _screen_pass(
    clients: pd.DataFrame,
    watchlist_subset: pd.DataFrame,
    wl_type: str,
    threshold: int,
) -> pd.DataFrame:
    \"\"\"Run one screening pass for a watchlist type. Returns match rows.\"\"\"
    # SAS: macros/m_screen_pass.sas:20 (DATA work.screen_&WL_TYPE.)
    try:
        from rapidfuzz.distance import Levenshtein
        from rapidfuzz.distance.JaroWinkler import similarity as jw_sim
    except ImportError as exc:
        raise ImportError("rapidfuzz required for watchlist screening") from exc

    records = []
    for _, client in clients.iterrows():
        best_sim = 0.0
        best_wl_id = ""
        match_flg = "N"
        match_method = ""
        cname = str(client["full_nm_upper"])

        for _, wl_row in watchlist_subset.iterrows():
            wname = str(wl_row["wl_nm"])
            # Invert Levenshtein to 0-200 similarity scale (approximates COMPGED)
            max_len = max(len(cname), len(wname), 1)
            lev = Levenshtein.distance(cname, wname)
            sim = max(0.0, 200.0 - (lev / max_len) * 200.0)

            if sim >= threshold:
                if sim > best_sim:
                    best_sim = sim
                    best_wl_id = wl_row["wl_id"]
                    match_flg = "Y"
                    match_method = "COMPGED"
            else:
                # Phonetic fallback (approximates SOUNDEX + COMPLEV <= 3)
                if lev <= 3 and jw_sim(cname, wname) >= 0.85:
                    if sim > best_sim:
                        best_sim = sim
                        best_wl_id = wl_row["wl_id"]
                        match_flg = "P"
                        match_method = "SOUNDEX+LEV"

        records.append({
            "cust_id": client["cust_id"],
            "full_nm_upper": cname,
            "match_flg": match_flg,
            "best_wl_id": best_wl_id,
            "best_sim": best_sim,
            "match_method": match_method,
            "wl_type_screened": wl_type,
        })

    return pd.DataFrame(records)


def run() -> None:
    # SAS: sas/03_screen_watchlist.sas:31
    clients = pd.read_parquet("data/staging/clients_std.parquet")
    watchlist = pd.read_csv("data/raw/watchlist.csv", dtype=str)

    all_results = []
    for wl_type, threshold in THRESHOLDS.items():
        subset = watchlist[watchlist["wl_typ_cd"] == wl_type].copy()
        results = _screen_pass(clients, subset, wl_type, threshold)
        all_results.append(results)

    screen_results = pd.concat(all_results, ignore_index=True)

    # SAS: sas/03_screen_watchlist.sas:52 (keep best match per customer)
    screen_best = (
        screen_results
        .sort_values("best_sim", ascending=False)
        .drop_duplicates(subset="cust_id", keep="first")
    )
    screen_best.to_parquet("data/staging/screen_best.parquet", index=False)
""",
    "score_risk.py": """\
\"\"\"Step 4: compute composite Customer Risk Rating (CRR) using rules cascade.\"\"\"
# ============================================================
# REVIEW REQUIRED — rules cascade + MERGE
# ============================================================
# The SAS uses PROC FORMAT INVALUE (CNTRY_RISK_IN) and PUT
# ($CHNL_RISK, $CASHOCC) to apply lookup tables stored in
# FMTLIB. This translation hard-codes the same values from
# formats/kyc_formats.sas.  If the format catalogue is ever
# updated, these dicts must be kept in sync.
# ============================================================
import pandas as pd

COUNTRY_RISK: dict[str, int] = {
    **dict.fromkeys(["AF", "IR", "IQ", "KP", "SY", "YE", "LY", "MM", "SS"], 5),
    **dict.fromkeys(["PK", "JO", "TN", "NG", "GH", "UG", "ZW", "ML", "NI"], 4),
    **dict.fromkeys(["RU", "BY", "CN", "VN", "TH", "BR", "MX", "TR", "ZA"], 3),
    **dict.fromkeys(["IN", "ID", "PH", "EG", "MA", "SA", "AE", "QA", "KW"], 2),
}
CHANNEL_RISK: dict[str, int] = {"INTRO": 3, "DIGITAL": 2, "BRANCH": 1}
CASH_OCC = {"DEAL", "GAMB", "CASI", "PAWN", "CURR", "REAG"}


def _score_row(row: pd.Series) -> pd.Series:
    # SAS: sas/04_score_risk.sas:34
    score = 0

    score += COUNTRY_RISK.get(str(row["cntry_resdnc_cd"]), 1) * 10

    if row["pep_self_decl_flg"] == "Y":
        score += 40
        pep_flag = "Y"
    elif row.get("match_flg") in ("Y", "P") and (row.get("best_sim") or 0) >= 100:
        score += 30
        pep_flag = "P"
    else:
        pep_flag = "N"

    if row.get("match_flg") == "Y" and row.get("match_method") == "COMPGED":
        score += 50
    elif row.get("match_flg") == "P":
        score += 20

    sow = str(row.get("src_of_wlth_cd", ""))
    if sow == "OTHR":
        score += 15
    elif sow == "BUSPRT":
        score += 10

    score += CHANNEL_RISK.get(str(row.get("onbrd_chnl_cd", "")), 2) * 5

    cust_typ = str(row.get("cust_typ_cd", ""))
    if cust_typ in ("TRUST", "FUND"):
        score += 20
    elif cust_typ == "CORP":
        score += 10

    if str(row.get("occ_cd", "")) in CASH_OCC:
        score += 25

    if score >= 80:
        band = "HIGH"
    elif score >= 40:
        band = "MED"
    else:
        band = "LOW"

    return pd.Series({"crr_score": score, "crr_band_cd": band, "pep_flag": pep_flag})


def run() -> None:
    # SAS: sas/04_score_risk.sas:17 (MERGE clients_std + screen_best)
    clients_std = pd.read_parquet("data/staging/clients_std.parquet")
    screen_best = pd.read_parquet("data/staging/screen_best.parquet")

    clients_screened = clients_std.merge(
        screen_best[["cust_id", "match_flg", "best_wl_id", "best_sim", "match_method"]],
        on="cust_id",
        how="left",
    )
    for col in ["match_flg", "best_wl_id", "match_method"]:
        clients_screened[col] = clients_screened[col].fillna(
            "N" if col == "match_flg" else ""
        )
    clients_screened["best_sim"] = clients_screened["best_sim"].fillna(0)

    scored = clients_screened.join(clients_screened.apply(_score_row, axis=1))
    scored.to_parquet("data/output/clients_scored.parquet", index=False)
""",
    "maintain_scd.py": """\
\"\"\"Step 5: maintain SCD Type-2 history on the client master.\"\"\"
# ============================================================
# REVIEW REQUIRED — SCD Type-2 MERGE pattern
# ============================================================
# The SAS uses a sorted MERGE with BY cust_id to close out
# current records and insert new versions.  The Python
# translation preserves the same surrogate-key increment logic
# but uses pandas merge + concat instead.
#
# CRITICAL: If two runs overlap without a clean handoff the
# cust_sk counter may produce duplicates — same warning as in
# the original SAS comment.
# ============================================================
import pandas as pd


def run() -> None:
    # SAS: sas/05_maintain_scd.sas:13
    client_master = pd.read_csv("data/staging/client_master.csv")
    clients_scored = pd.read_parquet("data/output/clients_scored.parquet")

    max_sk = int(client_master["cust_sk"].max())

    # SAS: sas/05_maintain_scd.sas:27 (close out current records)
    delta_ids = set(clients_scored["cust_id"])
    as_of_dt = pd.Timestamp("2024-12-31")
    close_mask = client_master["cust_id"].isin(delta_ids) & (client_master["curr_flg"] == "Y")
    client_master.loc[close_mask, "valid_to_dt"] = (as_of_dt - pd.Timedelta(days=1)).strftime(
        "%Y%m%d"
    )
    client_master.loc[close_mask, "curr_flg"] = "N"

    # SAS: sas/05_maintain_scd.sas:42 (insert new versions)
    new_versions = clients_scored[
        ["cust_id", "crr_band_cd", "crr_score", "full_nm_display"]
    ].copy()
    new_versions["cust_sk"] = range(max_sk + 1, max_sk + 1 + len(new_versions))
    new_versions["full_nm_std"] = new_versions["full_nm_display"]
    new_versions["valid_from_dt"] = as_of_dt.strftime("%Y%m%d")
    new_versions["valid_to_dt"] = "99991231"
    new_versions["curr_flg"] = "Y"
    new_versions["last_review_dt"] = as_of_dt.strftime("%Y%m%d")
    new_versions = new_versions.drop(columns=["full_nm_display"])

    client_master_scd = pd.concat(
        [client_master, new_versions[client_master.columns]], ignore_index=True
    )
    client_master_scd.to_csv("data/staging/client_master.csv", index=False)
    client_master_scd.to_parquet("data/output/client_master_scd.parquet", index=False)
""",
    "build_edd_queue.py": """\
\"\"\"Step 6: build EDD work queue and periodic review report.\"\"\"
# ============================================================
# MANUAL MIGRATION REQUIRED — PROC REPORT + ODS RTF
# ============================================================
# This step contains two components that require manual work:
#
# 1. EDD queue construction: the DATA step logic is translated
#    to pandas and is functionally equivalent. Review the
#    CATX/IFC reason-text assembly carefully — pandas string
#    concatenation behaviour differs for empty strings.
#
# 2. PROC REPORT + ODS RTF: the periodic review report writes
#    a formatted RTF document to a hardcoded UNC path.
#    Replace with your reporting framework (e.g. Jinja2/WeasyPrint,
#    openpyxl, or a BI tool export). The CALL DEFINE conditional
#    background-colour styling has no direct pandas equivalent.
#
# 3. Orphaned PROC PRINT (DEBUG) — present in original, excluded here.
# ============================================================
from datetime import date
from pathlib import Path

import pandas as pd

REVIEW_MONTHS = {"HIGH": 12, "MED": 24, "LOW": 36}


def run() -> None:
    # SAS: sas/06_build_edd_queue.sas:9
    clients_scored = pd.read_parquet("data/output/clients_scored.parquet")

    def _edd_row(row: pd.Series) -> pd.Series:
        trig_high = row["crr_band_cd"] == "HIGH"
        trig_pep = row["pep_flag"] in ("Y", "P")
        trig_sanc = row.get("match_flg") == "Y" and row.get("match_method") == "COMPGED"
        trig_cntry = row.get("cntry_resdnc_cd", "") in {
            "AF", "IR", "IQ", "KP", "SY", "YE", "LY", "MM", "SS",
            "PK", "JO", "TN", "NG", "GH", "UG", "ZW", "ML", "NI",
        }
        required = trig_high or trig_pep or trig_sanc or trig_cntry
        if not required:
            return pd.Series({"edd_required": False})

        if trig_sanc:
            priority = 1
        elif row["pep_flag"] == "Y":
            priority = 2
        elif trig_high:
            priority = 3
        else:
            priority = 4

        parts = []
        if trig_sanc:
            parts.append("Sanctions near-match")
        if row["pep_flag"] == "Y":
            parts.append("Confirmed PEP")
        if row["pep_flag"] == "P":
            parts.append("Possible PEP")
        if trig_high and not trig_sanc and row["pep_flag"] == "N":
            parts.append("High CRR score")
        if trig_cntry:
            parts.append("High-risk jurisdiction")

        return pd.Series({
            "edd_required": True,
            "case_priority": priority,
            "edd_reason_txt": "; ".join(parts),
        })

    flags = clients_scored.apply(_edd_row, axis=1)
    edd_queue = clients_scored[flags["edd_required"].fillna(False)].copy()
    edd_queue["case_priority"] = flags.loc[edd_queue.index, "case_priority"]
    edd_queue["edd_reason_txt"] = flags.loc[edd_queue.index, "edd_reason_txt"]
    edd_queue = edd_queue.sort_values(
        ["case_priority", "crr_score"], ascending=[True, False]
    )
    edd_queue.to_parquet("data/output/edd_queue.parquet", index=False)

    # SAS: sas/06_build_edd_queue.sas:72 (PROC REPORT + ODS RTF — MANUAL)
    # REVIEW REQUIRED: replace with appropriate reporting framework
    # Stub: write CSV for downstream consumers until RTF is implemented
    out_dir = Path("data/output/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    edd_queue.to_csv(out_dir / "kyc_periodic_review_20241231.csv", index=False)
""",
}

# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

PIPELINE_STEPS = [
    {
        "step_id": "step_01",
        "label": "Ingest client onboarding delta",
        "source_file": "sas/01_ingest_clients.sas",
        "inputs": ["client_onboarding.csv"],
        "outputs": ["clients_raw", "clients_delta"],
    },
    {
        "step_id": "step_02",
        "label": "Standardise identity attributes",
        "source_file": "sas/02_standardise_identity.sas",
        "inputs": ["clients_delta"],
        "outputs": ["clients_std"],
    },
    {
        "step_id": "step_03",
        "label": "Screen against watchlist",
        "source_file": "sas/03_screen_watchlist.sas",
        "inputs": ["clients_std", "watchlist.csv"],
        "outputs": ["screen_best"],
    },
    {
        "step_id": "step_04",
        "label": "Score customer risk (CRR)",
        "source_file": "sas/04_score_risk.sas",
        "inputs": ["clients_std", "screen_best", "risk_weights.csv"],
        "outputs": ["clients_scored"],
    },
    {
        "step_id": "step_05",
        "label": "Maintain SCD Type-2 master",
        "source_file": "sas/05_maintain_scd.sas",
        "inputs": ["clients_scored", "client_master.csv"],
        "outputs": ["client_master_scd"],
    },
    {
        "step_id": "step_06",
        "label": "Build EDD queue and review report",
        "source_file": "sas/06_build_edd_queue.sas",
        "inputs": ["clients_scored", "client_master_scd"],
        "outputs": ["edd_queue", "review_due"],
    },
]

# ---------------------------------------------------------------------------
# Block plans
# ---------------------------------------------------------------------------

BLOCK_PLANS = [
    # ── 01_ingest_clients.sas ──────────────────────────────────────────
    {
        "block_id": "01_ingest_clients.sas:10",
        "source_file": "sas/01_ingest_clients.sas",
        "start_line": 10,
        "end_line": 36,
        "block_type": "DATA_STEP",
        "strategy": "translated",
        "risk": "low",
        "rationale": (
            "INFILE/INPUT with DSD delimiter is equivalent to pd.read_csv with dtype=str."
            " PRXCHANGE regex cleansing maps directly to pandas str.replace."
            " FORMAT DATE9./DATETIME20. handled by pd.to_datetime."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.90,
        "confidence_band": "high",
        "input_datasets": ["client_onboarding.csv"],
        "output_datasets": ["work.clients_raw"],
    },
    {
        "block_id": "01_ingest_clients.sas:43",
        "source_file": "sas/01_ingest_clients.sas",
        "start_line": 43,
        "end_line": 46,
        "block_type": "DATA_STEP",
        "strategy": "translated",
        "risk": "low",
        "rationale": (
            "Simple WHERE date filter. "
            "Translated to pandas boolean mask. "
            "Hardcoded '01DEC2024' literal preserved as a known issue (see README)."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.90,
        "confidence_band": "high",
        "input_datasets": ["work.clients_raw"],
        "output_datasets": ["work.clients_delta"],
    },
    # ── 02_standardise_identity.sas ───────────────────────────────────
    {
        "block_id": "02_standardise_identity.sas:8",
        "source_file": "sas/02_standardise_identity.sas",
        "start_line": 8,
        "end_line": 41,
        "block_type": "DATA_STEP",
        "strategy": "translated",
        "risk": "low",
        "rationale": (
            "UPCASE/COMPRESS maps to str.upper() + str.replace."
            " SOUNDEX translated with a Python implementation."
            " PROPCASE maps to str.title()."
            " DOB plausibility flags and age band derivation map to pandas boolean indexing."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.88,
        "confidence_band": "high",
        "input_datasets": ["work.clients_delta"],
        "output_datasets": ["work.clients_std"],
    },
    # ── 03_screen_watchlist.sas ───────────────────────────────────────
    {
        "block_id": "03_screen_watchlist.sas:31",
        "source_file": "sas/03_screen_watchlist.sas",
        "start_line": 31,
        "end_line": 60,
        "block_type": "DATA_STEP",
        "strategy": "translated_with_review",
        "risk": "medium",
        "rationale": (
            "DECLARE HASH / HITER pattern replaced with rapidfuzz edit-distance."
            " COMPGED has no direct Python equivalent — threshold calibration required."
            " SOUNDEX + COMPLEV phonetic fallback approximated with Jaro-Winkler similarity."
            " Threshold values (100 for SANCTION, 120 for PEP/ADVMEDIA) must be validated"
            " against a SAS baseline run before production use."
            " Known threshold drift bug in original preserved."
        ),
        "estimated_effort": "medium",
        "confidence_score": 0.65,
        "confidence_band": "medium",
        "input_datasets": ["work.clients_std", "work.watchlist_all"],
        "output_datasets": ["work.screen_best"],
    },
    # ── 04_score_risk.sas ─────────────────────────────────────────────
    {
        "block_id": "04_score_risk.sas:17",
        "source_file": "sas/04_score_risk.sas",
        "start_line": 17,
        "end_line": 31,
        "block_type": "DATA_STEP",
        "strategy": "translated_with_review",
        "risk": "medium",
        "rationale": (
            "MERGE with IN= flags translated to pandas left merge + fillna."
            " Functionally equivalent but SAS MERGE requires sorted input;"
            " confirm sort order is preserved upstream."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.75,
        "confidence_band": "medium",
        "input_datasets": ["work.clients_std", "work.screen_best"],
        "output_datasets": ["work.clients_screened"],
    },
    {
        "block_id": "04_score_risk.sas:34",
        "source_file": "sas/04_score_risk.sas",
        "start_line": 34,
        "end_line": 82,
        "block_type": "DATA_STEP",
        "strategy": "translated_with_review",
        "risk": "medium",
        "rationale": (
            "Rules cascade using IF/THEN/ELSE and PROC FORMAT lookups (CNTRY_RISK_IN,"
            " $CHNL_RISK, $CASHOCC). Format values hard-coded from kyc_formats.sas."
            " Must be kept in sync if the format catalogue changes."
            " Accumulator pattern (crr_score +) translated to incremental Python additions."
        ),
        "estimated_effort": "low",
        "confidence_score": 0.75,
        "confidence_band": "medium",
        "input_datasets": ["work.clients_screened", "work.risk_weights"],
        "output_datasets": ["work.clients_scored"],
    },
    # ── 05_maintain_scd.sas ───────────────────────────────────────────
    {
        "block_id": "05_maintain_scd.sas:13",
        "source_file": "sas/05_maintain_scd.sas",
        "start_line": 13,
        "end_line": 75,
        "block_type": "DATA_STEP",
        "strategy": "translated_with_review",
        "risk": "high",
        "rationale": (
            "SCD Type-2 MERGE pattern: sorted BY cust_id with IN= flags."
            " Closing out current records (curr_flg='N', valid_to_dt) and inserting new"
            " versions with RETAIN-based surrogate key counter."
            " Translated to pandas merge + loc assignment + concat."
            " CRITICAL: duplicate-key risk on overlapping runs preserved from original."
            " Validate surrogate key uniqueness after each run."
        ),
        "estimated_effort": "high",
        "confidence_score": 0.60,
        "confidence_band": "medium",
        "input_datasets": ["work.clients_scored", "STAGLIB.client_master"],
        "output_datasets": ["work.client_master_scd", "STAGLIB.client_master"],
    },
    # ── 06_build_edd_queue.sas ────────────────────────────────────────
    {
        "block_id": "06_build_edd_queue.sas:9",
        "source_file": "sas/06_build_edd_queue.sas",
        "start_line": 9,
        "end_line": 41,
        "block_type": "DATA_STEP",
        "strategy": "manual",
        "risk": "high",
        "rationale": (
            "EDD trigger logic and CATX/IFC reason-text assembly translated to pandas."
            " PROC REPORT + ODS RTF has no direct Python equivalent — requires a"
            " reporting framework (Jinja2, openpyxl, or BI tool)."
            " CALL DEFINE conditional cell styling cannot be auto-translated."
            " Orphaned PROC PRINT (DEBUG) excluded from output."
            " Global macro variables REVIEW_CUTOFF_HIGH/MED/LOW from m_set_review_window"
            " must be replaced with explicit Python date arithmetic."
        ),
        "estimated_effort": "high",
        "confidence_score": 0.40,
        "confidence_band": "low",
        "input_datasets": ["work.clients_scored", "work.client_master_scd"],
        "output_datasets": ["work.edd_queue", "work.review_due"],
    },
]

# ---------------------------------------------------------------------------
# Libname map
# ---------------------------------------------------------------------------

LIBNAME_MAP = {
    "RAWLIB": "data/raw",
    "STAGLIB": "data/staging",
    "REFLIB": "data/ref",
    # OUTLIB and FMTLIB intentionally omitted: output tables have no libname so
    # they appear in the ERD (Data Model view).
}

# ---------------------------------------------------------------------------
# Data schema
# ---------------------------------------------------------------------------

DATA_SCHEMA = {
    "data/raw/client_onboarding.csv": {
        "columns": [
            "cust_id",
            "eff_dt",
            "full_nm",
            "dob",
            "cntry_resdnc_cd",
            "cntry_ctznshp_cd",
            "cust_typ_cd",
            "occ_cd",
            "pep_self_decl_flg",
            "src_of_wlth_cd",
            "onbrd_chnl_cd",
            "load_dttm",
        ],
        "column_types": {
            "cust_id": "character",
            "eff_dt": "double",
            "full_nm": "character",
            "dob": "double",
            "cntry_resdnc_cd": "character",
            "cntry_ctznshp_cd": "character",
            "cust_typ_cd": "character",
            "occ_cd": "character",
            "pep_self_decl_flg": "character",
            "src_of_wlth_cd": "character",
            "onbrd_chnl_cd": "character",
            "load_dttm": "double",
        },
        "column_labels": {
            "cust_id": "Customer Identifier",
            "eff_dt": "Effective Date",
            "full_nm": "Full Name (raw)",
            "dob": "Date of Birth",
            "cntry_resdnc_cd": "Country of Residence (ISO-2)",
            "cntry_ctznshp_cd": "Country of Citizenship (ISO-2)",
            "cust_typ_cd": "Customer Type Code",
            "occ_cd": "Occupation Code",
            "pep_self_decl_flg": "PEP Self-Declaration Flag",
            "src_of_wlth_cd": "Source of Wealth Code",
            "onbrd_chnl_cd": "Onboarding Channel Code",
            "load_dttm": "Load Datetime",
        },
        "column_formats": {
            "eff_dt": "DATE9.",
            "dob": "DATE9.",
            "load_dttm": "DATETIME20.",
        },
        "row_count": 220,
    },
    "data/raw/watchlist.csv": {
        "columns": [
            "wl_id",
            "wl_nm",
            "wl_typ_cd",
            "wl_cntry_cd",
            "list_src_cd",
            "list_dt",
            "wl_dob",
        ],
        "column_types": {
            "wl_id": "character",
            "wl_nm": "character",
            "wl_typ_cd": "character",
            "wl_cntry_cd": "character",
            "list_src_cd": "character",
            "list_dt": "character",
            "wl_dob": "character",
        },
        "column_labels": {
            "wl_id": "Watchlist Entry Identifier",
            "wl_nm": "Watchlist Name (uppercased)",
            "wl_typ_cd": "Watchlist Type (SANCTION/PEP/ADVMEDIA)",
            "wl_cntry_cd": "Associated Country (ISO-2)",
            "list_src_cd": "List Source Code (OFAC/UN/EU)",
            "list_dt": "List Date",
            "wl_dob": "Date of Birth on Watchlist",
        },
        "column_formats": {},
        "row_count": 117,
    },
    "data/ref/risk_weights.csv": {
        "columns": ["factor_cd", "factor_val", "weight_pts"],
        "column_types": {
            "factor_cd": "character",
            "factor_val": "double",
            "weight_pts": "double",
        },
        "column_labels": {
            "factor_cd": "Risk Factor Code",
            "factor_val": "Factor Value",
            "weight_pts": "Weight Points",
        },
        "column_formats": {},
        "row_count": 24,
    },
    "data/staging/client_master.csv": {
        "columns": [
            "cust_id",
            "cust_sk",
            "full_nm_std",
            "crr_band_cd",
            "crr_score",
            "valid_from_dt",
            "valid_to_dt",
            "curr_flg",
            "last_review_dt",
        ],
        "column_types": {
            "cust_id": "character",
            "cust_sk": "double",
            "full_nm_std": "character",
            "crr_band_cd": "character",
            "crr_score": "double",
            "valid_from_dt": "character",
            "valid_to_dt": "character",
            "curr_flg": "character",
            "last_review_dt": "character",
        },
        "column_labels": {
            "cust_id": "Customer Identifier",
            "cust_sk": "Customer Surrogate Key (SCD-2)",
            "full_nm_std": "Standardised Full Name",
            "crr_band_cd": "Customer Risk Rating Band",
            "crr_score": "Composite Risk Score",
            "valid_from_dt": "SCD-2 Valid From Date",
            "valid_to_dt": "SCD-2 Valid To Date (99991231 = current)",
            "curr_flg": "Current Record Flag (Y/N)",
            "last_review_dt": "Last Periodic Review Date",
        },
        "column_formats": {},
        "row_count": 50,
    },
    "clients_scored": {
        "columns": [
            "cust_id",
            "eff_dt",
            "full_nm",
            "full_nm_upper",
            "dob",
            "cntry_resdnc_cd",
            "cntry_ctznshp_cd",
            "cust_typ_cd",
            "occ_cd",
            "pep_self_decl_flg",
            "src_of_wlth_cd",
            "onbrd_chnl_cd",
            "match_flg",
            "best_wl_id",
            "best_sim",
            "match_method",
            "crr_score",
            "crr_band_cd",
            "pep_flag",
        ],
        "column_types": {
            "cust_id": "character",
            "eff_dt": "double",
            "full_nm": "character",
            "full_nm_upper": "character",
            "dob": "double",
            "cntry_resdnc_cd": "character",
            "cntry_ctznshp_cd": "character",
            "cust_typ_cd": "character",
            "occ_cd": "character",
            "pep_self_decl_flg": "character",
            "src_of_wlth_cd": "character",
            "onbrd_chnl_cd": "character",
            "match_flg": "character",
            "best_wl_id": "character",
            "best_sim": "double",
            "match_method": "character",
            "crr_score": "double",
            "crr_band_cd": "character",
            "pep_flag": "character",
        },
        "column_labels": {
            "full_nm_upper": "Full Name (uppercased, normalised)",
            "match_flg": "Watchlist Match Flag (Y/P/N)",
            "best_wl_id": "Best Matching Watchlist Entry ID",
            "best_sim": "Best Similarity Score (0-200)",
            "match_method": "Match Method (COMPGED / SOUNDEX+LEV)",
            "crr_score": "Composite Customer Risk Score",
            "crr_band_cd": "Risk Band (HIGH/MED/LOW)",
            "pep_flag": "PEP Flag (Y=confirmed, P=possible, N=none)",
        },
        "column_formats": {},
        "row_count": 200,
    },
    "edd_queue": {
        "columns": [
            "cust_id",
            "eff_dt",
            "full_nm",
            "full_nm_upper",
            "dob",
            "cntry_resdnc_cd",
            "cntry_ctznshp_cd",
            "cust_typ_cd",
            "occ_cd",
            "pep_self_decl_flg",
            "src_of_wlth_cd",
            "onbrd_chnl_cd",
            "match_flg",
            "best_wl_id",
            "best_sim",
            "match_method",
            "crr_score",
            "crr_band_cd",
            "pep_flag",
            "case_priority",
            "edd_reason_txt",
        ],
        "column_types": {
            "cust_id": "character",
            "eff_dt": "double",
            "full_nm": "character",
            "full_nm_upper": "character",
            "dob": "double",
            "cntry_resdnc_cd": "character",
            "cntry_ctznshp_cd": "character",
            "cust_typ_cd": "character",
            "occ_cd": "character",
            "pep_self_decl_flg": "character",
            "src_of_wlth_cd": "character",
            "onbrd_chnl_cd": "character",
            "match_flg": "character",
            "best_wl_id": "character",
            "best_sim": "double",
            "match_method": "character",
            "crr_score": "double",
            "crr_band_cd": "character",
            "pep_flag": "character",
            "case_priority": "double",
            "edd_reason_txt": "character",
        },
        "column_labels": {
            "case_priority": "EDD Case Priority (1=sanctions urgent, 2=PEP, 3=high CRR, 4=other)",
            "edd_reason_txt": "EDD Trigger Reason Text",
        },
        "column_formats": {},
        "row_count": 19,
    },
}

# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------

RELATIONSHIPS = [
    {
        "left_table": "clients_scored",
        "right_table": "client_master",
        "key_column": "cust_id",
        "via_block_id": "05_maintain_scd.sas:13",
        "relationship_type": "merge",
    },
    {
        "left_table": "edd_queue",
        "right_table": "clients_scored",
        "key_column": "cust_id",
        "via_block_id": "06_build_edd_queue.sas:9",
        "relationship_type": "filter",
    },
    {
        "left_table": "clients_scored",
        "right_table": "watchlist",
        "key_column": "best_wl_id",
        "via_block_id": "03_screen_watchlist.sas:31",
        "relationship_type": "join",
    },
    {
        "left_table": "clients_scored",
        "right_table": "risk_weights",
        "key_column": "factor_cd",
        "via_block_id": "04_score_risk.sas:34",
        "relationship_type": "join",
    },
]

# ---------------------------------------------------------------------------
# Migration plan
# ---------------------------------------------------------------------------

MIGRATION_PLAN = {
    "summary": (
        "KYC / AML Client Screening migrates a 6-script SAS compliance batch into Python/pandas. "
        "The pipeline ingests a daily client onboarding delta, standardises identity attributes "
        "(name normalisation, SOUNDEX, DOB validation), screens against a consolidated "
        "sanctions/PEP/adverse-media watchlist using COMPGED fuzzy matching, scores each client "
        "with a weighted rules cascade, maintains a SCD Type-2 client master, and builds an EDD "
        "work queue with a periodic review report. "
        "2 of 8 blocks are fully auto-translated. 4 require targeted review (HASH-based "
        "screening, MERGE patterns, SCD Type-2 logic). 1 block requires manual migration "
        "(PROC REPORT + ODS RTF)."
    ),
    "overall_risk": "high",
    "risk_explanation": (
        "High overall risk. The watchlist screening step (DECLARE HASH + COMPGED) has no "
        "direct Python equivalent — COMPGED is a SAS proprietary generalised edit distance "
        "and threshold calibration requires a SAS baseline run. The SCD Type-2 MERGE pattern "
        "has a known duplicate-key risk on overlapping runs. PROC REPORT + ODS RTF requires "
        "a full replacement with a Python reporting framework."
    ),
    "block_plans": BLOCK_PLANS,
    "recommended_review_blocks": [
        "03_screen_watchlist.sas:31",
        "05_maintain_scd.sas:13",
        "06_build_edd_queue.sas:9",
        "04_score_risk.sas:34",
    ],
    "cross_file_dependencies": [
        "sas/01_ingest_clients.sas depends on macros/m_log_step.sas",
        "sas/02_standardise_identity.sas depends on macros/m_log_step.sas",
        "sas/03_screen_watchlist.sas depends on macros/m_log_step.sas and macros/m_screen_pass.sas",
        "sas/04_score_risk.sas depends on macros/m_log_step.sas and macros/m_assert_nonempty.sas",
        "sas/04_score_risk.sas reads formats/kyc_formats.sas (CNTRY_RISK_IN, $CHNL_RISK, $CASHOCC)",
        "sas/05_maintain_scd.sas depends on macros/m_log_step.sas and macros/m_assert_nonempty.sas",
        "sas/06_build_edd_queue.sas depends on macros/m_log_step.sas and macros/m_set_review_window.sas",
        "sas/06_build_edd_queue.sas reads global macro vars REVIEW_CUTOFF_HIGH/MED/LOW from run_all.sas",
        "sas/06_build_edd_queue.sas reads formats/kyc_formats.sas (CNTRY_RISK_IN for trigger logic)",
    ],
    "missing_dependencies": [
        "FMTLIB format catalogue not bundled — formats hard-coded from kyc_formats.sas",
        "%m_check_obs inline in 01_ingest_clients.sas — not in macros/ directory",
    ],
    "sensitive_data_findings": [
        {
            "column": "full_nm",
            "matched_signal": "name",
            "source_type": "file",
            "source": "data/raw/client_onboarding.csv",
        },
        {
            "column": "dob",
            "matched_signal": "date_of_birth",
            "source_type": "file",
            "source": "data/raw/client_onboarding.csv",
        },
        {
            "column": "cntry_resdnc_cd",
            "matched_signal": "country",
            "source_type": "file",
            "source": "data/raw/client_onboarding.csv",
        },
        {
            "column": "pep_self_decl_flg",
            "matched_signal": "pep_status",
            "source_type": "file",
            "source": "data/raw/client_onboarding.csv",
        },
        {
            "column": "wl_nm",
            "matched_signal": "name",
            "source_type": "file",
            "source": "data/raw/watchlist.csv",
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
            "id": "01_ingest_clients.sas:10",
            "label": "DATA clients_raw (INFILE/INPUT)",
            "source_file": "sas/01_ingest_clients.sas",
            "block_type": "DATA_STEP",
            "status": "migrated",
        },
        {
            "id": "01_ingest_clients.sas:43",
            "label": "DATA clients_delta (date filter)",
            "source_file": "sas/01_ingest_clients.sas",
            "block_type": "DATA_STEP",
            "status": "migrated",
        },
        {
            "id": "02_standardise_identity.sas:8",
            "label": "DATA clients_std (name + DOB standardise)",
            "source_file": "sas/02_standardise_identity.sas",
            "block_type": "DATA_STEP",
            "status": "migrated",
        },
        {
            "id": "03_screen_watchlist.sas:31",
            "label": "HASH screen — SANCTION / PEP / ADVMEDIA",
            "source_file": "sas/03_screen_watchlist.sas",
            "block_type": "DATA_STEP",
            "status": "migrated",
        },
        {
            "id": "04_score_risk.sas:17",
            "label": "MERGE clients_std + screen_best",
            "source_file": "sas/04_score_risk.sas",
            "block_type": "DATA_STEP",
            "status": "migrated",
        },
        {
            "id": "04_score_risk.sas:34",
            "label": "DATA clients_scored (CRR rules cascade)",
            "source_file": "sas/04_score_risk.sas",
            "block_type": "DATA_STEP",
            "status": "migrated",
        },
        {
            "id": "05_maintain_scd.sas:13",
            "label": "SCD Type-2 MERGE — client master",
            "source_file": "sas/05_maintain_scd.sas",
            "block_type": "DATA_STEP",
            "status": "migrated",
        },
        {
            "id": "06_build_edd_queue.sas:9",
            "label": "EDD queue + PROC REPORT (manual)",
            "source_file": "sas/06_build_edd_queue.sas",
            "block_type": "DATA_STEP",
            "status": "manual_review",
        },
    ],
    "edges": [
        {
            "source": "01_ingest_clients.sas:10",
            "target": "01_ingest_clients.sas:43",
            "dataset": "work.clients_raw",
            "inferred": False,
        },
        {
            "source": "01_ingest_clients.sas:43",
            "target": "02_standardise_identity.sas:8",
            "dataset": "work.clients_delta",
            "inferred": False,
        },
        {
            "source": "02_standardise_identity.sas:8",
            "target": "03_screen_watchlist.sas:31",
            "dataset": "work.clients_std",
            "inferred": False,
        },
        {
            "source": "02_standardise_identity.sas:8",
            "target": "04_score_risk.sas:17",
            "dataset": "work.clients_std",
            "inferred": False,
        },
        {
            "source": "03_screen_watchlist.sas:31",
            "target": "04_score_risk.sas:17",
            "dataset": "work.screen_best",
            "inferred": False,
        },
        {
            "source": "04_score_risk.sas:17",
            "target": "04_score_risk.sas:34",
            "dataset": "work.clients_screened",
            "inferred": False,
        },
        {
            "source": "04_score_risk.sas:34",
            "target": "05_maintain_scd.sas:13",
            "dataset": "work.clients_scored",
            "inferred": False,
        },
        {
            "source": "04_score_risk.sas:34",
            "target": "06_build_edd_queue.sas:9",
            "dataset": "work.clients_scored",
            "inferred": False,
        },
        {
            "source": "05_maintain_scd.sas:13",
            "target": "06_build_edd_queue.sas:9",
            "dataset": "work.client_master_scd",
            "inferred": False,
        },
    ],
    "file_nodes": [
        {
            "filename": "autoexec.sas",
            "file_type": "AUTOEXEC",
            "blocks": [],
            "status": "OK",
        },
        {
            "filename": "macros/m_log_step.sas",
            "file_type": "MACRO",
            "blocks": [],
            "status": "OK",
        },
        {
            "filename": "macros/m_assert_nonempty.sas",
            "file_type": "MACRO",
            "blocks": [],
            "status": "OK",
        },
        {
            "filename": "macros/m_set_review_window.sas",
            "file_type": "MACRO",
            "blocks": [],
            "status": "OK",
        },
        {
            "filename": "macros/m_screen_pass.sas",
            "file_type": "MACRO",
            "blocks": [],
            "status": "OK",
        },
        {
            "filename": "formats/kyc_formats.sas",
            "file_type": "PROGRAM",
            "blocks": [],
            "status": "OK",
        },
        {
            "filename": "sas/01_ingest_clients.sas",
            "file_type": "PROGRAM",
            "blocks": ["01_ingest_clients.sas:10", "01_ingest_clients.sas:43"],
            "status": "OK",
        },
        {
            "filename": "sas/02_standardise_identity.sas",
            "file_type": "PROGRAM",
            "blocks": ["02_standardise_identity.sas:8"],
            "status": "OK",
        },
        {
            "filename": "sas/03_screen_watchlist.sas",
            "file_type": "PROGRAM",
            "blocks": ["03_screen_watchlist.sas:31"],
            "status": "OK",
        },
        {
            "filename": "sas/04_score_risk.sas",
            "file_type": "PROGRAM",
            "blocks": ["04_score_risk.sas:17", "04_score_risk.sas:34"],
            "status": "OK",
        },
        {
            "filename": "sas/05_maintain_scd.sas",
            "file_type": "PROGRAM",
            "blocks": ["05_maintain_scd.sas:13"],
            "status": "OK",
        },
        {
            "filename": "sas/06_build_edd_queue.sas",
            "file_type": "PROGRAM",
            "blocks": ["06_build_edd_queue.sas:9"],
            "status": "ERROR_PRONE",
            "status_reason": (
                "PROC REPORT + ODS RTF requires manual migration — no automatic translation"
            ),
        },
    ],
    "file_edges": [
        {
            "source_file": "sas/01_ingest_clients.sas",
            "target_file": "macros/m_log_step.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "01_ingest_clients.sas:10",
        },
        {
            "source_file": "sas/02_standardise_identity.sas",
            "target_file": "macros/m_log_step.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "02_standardise_identity.sas:8",
        },
        {
            "source_file": "sas/03_screen_watchlist.sas",
            "target_file": "macros/m_log_step.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "03_screen_watchlist.sas:31",
        },
        {
            "source_file": "sas/03_screen_watchlist.sas",
            "target_file": "macros/m_screen_pass.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "03_screen_watchlist.sas:31",
        },
        {
            "source_file": "sas/04_score_risk.sas",
            "target_file": "macros/m_log_step.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "04_score_risk.sas:17",
        },
        {
            "source_file": "sas/04_score_risk.sas",
            "target_file": "macros/m_assert_nonempty.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "04_score_risk.sas:17",
        },
        {
            "source_file": "sas/04_score_risk.sas",
            "target_file": "formats/kyc_formats.sas",
            "reason": "FORMAT_CALL",
            "via_block_id": "04_score_risk.sas:34",
        },
        {
            "source_file": "sas/05_maintain_scd.sas",
            "target_file": "macros/m_log_step.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "05_maintain_scd.sas:13",
        },
        {
            "source_file": "sas/05_maintain_scd.sas",
            "target_file": "macros/m_assert_nonempty.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "05_maintain_scd.sas:13",
        },
        {
            "source_file": "sas/06_build_edd_queue.sas",
            "target_file": "macros/m_log_step.sas",
            "reason": "MACRO_CALL",
            "via_block_id": "06_build_edd_queue.sas:9",
        },
        {
            "source_file": "sas/06_build_edd_queue.sas",
            "target_file": "macros/m_set_review_window.sas",
            "reason": "MACRO_VAR",
            "via_block_id": "06_build_edd_queue.sas:9",
        },
        {
            "source_file": "sas/06_build_edd_queue.sas",
            "target_file": "formats/kyc_formats.sas",
            "reason": "FORMAT_CALL",
            "via_block_id": "06_build_edd_queue.sas:9",
        },
        # Data flow
        {
            "source_file": "sas/01_ingest_clients.sas",
            "target_file": "sas/02_standardise_identity.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "01_ingest_clients.sas:43",
        },
        {
            "source_file": "sas/02_standardise_identity.sas",
            "target_file": "sas/03_screen_watchlist.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "02_standardise_identity.sas:8",
        },
        {
            "source_file": "sas/02_standardise_identity.sas",
            "target_file": "sas/04_score_risk.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "02_standardise_identity.sas:8",
        },
        {
            "source_file": "sas/03_screen_watchlist.sas",
            "target_file": "sas/04_score_risk.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "03_screen_watchlist.sas:31",
        },
        {
            "source_file": "sas/04_score_risk.sas",
            "target_file": "sas/05_maintain_scd.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "04_score_risk.sas:34",
        },
        {
            "source_file": "sas/04_score_risk.sas",
            "target_file": "sas/06_build_edd_queue.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "04_score_risk.sas:34",
        },
        {
            "source_file": "sas/05_maintain_scd.sas",
            "target_file": "sas/06_build_edd_queue.sas",
            "reason": "WRITES_DATASET",
            "via_block_id": "05_maintain_scd.sas:13",
        },
    ],
    "pipeline_steps": [
        {
            "step_id": "step_01",
            "name": "Ingest client onboarding delta",
            "description": (
                "Read the daily delta CSV using INFILE/INPUT with UTF-8 encoding."
                " Clean name field with PRXCHANGE regex (strip punctuation, collapse spaces)."
                " Filter to current month records (known hardcoded date bug)."
            ),
            "files": ["sas/01_ingest_clients.sas"],
            "blocks": ["01_ingest_clients.sas:10", "01_ingest_clients.sas:43"],
            "inputs": ["client_onboarding.csv"],
            "outputs": ["clients_raw", "clients_delta"],
        },
        {
            "step_id": "step_02",
            "name": "Standardise identity attributes",
            "description": (
                "Normalise name to uppercase with compressed whitespace."
                " Derive SOUNDEX blocking key for fuzzy matching."
                " Flag implausible DOBs (future or age > 120)."
                " Assign age band (U25/U40/U60/O60)."
            ),
            "files": ["sas/02_standardise_identity.sas"],
            "blocks": ["02_standardise_identity.sas:8"],
            "inputs": ["clients_delta"],
            "outputs": ["clients_std"],
        },
        {
            "step_id": "step_03",
            "name": "Screen against watchlist",
            "description": (
                "Split watchlist into SANCTION / PEP / ADVMEDIA subsets."
                " Load each subset into an in-memory HASH object."
                " For each client, compute COMPGED (generalised edit distance) against all"
                " watchlist entries. Phonetic fallback via SOUNDEX + COMPLEV."
                " Keep best match per customer across all three passes."
            ),
            "files": ["sas/03_screen_watchlist.sas", "macros/m_screen_pass.sas"],
            "blocks": ["03_screen_watchlist.sas:31"],
            "inputs": ["clients_std", "watchlist.csv"],
            "outputs": ["screen_best"],
        },
        {
            "step_id": "step_04",
            "name": "Score customer risk (CRR)",
            "description": (
                "Merge screening results back to standardised clients."
                " Apply 7-factor rules cascade: country risk, PEP status, sanctions match,"
                " source of wealth, onboarding channel, customer type, occupation cash"
                " intensity. Assign HIGH/MED/LOW band from composite score."
            ),
            "files": ["sas/04_score_risk.sas", "formats/kyc_formats.sas"],
            "blocks": ["04_score_risk.sas:17", "04_score_risk.sas:34"],
            "inputs": ["clients_std", "screen_best", "risk_weights.csv"],
            "outputs": ["clients_scored"],
        },
        {
            "step_id": "step_05",
            "name": "Maintain SCD Type-2 master",
            "description": (
                "Load current client master from STAGLIB."
                " Close out records for clients present in today's delta"
                " (set valid_to_dt = AS_OF_DT - 1, curr_flg = 'N')."
                " Insert new versions with auto-incremented surrogate key."
                " Write updated master back to STAGLIB and OUTLIB."
            ),
            "files": ["sas/05_maintain_scd.sas"],
            "blocks": ["05_maintain_scd.sas:13"],
            "inputs": ["clients_scored", "client_master.csv"],
            "outputs": ["client_master_scd"],
        },
        {
            "step_id": "step_06",
            "name": "Build EDD queue and review report",
            "description": (
                "Filter scored clients to those requiring Enhanced Due Diligence"
                " (HIGH band, confirmed/possible PEP, sanctions match, high-risk jurisdiction)."
                " Assign case priority and build reason text."
                " Identify clients past their periodic review due date."
                " Produce PROC REPORT + ODS RTF periodic review report (manual migration)."
            ),
            "files": ["sas/06_build_edd_queue.sas"],
            "blocks": ["06_build_edd_queue.sas:9"],
            "inputs": ["clients_scored", "client_master_scd"],
            "outputs": ["edd_queue", "review_due"],
        },
    ],
    "block_confidence": {
        "01_ingest_clients.sas:10": {"confidence": "high", "verified_confidence": "high"},
        "01_ingest_clients.sas:43": {"confidence": "high", "verified_confidence": "high"},
        "02_standardise_identity.sas:8": {"confidence": "high", "verified_confidence": "high"},
        "03_screen_watchlist.sas:31": {"confidence": "medium", "verified_confidence": "medium"},
        "04_score_risk.sas:17": {"confidence": "medium", "verified_confidence": "medium"},
        "04_score_risk.sas:34": {"confidence": "medium", "verified_confidence": "medium"},
        "05_maintain_scd.sas:13": {"confidence": "medium", "verified_confidence": None},
        "06_build_edd_queue.sas:9": {"confidence": "low", "verified_confidence": None},
    },
    "cross_file_edges": [
        {
            "source": "03_screen_watchlist.sas:31",
            "target": "04_score_risk.sas:17",
            "dataset": "work.screen_best",
        },
        {
            "source": "04_score_risk.sas:34",
            "target": "05_maintain_scd.sas:13",
            "dataset": "work.clients_scored",
        },
        {
            "source": "04_score_risk.sas:34",
            "target": "06_build_edd_queue.sas:9",
            "dataset": "work.clients_scored",
        },
        {
            "source": "05_maintain_scd.sas:13",
            "target": "06_build_edd_queue.sas:9",
            "dataset": "work.client_master_scd",
        },
    ],
    "column_flows": [
        {
            "column": "cust_id",
            "source_dataset": "RAWLIB.client_onboarding",
            "target_dataset": "work.clients_scored",
            "via_block_id": "01_ingest_clients.sas:10",
        },
        {
            "column": "full_nm_upper",
            "source_dataset": "work.clients_std",
            "target_dataset": "work.screen_best",
            "via_block_id": "03_screen_watchlist.sas:31",
        },
        {
            "column": "crr_score",
            "source_dataset": "work.clients_scored",
            "target_dataset": "work.client_master_scd",
            "via_block_id": "05_maintain_scd.sas:13",
        },
        {
            "column": "crr_band_cd",
            "source_dataset": "work.clients_scored",
            "target_dataset": "work.edd_queue",
            "via_block_id": "06_build_edd_queue.sas:9",
        },
    ],
    "dataset_summaries": {
        "RAWLIB.client_onboarding": "Daily client onboarding delta — ~220 records",
        "work.clients_raw": "Raw ingest with name regex cleansing — ~220 records",
        "work.clients_delta": "Current-month delta (eff_dt >= 01DEC2024) — ~200 records",
        "work.clients_std": "Standardised names, SOUNDEX keys, DOB flags, age bands",
        "RAWLIB.watchlist": "Consolidated sanctions/PEP/adverse-media — 117 entries",
        "work.screen_best": "Best watchlist match per customer (Y/P/N flag)",
        "work.clients_scored": "Scored clients with CRR and risk band — ~200 records",
        "STAGLIB.client_master": "SCD-2 client master (pre-run) — 50 current records",
        "work.client_master_scd": "Updated SCD-2 master after new versions inserted",
        "work.edd_queue": "EDD cases requiring enhanced due diligence — ~19 records",
        "work.review_due": "Clients past periodic review cutoff date",
    },
}

# ---------------------------------------------------------------------------
# Block revisions
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
    """Insert the KYC/AML demo job and all block revisions into the database.

    Args:
        drop_existing: When True, delete any existing job with DEMO_JOB_ID first.
    """
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    input_hash = hashlib.sha256("\n".join(sorted(SAS_FILES.keys())).encode()).hexdigest()

    now = datetime.now(UTC)

    async with async_session() as session:
        if drop_existing:
            existing = await session.get(Job, DEMO_JOB_ID)
            if existing is not None:
                await session.delete(existing)
                await session.commit()

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

    print(f"Demo job seeded: {DEMO_JOB_ID}")
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
