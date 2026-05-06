/* 06_summary_stats.sas - PROC SORT + PROC MEANS */
%include "&root./sas/autoexec.sas";

proc sort data=outdir.customer_revenue_daily
          out=work.revenue_sorted;
    by SEGMENT_CLEAN COUNTRY_CLEAN;
run;

proc means data=work.revenue_sorted noprint;
    class SEGMENT_CLEAN COUNTRY_CLEAN;
    var TOTAL_EUR;
    output out=outdir.revenue_summary
        n=N_ROWS
        mean=MEAN_EUR
        sum=SUM_EUR
        min=MIN_EUR
        max=MAX_EUR;
run;
