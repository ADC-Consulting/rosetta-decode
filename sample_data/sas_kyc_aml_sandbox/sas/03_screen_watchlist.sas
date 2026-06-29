/* 03_screen_watchlist.sas
   Screen onboarding records against the consolidated sanctions / PEP / adverse-media watchlist.
   Uses in-memory hash objects for performance — avoids SQL join overhead at scale.
   T. Bergstrom / Financial Crime Technology  2021-06-30

   Matching approach:
     - Primary: COMPGED (generalised edit distance, language-normalised)
     - Secondary: SOUNDEX + COMPLEV (phonetic blocking + character-level distance)
     - Sanction threshold: 100, PEP threshold: 120, AdvMedia threshold: 150
*/

%m_log_step(STEP_NAME=03_screen_watchlist);

/* v1 SQL screen — replaced by hash 2023-06, kept for audit
PROC SQL;
  CREATE TABLE work.screen_v1 AS
  SELECT
    c.cust_id,
    c.full_nm_upper,
    w.wl_id,
    w.wl_nm,
    COMPGED(c.full_nm_upper, w.wl_nm) AS ged_score
  FROM work.clients_std c
  CROSS JOIN work.watchlist w
  WHERE COMPGED(c.full_nm_upper, w.wl_nm) < 100
  ;
QUIT;
*/

/* Pre-split watchlist by type for hash loading */
DATA work.watchlist_SANCTION work.watchlist_PEP work.watchlist_ADVMEDIA;
  SET work.watchlist_all;
  IF wl_typ_cd = 'SANCTION' THEN OUTPUT work.watchlist_SANCTION;
  ELSE IF wl_typ_cd = 'PEP'     THEN OUTPUT work.watchlist_PEP;
  ELSE IF wl_typ_cd = 'ADVMEDIA' THEN OUTPUT work.watchlist_ADVMEDIA;
RUN;

/* Initialise results accumulator */
DATA work.screen_results;
  LENGTH cust_id $15 full_nm_upper $100 match_flg $1 best_wl_id $15
         best_sim 8 match_method $20 wl_type_screened $10;
  STOP;
RUN;

/* Run screening passes — thresholds set per watchlist type
   Note: SANCTION threshold deliberately set lower (stricter) than PEP */
%m_screen_pass(WL_TYPE=SANCTION,  THRESHOLD=100);  /* strict: any near-match escalated */
%m_screen_pass(WL_TYPE=PEP,       THRESHOLD=120);
%m_screen_pass(WL_TYPE=ADVMEDIA,  THRESHOLD=120);

/* Keep best match per customer across all watchlist types */
PROC SORT DATA=work.screen_results;
  BY cust_id DESCENDING best_sim;
RUN;

DATA work.screen_best;
  SET work.screen_results;
  BY cust_id;
  IF FIRST.cust_id;
RUN;

%m_check_obs(DSN=work.screen_best, CONTEXT=03_screen_watchlist);

%PUT NOTE: [03_screen_watchlist] Screening complete. Matches: %SYSFUNC(attrn(%SYSFUNC(open(work.screen_best)),NOBS)).;
