/* ====================================================================
   m_log_step.sas
   Utility macro to write a step name and timestamp to the SAS log
   and also to the batch log file on the network share.

   How to use:
     %m_log_step(STEP_NAME=01_load_positions)

   Parameters:
     STEP_NAME = the name of the current step being executed

   Notes:
     - This macro is called at the start of every pipeline script.
     - The log file path is hardcoded to the prod log server.
       If you need to change it, talk to Platform Engineering.
     - Do NOT call this macro inside a DATA step or PROC SQL block.
       It must be called at the top level of your SAS program.
   ==================================================================== */

%MACRO m_log_step(STEP_NAME=);

  /* Get the current date and time as a formatted string */
  %LET _NOW = %SYSFUNC(datetime(), datetime20.);

  /* Write the step name and timestamp to the SAS log */
  %PUT NOTE: ============================================================;
  %PUT NOTE: STEP START : &STEP_NAME.;
  %PUT NOTE: TIMESTAMP  : &_NOW.;
  %PUT NOTE: RUN DATE   : &RUN_DT.;
  %PUT NOTE: ============================================================;

  /* Also write to the shared batch log file (hardcoded path) */
  /* Note: This will fail if the network share is unavailable */
  DATA _NULL_;
    FILE "\\apx-sas-prod\logs\finrep.log" MOD;
    PUT "STEP=&STEP_NAME. TS=&_NOW. RUN_DT=&RUN_DT.";
  RUN;

%MEND m_log_step;
