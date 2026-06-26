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
  OUTFILE="\\apx-sas-prod\reports\&PERIOD_LABEL.\exposure_summary_&RUN_DT..csv"  /* global intentionally — used by 05_produce_output */
  DBMS=CSV
  REPLACE;
RUN;

/* Export enriched positions detail */
PROC EXPORT
  DATA=work.pos_enriched
  OUTFILE="\\apx-sas-prod\reports\&PERIOD_LABEL.\pos_enriched_&RUN_DT..csv"
  DBMS=CSV
  REPLACE;
RUN;

/* TODO: remove before prod */
PROC PRINT DATA=work.pos_enriched (OBS=20);
  TITLE "DEBUG: pos_enriched sample — &PERIOD_LABEL.";
  VAR trade_id desk_cd instmt_id qty_nom dirty_px dv01 mkt_val_eur rating_band;
RUN;

%PUT NOTE: [05_produce_output] Output written to OUTLIB and CSV export complete.;
