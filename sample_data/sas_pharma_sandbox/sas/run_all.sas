/* run_all.sas - driver. */
%include "./sas/00_setup.sas";
%include "./sas/01_build_sdtm_dm.sas";
%include "./sas/02_build_sdtm_ex.sas";
%include "./sas/03_build_sdtm_ae.sas";
%include "./sas/04_build_sdtm_lb.sas";
%include "./sas/05_build_adam_adsl.sas";
