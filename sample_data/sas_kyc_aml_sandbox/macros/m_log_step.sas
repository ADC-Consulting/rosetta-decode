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
     - The log file path (\\mer-sas-prod\logs\kyc.log) is hardcoded.
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
    FILE "\\mer-sas-prod\logs\kyc.log" MOD;
    PUT "STEP=&STEP_NAME. TS=&_NOW. AS_OF_DT=&AS_OF_DT.";
  RUN;

%MEND m_log_step;
