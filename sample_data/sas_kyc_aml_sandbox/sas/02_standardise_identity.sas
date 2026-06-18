/* 02_standardise_identity.sas
   Standardise identity attributes for downstream matching.
   N. Johansson / Data Quality  2020-04-08
*/

%m_log_step(STEP_NAME=02_standardise_identity);

DATA work.clients_std;
  SET work.clients_delta;

  /* Standardise name: upper, compress spaces, remove double-spaces */
  full_nm_upper = UPCASE(COMPRESS(full_nm_clean, , 'S'));

  /* Derive SOUNDEX blocking key for name matching */
  soundex_key = SOUNDEX(full_nm_upper);

  /* Proper-case version for display */
  full_nm_display = PROPCASE(full_nm_clean);

  /* DOB plausibility check — flag implausible dates */
  /* old PROPCASE pre-2021 — removed when we standardised to COMPRESS first:
  full_nm_display = PROPCASE(full_nm);
  */
  IF dob > TODAY() THEN DO;
    dob_flag = 'FUTURE';
    %PUT WARNING: [02_standardise_identity] Future DOB found for &cust_id.;
  END;
  ELSE IF (TODAY() - dob) / 365.25 > 120 THEN dob_flag = 'IMPLAUSIBLE';
  ELSE dob_flag = '';

  /* Derive age band */
  IF dob NE . THEN DO;
    _age = INT((TODAY() - dob) / 365.25);
    IF      _age < 25  THEN age_band = 'U25';
    ELSE IF _age < 40  THEN age_band = 'U40';
    ELSE IF _age < 60  THEN age_band = 'U60';
    ELSE                    age_band = 'O60';
  END;
  DROP _age;

RUN;

%m_check_obs(DSN=work.clients_std, CONTEXT=02_standardise_identity);

%PUT NOTE: [02_standardise_identity] Standardised %SYSFUNC(attrn(%SYSFUNC(open(work.clients_std)),NOBS)) records.;
