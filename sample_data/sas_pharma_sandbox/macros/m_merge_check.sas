/* m_merge_check.sas - BY merge with IN= flags (inner join semantics). */
%macro m_merge_check(a=, b=, out=, by=USUBJID);
    proc sort data=&a; by &by; run;
    proc sort data=&b; by &by; run;

    data &out;
        merge &a(in=ina) &b(in=inb);
        by &by;
        if ina and inb;
    run;
%mend m_merge_check;
