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
