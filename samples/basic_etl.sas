/* basic_etl.sas
   Source: ADC Consulting demo dataset
   Purpose: Classify employees by salary band and compute department aggregates.
*/

/* ── Step 1: Load raw employees and derive salary band ───────────────────── */
DATA employees_classified;
    SET employees_raw;
    IF salary < 40000 THEN salary_band = 'LOW';
    ELSE IF salary < 80000 THEN salary_band = 'MID';
    ELSE salary_band = 'HIGH';
    annual_bonus = salary * 0.10;
    full_name = TRIM(first_name) || ' ' || TRIM(last_name);
    KEEP emp_id department salary salary_band annual_bonus full_name;
RUN;

/* ── Step 2: Aggregate by department ─────────────────────────────────────── */
PROC SQL;
    CREATE TABLE dept_summary AS
    SELECT
        department,
        COUNT(*)          AS headcount,
        SUM(salary)       AS total_salary,
        AVG(salary)       AS avg_salary,
        SUM(annual_bonus) AS total_bonus
    FROM employees_classified
    GROUP BY department;
QUIT;
