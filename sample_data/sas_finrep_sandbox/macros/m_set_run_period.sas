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
