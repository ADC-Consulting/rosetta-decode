/* 02_clean_customers.sas */
%include "&root./sas/autoexec.sas";
%include "&root./macros/clean_string.sas";
%include "&root./macros/assert_rowcount.sas";

data rawdir.customers_clean;
    set rawdir.customers;
    if missing(CUSTOMER_ID) then delete;
    COUNTRY_CLEAN = %clean_string(COUNTRY);
    SEGMENT_CLEAN = %clean_string(SEGMENT);
run;

%assert_rowcount(rawdir.customers_clean, 1);
