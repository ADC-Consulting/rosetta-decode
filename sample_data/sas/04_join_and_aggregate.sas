/* 04_join_and_aggregate.sas - FX convert, enrich, aggregate */
%include "&root./sas/autoexec.sas";

proc sql;
    create table work.tx_fx as
    select t.CUSTOMER_ID,
           t.PRODUCT_ID,
           datepart(t.TX_DATE) as TX_DATE format=yymmdd10.,
           t.AMOUNT_LOCAL,
           t.CURRENCY,
           f.RATE_TO_EUR,
           (t.AMOUNT_LOCAL / f.RATE_TO_EUR) as AMOUNT_EUR
    from rawdir.transactions_clean as t
    inner join rawdir.exchange_rates as f
      on datepart(t.TX_DATE) = input(f.DATE, yymmdd10.)
     and t.CURRENCY = f.CURRENCY;
quit;

proc sql;
    create table work.tx_fx_cat as
    select x.*, p.CATEGORY
    from work.tx_fx as x
    left join rawdir.products as p
      on x.PRODUCT_ID = p.PRODUCT_ID;
quit;

proc sql;
    create table outdir.customer_revenue_daily as
    select c.CUSTOMER_ID,
           x.TX_DATE as DATE,
           sum(x.AMOUNT_EUR) as TOTAL_EUR,
           c.COUNTRY_CLEAN,
           c.SEGMENT_CLEAN,
           c.IS_ACTIVE
    from work.tx_fx_cat as x
    inner join rawdir.customers_clean as c
      on x.CUSTOMER_ID = c.CUSTOMER_ID
    group by c.CUSTOMER_ID, x.TX_DATE, c.COUNTRY_CLEAN, c.SEGMENT_CLEAN, c.IS_ACTIVE;
quit;

proc sql;
    create table outdir.category_revenue as
    select CATEGORY, sum(AMOUNT_EUR) as TOTAL_EUR
    from work.tx_fx_cat
    group by CATEGORY
    order by TOTAL_EUR desc;
quit;
