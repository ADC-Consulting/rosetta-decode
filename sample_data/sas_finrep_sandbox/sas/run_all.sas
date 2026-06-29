/* run_all.sas — FinRep Exposure Batch Entry Point
   Apex Capital Management — Fixed Income & Credit
   Owner: D. Sinclair / Batch Infrastructure
   Usage: Submit this file to run the full month-end exposure pipeline.
          Set RUN_DT before submitting (YYYYMMDD format).
*/

OPTIONS MPRINT MLOGIC SYMBOLGEN;   /* left from last debug session — should be removed before UAT */

/* ── Run parameters ── */
%LET RUN_DT = 20241231;

/* Derive period labels from run date */
%m_set_run_period;

/* ── Pipeline steps ── */
%INCLUDE "\\apx-sas-prod\batch\finrep\sas\01_load_positions.sas";
%INCLUDE "\\apx-sas-prod\batch\finrep\sas\02_load_reference.sas";
%INCLUDE "\\apx-sas-prod\batch\finrep\sas\03_enrich_positions.sas";
%INCLUDE "\\apx-sas-prod\batch\finrep\sas\04_aggregate_exposure.sas";
%INCLUDE "\\apx-sas-prod\batch\finrep\sas\05_produce_output.sas";

%PUT NOTE: [run_all] FinRep batch complete. Period: &PERIOD_LABEL.;
