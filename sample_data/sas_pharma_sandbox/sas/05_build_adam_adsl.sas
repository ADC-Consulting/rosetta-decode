/* 05_build_adam_adsl.sas - SDTM -> ADaM ADSL (MAIN RECONCILIATION TARGET)
   Exercises: macros, PROC SQL HAVING, BY-merge with IN=, INTCK,
   PROC FORMAT/PUT, %put logging, retain for variable order. */

%m_first_dose(in=sdtm.ex, out=work.dose);

proc sql;
    create table work.aesum as
    select  USUBJID,
            min(AESTDT) as FIRSTAEDT format=yymmdd10.,
            max(AESEV)  as MAXAEGR
    from sdtm.ae
    group by USUBJID
    having count(*) >= 1;
quit;

proc sort data=sdtm.dm;   by STUDYID SITEID SUBJID; run;
proc sort data=work.dose; by STUDYID SITEID SUBJID; run;

data work.adsl_pre;
    length USUBJID $40 SAFFL $1 ITTFL $1 TRT01P $40 TRT01A $40;
    merge sdtm.dm(in=indm) work.dose(in=indose);
    by STUDYID SITEID SUBJID;
    if indm;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    if not missing(TRTSDT) and not missing(TRTEDT) then
        TRTDURD = intck('day', TRTSDT, TRTEDT) + 1;
    SAFFL  = 'Y';
    ITTFL  = 'Y';
    TRT01P = ARM;
    TRT01A = ACTARM;
run;

%m_derive_age_group(in=work.adsl_pre, out=work.adsl_age, agevar=AGE, grpvar=AGEGR1);

proc sort data=work.adsl_age; by USUBJID; run;
proc sort data=work.aesum;    by USUBJID; run;

data adam.adsl;
    length AGEGR1 $8;
    merge work.adsl_age(in=ina) work.aesum(in=inb);
    by USUBJID;
    if ina;
run;

data adam.adsl;
    retain USUBJID STUDYID SUBJID SITEID
           ARM TRT01P TRT01A
           AGE AGEU AGEGR1 SEX RACE
           TRTSDT TRTEDT TRTDURD
           SAFFL ITTFL DTHFL FIRSTAEDT MAXAEGR;
    set adam.adsl;
    keep USUBJID STUDYID SUBJID SITEID
         ARM TRT01P TRT01A
         AGE AGEU AGEGR1 SEX RACE
         TRTSDT TRTEDT TRTDURD
         SAFFL ITTFL DTHFL FIRSTAEDT MAXAEGR;
run;

proc export data=adam.adsl
            outfile="./data/adam/adsl_actual.csv"
            dbms=csv replace;
run;

%put NOTE: ADSL build complete. N subjects = &SYSNOBS..;
