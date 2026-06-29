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

/* old method pre-2022 — kept for reference in case PROC IMPORT breaks again
DATA work.instrument_ref_old;
  INFILE RAWLIB('instrument_ref.csv') DSD DELIMITER=',' FIRSTOBS=2 MISSOVER;
  INPUT
    instmt_id    : $15.
    isin         : $12.
    issuer_id    : $10.
    asset_cls_cd : $8.
    maturity_dt  : yymmdd8.
    cpn_rt       : BEST8.
    ext_rating_cd: $8.
    duration     : BEST8.
    ref_load_dt  : yymmdd8.
  ;
  FORMAT maturity_dt DATE9. ref_load_dt DATE9.;
RUN;
*/

%m_check_obs(DSN=work.instrument_ref, CONTEXT=02_load_reference instrument_ref);

/* Counterparty is pre-staged — just assign from staging library */
DATA work.counterparty;
  SET STAGLIB.counterparty;
RUN;

%m_check_obs(DSN=work.counterparty, CONTEXT=02_load_reference counterparty);

%PUT NOTE: [02_load_reference] Instrument ref: %SYSFUNC(attrn(%SYSFUNC(open(work.instrument_ref)),NOBS)) rows.;
%PUT NOTE: [02_load_reference] Counterparty:   %SYSFUNC(attrn(%SYSFUNC(open(work.counterparty)),NOBS)) rows.;
