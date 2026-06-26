/* 01_ingest_clients.sas
   Ingest new/amended client onboarding records from the daily delta file.
   Author: W. Hargreaves / Client Onboarding Systems  2016
   Revised: F. Morel / Financial Crime Tech  2021-03 — added PRX cleansing
*/

%m_log_step(STEP_NAME=01_ingest_clients);

/* Read raw delta using INFILE/INPUT (PROC IMPORT rejected — encoding issues 2016) */
DATA work.clients_raw;
  INFILE RAWLIB('client_onboarding.csv')
    DSD DELIMITER=',' FIRSTOBS=2 MISSOVER TRUNCOVER
    LRECL=1000 ENCODING='UTF-8';

  INPUT
    cust_id          : $15.
    eff_dt           : yymmdd8.
    full_nm          : $100.
    dob              : yymmdd8.
    cntry_resdnc_cd  : $2.
    cntry_ctznshp_cd : $2.
    cust_typ_cd      : $6.
    occ_cd           : $8.
    pep_self_decl_flg: $1.
    src_of_wlth_cd   : $8.
    onbrd_chnl_cd    : $8.
    load_dttm        : DATETIME20.
  ;

  FORMAT eff_dt DATE9. dob DATE9. load_dttm DATETIME20.;

  /* Strip stray punctuation and Unicode noise from name field using regex */
  full_nm_clean = PRXCHANGE('s/[^\w\s\-]//oi', -1, full_nm);
  full_nm_clean = PRXCHANGE('s/\s+/ /o',        -1, STRIP(full_nm_clean));

RUN;

%m_check_obs(DSN=work.clients_raw);

/* Filter to current delta window.
   TODO: this should use &AS_OF_DT. macro but the literal was hardcoded in 2018
   and nobody has updated it. Works fine for December runs. */
DATA work.clients_delta;
  SET work.clients_raw;
  WHERE eff_dt >= '01DEC2024'd;
RUN;

%m_check_obs(DSN=work.clients_delta);

%PUT NOTE: [01_ingest_clients] Delta records: %SYSFUNC(attrn(%SYSFUNC(open(work.clients_delta)),NOBS)).;

/* Macro defined in macros/m_check_obs.sas */
%MACRO m_check_obs(DSN=);
  /* inline version kept for backward compat — original in macros/ */
  %IF %SYSFUNC(exist(&DSN.)) %THEN %DO;
    %IF %SYSFUNC(attrn(%SYSFUNC(open(&DSN.)),NOBS)) = 0 %THEN
      %PUT WARNING: [01_ingest_clients] &DSN. is empty.;
  %END;
%MEND;
