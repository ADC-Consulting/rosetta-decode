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
