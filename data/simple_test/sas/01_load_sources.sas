/* 01_load_sources.sas - import CSV/XLSX sources */
%include "&root./sas/autoexec.sas";

proc import datafile=csvcust out=rawdir.customers dbms=csv replace;
    guessingrows=max;
run;

proc import datafile=csvtx out=rawdir.transactions dbms=csv replace;
    guessingrows=max;
run;

proc import datafile=csvfx out=rawdir.exchange_rates dbms=csv replace;
    guessingrows=max;
run;

proc import datafile=xlsprod out=rawdir.products dbms=xlsx replace;
    sheet="Sheet1"; getnames=yes;
run;
