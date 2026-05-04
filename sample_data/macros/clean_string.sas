%macro clean_string(val);
    %sysfunc(strip(%sysfunc(upcase(&val))))
%mend;
