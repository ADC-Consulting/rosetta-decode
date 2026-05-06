/* 03_clean_transactions.sas */
%include "&root./sas/autoexec.sas";
%include "&root./macros/assert_rowcount.sas";

data rawdir.transactions_clean;
    set rawdir.transactions;
    if missing(CUSTOMER_ID) then delete;
    if missing(CURRENCY)    then delete;
    if AMOUNT_LOCAL <= 0    then delete;
run;

%assert_rowcount(rawdir.transactions_clean, 1);
