/* m_first_dose.sas - PROC SQL inside macro, dedup, MIN/MAX aggregation. */
%macro m_first_dose(in=, out=);
    proc sql;
        create table &out as
        select  STUDYID, SUBJID, SITEID,
                min(EXSTDTC) as TRTSDT format=yymmdd10.,
                max(EXENDTC) as TRTEDT format=yymmdd10.
        from (select distinct STUDYID, SUBJID, SITEID, EXSTDTC, EXENDTC
              from &in)
        group by STUDYID, SUBJID, SITEID;
    quit;
%mend m_first_dose;
