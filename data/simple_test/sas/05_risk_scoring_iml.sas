/* 05_risk_scoring_iml.sas
   Descriptive stats on daily revenue: mean, sample std, z-score with zero guard. */
%include "&root./sas/autoexec.sas";

proc iml;
    use outdir.customer_revenue_daily;
    read all var {CUSTOMER_ID DATE TOTAL_EUR} into X[colname=vars];
    close outdir.customer_revenue_daily;

    revenue  = X[, 3];
    mean_rev = mean(revenue);
    std_rev  = std(revenue);
    if std_rev = 0 then std_rev = 1;

    z   = (revenue - mean_rev) / std_rev;
    out = X || z;

    create outdir.customer_revenue_zscore
        from out[colname={"CUSTOMER_ID" "DATE" "TOTAL_EUR" "Z_SCORE"}];
    append from out;
    close outdir.customer_revenue_zscore;
quit;
