/* 00_setup.sas - libnames, options, format catalog, macro includes. */
options mprint mlogic symbolgen source source2 nodate nonumber;

libname raw     "./data/raw" access=readonly;
libname sdtm    "./data/sdtm";
libname adam    "./data/adam";
libname library "./formats";

%include "./formats/pharma_formats.sas";
%include "./macros/m_derive_age_group.sas";
%include "./macros/m_first_dose.sas";
%include "./macros/m_safety_flag.sas";
%include "./macros/m_merge_check.sas";
