/* 04_build_sdtm_lb.sas - raw -> SDTM.LB
   Difficulties: Latin-1 input encoding, char->numeric coercion, missing
   numerics, PROC TRANSPOSE wide pivot. */
filename lbcsv "./data/raw/lb_raw.csv" encoding="latin1";

proc import datafile=lbcsv out=work.lb_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

data sdtm.lb;
    length USUBJID $40;
    set work.lb_raw;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    LBDT = input(LBDTC, yymmdd10.);
    if missing(LBORRES) then LBSTRESN = .;
    else LBSTRESN = input(LBORRES, best12.);
    format LBDT yymmdd10.;
run;

proc transpose data=sdtm.lb out=work.lb_wide(drop=_NAME_) prefix=LB_;
    by USUBJID VISIT;
    id LBTESTCD;
    var LBSTRESN;
run;
