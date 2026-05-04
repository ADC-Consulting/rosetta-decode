options mprint mlogic symbolgen;

%let root = /path/to/sas_project;

libname rawdir "&root./data/raw";
libname outdir "&root./data/output";

filename csvcust  "&root./data/raw/customers.csv";
filename csvtx    "&root./data/raw/transactions.csv";
filename csvfx    "&root./data/raw/exchange_rates.csv";
filename xlsprod  "&root./data/raw/products.xlsx";
