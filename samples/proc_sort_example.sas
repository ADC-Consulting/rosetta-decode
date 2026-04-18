/* proc_sort_example.sas
   Purpose: Demonstrate PROC SORT extraction — two sort variants plus a %LET macro variable.
*/

%LET sort_dept = department;

/* Step 1: Add annual_bonus column */
DATA employees_work;
    SET employees_raw;
    annual_bonus = salary * 0.10;
RUN;

/* Step 2: Sort with explicit OUT= dataset — BY two columns */
PROC SORT DATA=employees_work OUT=employees_by_dept;
    BY &sort_dept salary;
RUN;

/* Step 3: Sort in place — no OUT=, DESCENDING column */
PROC SORT DATA=employees_by_dept;
    BY DESCENDING salary;
RUN;
