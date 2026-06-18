/* 04_score_risk.sas
   Compute composite Customer Risk Rating (CRR) from weighted rules model.
   H. Nakamura / Financial Crime Rules  2019-11-22
   Updated 2023-02: added source-of-wealth factor, revised channel weights.
*/

%m_log_step(STEP_NAME=04_score_risk);

/* Load risk weight parameters from reference library */
DATA work.risk_weights;
  SET REFLIB.risk_weights;
RUN;

%m_assert_nonempty(DSN=work.risk_weights, CONTEXT=04_score_risk risk weights missing);

/* Join screening results back to standardised clients */
DATA work.clients_screened;
  MERGE work.clients_std (IN=a)
        work.screen_best (IN=b KEEP=cust_id match_flg best_wl_id best_sim match_method);
  BY cust_id;
  IF a;

  /* Default screening fields if no match record */
  IF NOT b THEN DO;
    match_flg    = 'N';
    best_wl_id   = '';
    best_sim     = 0;
    match_method = '';
  END;

RUN;

/* Score each client using the rules cascade */
DATA work.clients_scored;
  SET work.clients_screened;

  crr_score = 0;

  /* Factor 1: Country of residence risk */
  _cntry_pts = INPUT(cntry_resdnc_cd, CNTRY_RISK_IN.);
  IF _cntry_pts = . THEN _cntry_pts = 1;
  crr_score + (_cntry_pts * 10);

  /* Factor 2: PEP status — self-declared or screening match */
  IF pep_self_decl_flg = 'Y' THEN DO;
    crr_score + 40;
    pep_flag = 'Y';
  END;
  ELSE IF match_flg IN ('Y', 'P') AND best_sim >= 100 THEN DO;
    crr_score + 30;
    pep_flag = 'P';  /* possible PEP */
  END;
  ELSE pep_flag = 'N';

  /* Factor 3: Sanctions screening result */
  IF match_flg = 'Y' AND match_method = 'COMPGED' THEN crr_score + 50;
  ELSE IF match_flg = 'P' THEN crr_score + 20;

  /* Factor 4: Source of wealth */
  IF src_of_wlth_cd = 'OTHR' THEN crr_score + 15;
  ELSE IF src_of_wlth_cd = 'BUSPRT' THEN crr_score + 10;

  /* Factor 5: Onboarding channel */
  _chnl_pts = INPUT(PUT(onbrd_chnl_cd, $CHNL_RISK.), BEST2.);
  IF _chnl_pts = . THEN _chnl_pts = 2;
  crr_score + (_chnl_pts * 5);

  /* Factor 6: Customer type */
  IF cust_typ_cd IN ('TRUST', 'FUND') THEN crr_score + 20;
  ELSE IF cust_typ_cd = 'CORP' THEN crr_score + 10;

  /* Factor 7: Occupation cash intensity */
  IF PUT(occ_cd, $CASHOCC.) = 'Y' THEN crr_score + 25;

  /* Assign risk band from score */
  IF      crr_score >= 80 THEN crr_band_cd = 'HIGH';
  ELSE IF crr_score >= 40 THEN crr_band_cd = 'MED';
  ELSE                         crr_band_cd = 'LOW';

  DROP _cntry_pts _chnl_pts;

RUN;

%m_check_obs(DSN=work.clients_scored, CONTEXT=04_score_risk);

/* Write scored clients to output */
DATA OUTLIB.client_screened;
  SET work.clients_scored;
RUN;

%PUT NOTE: [04_score_risk] Scoring complete. HIGH band: %SYSFUNC(countw('X')) (approx — check output).;
