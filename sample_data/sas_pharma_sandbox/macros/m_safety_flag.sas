/* m_safety_flag.sas - returns a value via %let in caller's scope. */
%macro m_safety_flag(dosed=);
    %global SAFETY_RESULT;
    %if &dosed = 1 %then %let SAFETY_RESULT = Y;
    %else %let SAFETY_RESULT = N;
%mend m_safety_flag;
