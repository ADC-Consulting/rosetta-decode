/* ============================================================
   PROC IML fixture: risk scoring via matrix operations
   SAS: samples/sas_project/05_risk_scoring_iml.sas:1
   ============================================================ */

/* Input: scored employees dataset with numeric features */
DATA work.scored;
    INFILE DATALINES DELIMITER=',' DSD;
    INPUT employee_id age tenure score;
    DATALINES;
1001,35,5,0.72
1002,28,2,0.55
1003,42,10,0.88
1004,23,1,0.31
;
RUN;

/* Compute risk tier using IML matrix math */
PROC IML;
    USE work.scored;
    READ ALL VAR {score} INTO scores;
    CLOSE work.scored;

    /* Risk thresholds */
    high_thresh = 0.75;
    low_thresh  = 0.50;

    n = NROW(scores);
    tier = J(n, 1, 0);        /* pre-allocate column vector */

    DO i = 1 TO n;
        IF scores[i] >= high_thresh THEN tier[i] = 3;   /* high   */
        ELSE IF scores[i] >= low_thresh THEN tier[i] = 2; /* medium */
        ELSE tier[i] = 1;                                 /* low    */
    END;

    /* Combine back into a dataset */
    USE work.scored;
    READ ALL VAR {employee_id} INTO ids;
    CLOSE work.scored;

    result = ids || tier;
    CREATE work.risk_tiers FROM result [COLNAME={"employee_id" "risk_tier"}];
    APPEND FROM result;
    CLOSE work.risk_tiers;
QUIT;

/* Display results */
PROC PRINT DATA=work.risk_tiers; RUN;
