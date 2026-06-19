/* m_derive_age_group.sas - macro using %if/%do, PUT with format. */
%macro m_derive_age_group(in=, out=, agevar=AGE, grpvar=AGEGR1);
    %if %length(&in) = 0 %then %do;
        %put ERROR: m_derive_age_group requires IN= dataset.;
        %return;
    %end;

    data &out;
        set &in;
        length &grpvar $8;
        &grpvar = put(&agevar, agegr1f.);
    run;
%mend m_derive_age_group;
