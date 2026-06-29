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
