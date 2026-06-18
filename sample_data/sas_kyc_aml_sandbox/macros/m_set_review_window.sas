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
