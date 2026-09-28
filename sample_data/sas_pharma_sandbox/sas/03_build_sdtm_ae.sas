/* 03_build_sdtm_ae.sas - raw -> SDTM.AE
   Difficulties: RETAIN + BY + FIRST., implicit row-sequence accumulator. */
proc import datafile="./data/raw/ae_raw.csv"
            out=work.ae_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

proc sort data=work.ae_raw; by STUDYID SITEID SUBJID AESTDTC; run;

data sdtm.ae;
    length USUBJID $40 AESEVC $20;
    retain AESEQ;
    set work.ae_raw;
    by STUDYID SITEID SUBJID AESTDTC;
    if first.SUBJID then AESEQ = 0;
    AESEQ + 1;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    AESTDT = input(AESTDTC, yymmdd10.);
    AESEVC = put(AESEV, aegrf.);
    format AESTDT yymmdd10.;
run;
