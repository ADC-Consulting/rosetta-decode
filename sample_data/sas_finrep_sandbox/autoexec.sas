/* autoexec.sas — Apex Capital Management FinRep batch environment
   Infrastructure: J. Kowalski / Platform Engineering
   Last revised: 2019-04-02
*/
OPTIONS COMPRESS=YES NOFMTERR NOSYMBOLGEN MPRINT NOMLOGIC;
OPTIONS LINESIZE=132 PAGESIZE=MAX CENTER NODATE;

%LET RUN_ENV    = PRD;
%LET BATCH_ROOT = \\apx-sas-prod\data;

LIBNAME RAWLIB  "&BATCH_ROOT.\raw\&RUN_DT.";
LIBNAME STAGLIB "&BATCH_ROOT.\staging";
LIBNAME OUTLIB  "&BATCH_ROOT.\output\&RUN_DT.";
LIBNAME FMTLIB  "\\apx-sas-prod\formats";

OPTIONS FMTSEARCH=(FMTLIB WORK);
