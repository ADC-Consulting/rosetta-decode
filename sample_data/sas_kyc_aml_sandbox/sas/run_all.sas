/* run_all.sas — KYC/AML Nightly Batch Entry Point
   Meridian Asset Partners — Financial Crime Compliance
   Owner: K. Ostrowski / Platform Engineering
   Usage: Set AS_OF_DT and submit this file.
*/

OPTIONS MPRINT MLOGIC SYMBOLGEN;   /* left from last debug session */

/* ── Run parameters ── */
%LET AS_OF_DT = 20241231;

/* Derive review window cutoffs from AS_OF_DT */
%m_set_review_window;

/* ── Pipeline steps ── */
%INCLUDE "\\mer-sas-prod\batch\kyc\sas\01_ingest_clients.sas";
%INCLUDE "\\mer-sas-prod\batch\kyc\sas\02_standardise_identity.sas";
%INCLUDE "\\mer-sas-prod\batch\kyc\sas\03_screen_watchlist.sas";
%INCLUDE "\\mer-sas-prod\batch\kyc\sas\04_score_risk.sas";
%INCLUDE "\\mer-sas-prod\batch\kyc\sas\05_maintain_scd.sas";
%INCLUDE "\\mer-sas-prod\batch\kyc\sas\06_build_edd_queue.sas";

%PUT NOTE: [run_all] KYC/AML batch complete. AS_OF_DT=&AS_OF_DT.;
