/* 05_maintain_scd.sas
   Maintain SCD Type 2 history on the client master.
   Closes out prior versions for amended clients, inserts new versions.
   P. Hartmann / Data Warehouse  2017-03-14
   NOTE: This step is order-dependent. Run AFTER 04_score_risk.
         The surrogate key (cust_sk) increments from the max existing value.
         If two runs overlap without a clean handoff, duplicates may result.
*/

%m_log_step(STEP_NAME=05_maintain_scd);

/* Load current client master */
DATA work.client_master;
  SET STAGLIB.client_master;
RUN;

%m_assert_nonempty(DSN=work.client_master, CONTEXT=05_maintain_scd master empty);

/* Find max surrogate key in current master */
PROC SQL NOPRINT;
  SELECT MAX(cust_sk) INTO: _MAX_SK TRIMMED
  FROM work.client_master;
QUIT;
%LET _MAX_SK = %EVAL(&_MAX_SK. + 0);

/* Close out existing current records for clients in today's delta */
DATA work.client_master_closed;
  MERGE work.client_master (IN=a)
        work.clients_scored (IN=b KEEP=cust_id RENAME=(cust_id=cust_id));
  BY cust_id;
  IF a;

  /* Close out current record if this customer has a new version today */
  IF b AND curr_flg = 'Y' THEN DO;
    valid_to_dt = INPUT("&AS_OF_DT.", yymmdd8.) - 1;
    curr_flg    = 'N';
  END;

RUN;

/* Insert new versions for amended/new clients */
DATA work.new_versions;
  SET work.clients_scored;

  RETAIN _SK_CTR;
  IF _N_ = 1 THEN _SK_CTR = &_MAX_SK.;
  _SK_CTR + 1;

  cust_sk         = _SK_CTR;
  full_nm_std     = full_nm_display;
  valid_from_dt   = INPUT("&AS_OF_DT.", yymmdd8.);
  valid_to_dt     = INPUT('99991231', yymmdd8.);
  curr_flg        = 'Y';
  last_review_dt  = INPUT("&AS_OF_DT.", yymmdd8.);

  KEEP cust_id cust_sk full_nm_std crr_band_cd crr_score
       valid_from_dt valid_to_dt curr_flg last_review_dt;
  DROP _SK_CTR;
RUN;

/* Combine closed-out history with new versions */
DATA work.client_master_scd;
  SET work.client_master_closed
      work.new_versions;
  BY cust_id;
RUN;

/* Write back to staging library (overwrites) */
DATA STAGLIB.client_master;
  SET work.client_master_scd;
RUN;

DATA OUTLIB.client_master_scd;
  SET work.client_master_scd;
RUN;

%m_check_obs(DSN=work.client_master_scd, CONTEXT=05_maintain_scd final master);

%PUT NOTE: [05_maintain_scd] SCD-2 maintenance complete. Total records: %SYSFUNC(attrn(%SYSFUNC(open(work.client_master_scd)),NOBS)).;
