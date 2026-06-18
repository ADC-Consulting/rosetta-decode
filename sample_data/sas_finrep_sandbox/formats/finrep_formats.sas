/* finrep_formats.sas — FinRep value formats for Apex Capital
   Standard PROC FORMAT definitions for regulatory exposure reporting.
*/
PROC FORMAT LIBRARY=FMTLIB;

  /* External rating to rating band */
  VALUE $RATINGBAND
    'AAA', 'AA'        = 'IG_PRIME'
    'A', 'BBB'         = 'IG_STANDARD'
    'SUB_IG'           = 'NON_IG'
    'NR'               = 'UNRATED'
    OTHER              = 'UNKNOWN'
  ;

  /* Asset class display labels */
  VALUE $ASSETLBL
    'CORP'    = 'Corporate Bond'
    'SVRN'    = 'Sovereign'
    'ABS'     = 'Asset-Backed Security'
    'CVRDBND' = 'Covered Bond'
    OTHER     = 'Other'
  ;

  /* Desk display names */
  VALUE $DESKLBL
    'DESK-IG' = 'Investment Grade'
    'DESK-HY' = 'High Yield'
    'DESK-EM' = 'Emerging Markets'
    OTHER     = 'Other'
  ;

  /* DV01 risk bucket — range-based */
  VALUE DV01BUCK
    LOW   -< 1000   = 'MICRO'
    1000  -< 10000  = 'SMALL'
    10000 -< 100000 = 'MEDIUM'
    100000 - HIGH   = 'LARGE'
    OTHER           = 'UNKNOWN'
  ;

  /* Sector labels for counterparty */
  VALUE $SECTORLBL
    'FINAN' = 'Financial Institution'
    'CORP'  = 'Corporate'
    'SOVGN' = 'Sovereign / Supranational'
    'SUPRA' = 'Supranational'
    OTHER   = 'Other'
  ;

RUN;
