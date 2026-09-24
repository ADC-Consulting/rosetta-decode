/* 02_build_sdtm_ex.sas - raw -> SDTM.EX
   Difficulty: dedup duplicate dosing rows (PROC SORT NODUPKEY). */
proc import datafile="./data/raw/ex_raw.csv"
            out=work.ex_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

proc sort data=work.ex_raw out=work.ex_dedup nodupkey;
    by STUDYID SUBJID SITEID EXSTDTC EXENDTC EXTRT EXDOSE;
run;

data sdtm.ex;
    length USUBJID $40;
    set work.ex_dedup;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    EXSTDT = input(EXSTDTC, yymmdd10.);
    EXENDT = input(EXENDTC, yymmdd10.);
    format EXSTDT EXENDT yymmdd10.;
run;
