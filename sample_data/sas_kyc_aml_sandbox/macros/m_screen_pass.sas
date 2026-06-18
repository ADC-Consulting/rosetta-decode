/* m_screen_pass.sas
   Parameterised screening macro.
   Runs one pass of name-matching for a given watchlist type.
   Appends results to work.screen_results.
   T. Bergstrom / Financial Crime Technology  2021-06-30
*/

%MACRO m_screen_pass(WL_TYPE=, THRESHOLD=);

  %m_log_step(STEP_NAME=m_screen_pass_&WL_TYPE.);

  /* Set threshold based on watchlist type if not passed explicitly */
  %IF &THRESHOLD. = %THEN %DO;
    %IF &WL_TYPE. = SANCTION %THEN %LET THRESHOLD = 80;
    %ELSE %IF &WL_TYPE. = PEP    %THEN %LET THRESHOLD = 100;
    %ELSE                               %LET THRESHOLD = 120;
  %END;

  /* Screen onboarding records against this watchlist type */
  DATA work.screen_&WL_TYPE.;
    SET work.clients_std;

    /* Load watchlist subset for this type into hash */
    IF _N_ = 1 THEN DO;
      DECLARE HASH hwl(DATASET: "work.watchlist_&WL_TYPE.");
      hwl.DefineKey('wl_id');
      hwl.DefineData('wl_nm', 'wl_cntry_cd', 'list_src_cd');
      hwl.DefineDone();

      DECLARE HITER hwl_iter('hwl');
    END;

    /* Iterate over watchlist entries and score */
    match_flg    = 'N';
    best_wl_id   = '';
    best_sim     = 0;
    match_method = '';

    RC = hwl_iter.First();
    DO WHILE (RC = 0);
      /* Compute generalised edit distance */
      _ged = COMPGED(full_nm_upper, wl_nm, 'LN');
      _lev = COMPLEV(full_nm_upper, wl_nm, 'LN');
      _sdx = (SOUNDEX(full_nm_upper) = SOUNDEX(wl_nm));

      /* Similarity score: lower GED = better match (invert to 0-200 scale) */
      _sim = MAX(0, 200 - _ged);

      IF _sim >= &THRESHOLD. THEN DO;
        IF _sim > best_sim THEN DO;
          best_sim     = _sim;
          best_wl_id   = wl_id;
          match_flg    = 'Y';
          match_method = "COMPGED";
        END;
      END;
      ELSE IF _sdx = 1 AND _lev <= 3 THEN DO;
        IF _sim > best_sim THEN DO;
          best_sim     = _sim;
          best_wl_id   = wl_id;
          match_flg    = 'P';   /* possible match */
          match_method = "SOUNDEX+LEV";
        END;
      END;

      RC = hwl_iter.Next();
    END;

    wl_type_screened = "&WL_TYPE.";
    KEEP cust_id full_nm_upper match_flg best_wl_id best_sim match_method wl_type_screened;
  RUN;

  /* Append this pass to cumulative results */
  PROC APPEND BASE=work.screen_results DATA=work.screen_&WL_TYPE. FORCE;
  RUN;

%MEND m_screen_pass;
