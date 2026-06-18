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
