/* kyc_formats.sas — KYC/AML value formats for Meridian Asset Partners
*/
PROC FORMAT LIBRARY=FMTLIB;

  /* Country risk tier — INVALUE (numeric input) */
  INVALUE CNTRY_RISK_IN
    'AF', 'IR', 'IQ', 'KP', 'SY', 'YE', 'LY', 'MM', 'SS'  = 5  /* FATF High Risk */
    'PK', 'JO', 'TN', 'NG', 'GH', 'UG', 'ZW', 'ML', 'NI'  = 4  /* Elevated */
    'RU', 'BY', 'CN', 'VN', 'TH', 'BR', 'MX', 'TR', 'ZA'  = 3  /* Medium-High */
    'IN', 'ID', 'PH', 'EG', 'MA', 'SA', 'AE', 'QA', 'KW'  = 2  /* Medium */
    OTHER                                                    = 1  /* Standard */
  ;

  /* Country risk label */
  VALUE $CNTRY_RISK_LBL
    'HIGH'     = 'High Risk Jurisdiction'
    'ELEVATED' = 'Elevated Risk'
    'MEDIUM'   = 'Medium Risk'
    'STANDARD' = 'Standard Risk'
    OTHER      = 'Unknown'
  ;

  /* Customer risk rating band */
  VALUE $CRRBAND
    'HIGH' = 'Enhanced Due Diligence Required'
    'MED'  = 'Standard Due Diligence'
    'LOW'  = 'Simplified Due Diligence'
    OTHER  = 'Unrated'
  ;

  /* Occupation cash-intensity flag */
  VALUE $CASHOCC
    'DEAL', 'GAMB', 'CASI', 'PAWN', 'CURR', 'REAG' = 'Y'
    OTHER                                            = 'N'
  ;

  /* Onboarding channel risk score */
  VALUE $CHNL_RISK
    'INTRO'   = '3'   /* Introduced via third party — highest channel risk */
    'DIGITAL' = '2'   /* Online onboarding — no in-person verification */
    'BRANCH'  = '1'   /* Face-to-face — lowest channel risk */
    OTHER     = '2'
  ;

  /* Source of wealth display labels */
  VALUE $SOWLBL
    'SAL'    = 'Salary / Employment'
    'INHRT'  = 'Inheritance'
    'BUSPRT' = 'Business Profits'
    'INVST'  = 'Investment Returns'
    'OTHR'   = 'Other / Not Stated'
    OTHER    = 'Unknown'
  ;

RUN;
