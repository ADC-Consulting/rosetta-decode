/* 01_build_sdtm_dm.sas - raw -> SDTM.DM
   Difficulties: UTF-8 BOM input, LENGTH truncation, ISO date parsing. */
proc import datafile="./data/raw/dm_raw.csv"
            out=work.dm_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

data sdtm.dm;
    length USUBJID $40 STUDYID $20 SUBJID $8 SITEID $4
           ARM $40 ACTARM $40 SEX $1 RACE $40 AGEU $8 DTHFL $1;
    set work.dm_raw;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    RFSTDT = input(RFSTDTC, yymmdd10.);
    if not missing(DTHDTC) then DTHDT = input(DTHDTC, yymmdd10.);
    format RFSTDT DTHDT yymmdd10.;
    keep USUBJID STUDYID SUBJID SITEID ARM ACTARM SEX RACE AGE AGEU
         RFSTDT DTHDT DTHFL;
run;
