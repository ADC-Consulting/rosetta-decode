# mypy: ignore-errors
"""build_sas_pharma_sandbox.py.

Generate a self-contained SAS->PySpark conversion test harness mimicking a
pharma SDTM/ADaM pipeline (500 subjects, deterministic).

Produces under ./sas_pharma_sandbox/:
    - data/raw/        synthetic EDC extracts (input CSVs)
    - data/sdtm/       empty (target for SAS run)
    - data/adam/       empty (target for SAS run)
    - data/golden/     adsl_expected.csv (reconciliation target)
    - sas/             SAS pipeline scripts to be converted
    - macros/          SAS macros
    - formats/         PROC FORMAT catalog
    - logs/            synthetic run_all.log
    - README.md        difficulty matrix and usage notes
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path("sas_pharma_sandbox")
SEED = 20260505
N_SUBJECTS = 500
STUDYID = "ADC-XYZ-001"
SITES = ["001", "002", "003", "004", "005"]
ARMS = [("Placebo", "Placebo"), ("Drug X 50mg", "Drug X 50mg")]
RACES = ["WHITE", "BLACK OR AFRICAN AMERICAN", "ASIAN", "OTHER"]
SEXES = ["M", "F"]


def iso(d: date) -> str:
    """Format date as ISO YYYY-MM-DD."""
    return d.isoformat()


def ensure_dirs() -> None:
    """Create the full directory tree."""
    for sub in [
        "data/raw",
        "data/sdtm",
        "data/adam",
        "data/golden",
        "sas",
        "macros",
        "formats",
        "logs",
    ]:
        (ROOT / sub).mkdir(parents=True, exist_ok=True)


def generate_subjects() -> list[dict]:
    """Generate deterministic synthetic subject records."""
    rng = random.Random(SEED)
    subjects: list[dict] = []
    for i in range(1, N_SUBJECTS + 1):
        subjid = f"{i:04d}"
        site = rng.choice(SITES)
        usubjid = f"{STUDYID}-{site}-{subjid}"
        arm_p, arm_a = rng.choice(ARMS)
        sex = rng.choice(SEXES)
        race = rng.choices(RACES, weights=[0.55, 0.20, 0.15, 0.10])[0]
        age = rng.randint(18, 85)
        trtsdt = date(2025, 1, 1) + timedelta(days=rng.randint(0, 300))
        trtdurd = rng.randint(7, 84)
        trtedt = trtsdt + timedelta(days=trtdurd - 1)
        is_dead = rng.random() < 0.03
        dthdt = (trtsdt + timedelta(days=rng.randint(5, 120))) if is_dead else None

        n_ae = rng.choices([0, 1, 2, 3, 4, 5, 6], weights=[20, 25, 20, 15, 10, 6, 4])[0]
        aes = []
        for _ in range(n_ae):
            ae_start = trtsdt + timedelta(days=rng.randint(0, max(1, trtdurd + 30)))
            sev = rng.choices([1, 2, 3, 4, 5], weights=[40, 30, 18, 8, 4])[0]
            aes.append(
                {
                    "AESTDTC": ae_start,
                    "AESEV": sev,
                    "AETERM": rng.choice(
                        ["HEADACHE", "NAUSEA", "FATIGUE", "RASH", "DIARRHOEA", "DIZZINESS"]
                    ),
                }
            )

        labs = []
        visits = ["SCREENING", "BASELINE", "WEEK 2", "WEEK 4", "WEEK 8", "EOT"]
        tests = [
            ("ALT", "U/L", 10, 60),
            ("AST", "U/L", 10, 55),
            ("CREAT", "umol/L", 50, 110),
            ("HGB", "g/dL", 11, 17),
        ]
        for v_idx, v in enumerate(visits):
            v_date = trtsdt + timedelta(days=v_idx * 14 - 14)
            for tname, tunit, lo, hi in tests:
                if rng.random() < 0.02:
                    val = None
                else:
                    val = round(rng.uniform(lo * 0.6, hi * 1.4), 2)
                labs.append(
                    {
                        "VISIT": v,
                        "LBDTC": v_date,
                        "LBTESTCD": tname,
                        "LBORRES": val,
                        "LBORRESU": tunit,
                    }
                )

        vitals = []
        for v_idx, v in enumerate(visits[:4]):
            v_date = trtsdt + timedelta(days=v_idx * 14 - 14)
            vitals.append(
                {
                    "VISIT": v,
                    "VSDTC": v_date,
                    "VSTESTCD": "SYSBP",
                    "VSORRES": rng.randint(95, 160),
                    "VSORRESU": "mmHg",
                }
            )

        n_ex = rng.choices([1, 2, 3], weights=[70, 25, 5])[0]
        ex_records = []
        for j in range(n_ex):
            ex_start = trtsdt + timedelta(days=j * 14)
            ex_end = min(ex_start + timedelta(days=13), trtedt)
            ex_records.append(
                {
                    "EXSTDTC": ex_start,
                    "EXENDTC": ex_end,
                    "EXTRT": arm_a,
                    "EXDOSE": 0 if arm_p == "Placebo" else 50,
                }
            )
        # Inject duplicate dosing row for ~2% of subjects (difficulty: dedup)
        if rng.random() < 0.02 and ex_records:
            ex_records.append(dict(ex_records[0]))

        subjects.append(
            {
                "USUBJID": usubjid,
                "STUDYID": STUDYID,
                "SUBJID": subjid,
                "SITEID": site,
                "ARM": arm_p,
                "ACTARM": arm_a,
                "SEX": sex,
                "RACE": race,
                "AGE": age,
                "TRTSDT": trtsdt,
                "TRTEDT": trtedt,
                "TRTDURD": trtdurd,
                "DTHFL": "Y" if is_dead else "N",
                "DTHDT": dthdt,
                "SAFFL": "Y",
                "ITTFL": "Y",
                "AES": aes,
                "LABS": labs,
                "VITALS": vitals,
                "EX": ex_records,
            }
        )
    return subjects


def write_raw_csvs(subjects: list[dict]) -> None:
    """Write raw EDC-style input CSVs (with deliberate encoding quirks)."""
    raw = ROOT / "data/raw"

    # DM raw - UTF-8 BOM (encoding difficulty)
    with open(raw / "dm_raw.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "STUDYID",
                "SUBJID",
                "SITEID",
                "ARM",
                "ACTARM",
                "SEX",
                "RACE",
                "AGE",
                "AGEU",
                "RFSTDTC",
                "DTHDTC",
                "DTHFL",
            ]
        )
        for s in subjects:
            w.writerow(
                [
                    s["STUDYID"],
                    s["SUBJID"],
                    s["SITEID"],
                    s["ARM"],
                    s["ACTARM"],
                    s["SEX"],
                    s["RACE"],
                    s["AGE"],
                    "YEARS",
                    iso(s["TRTSDT"]),
                    iso(s["DTHDT"]) if s["DTHDT"] else "",
                    s["DTHFL"],
                ]
            )

    with open(raw / "ex_raw.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["STUDYID", "SUBJID", "SITEID", "EXTRT", "EXDOSE", "EXSTDTC", "EXENDTC"])
        for s in subjects:
            for ex in s["EX"]:
                w.writerow(
                    [
                        s["STUDYID"],
                        s["SUBJID"],
                        s["SITEID"],
                        ex["EXTRT"],
                        ex["EXDOSE"],
                        iso(ex["EXSTDTC"]),
                        iso(ex["EXENDTC"]),
                    ]
                )

    with open(raw / "ae_raw.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["STUDYID", "SUBJID", "SITEID", "AETERM", "AESEV", "AESTDTC"])
        for s in subjects:
            for ae in s["AES"]:
                w.writerow(
                    [
                        s["STUDYID"],
                        s["SUBJID"],
                        s["SITEID"],
                        ae["AETERM"],
                        ae["AESEV"],
                        iso(ae["AESTDTC"]),
                    ]
                )

    # LB raw - Latin-1 (encoding difficulty)
    with open(raw / "lb_raw.csv", "w", encoding="latin-1", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "STUDYID",
                "SUBJID",
                "SITEID",
                "VISIT",
                "LBDTC",
                "LBTESTCD",
                "LBORRES",
                "LBORRESU",
            ]
        )
        for s in subjects:
            for lb in s["LABS"]:
                w.writerow(
                    [
                        s["STUDYID"],
                        s["SUBJID"],
                        s["SITEID"],
                        lb["VISIT"],
                        iso(lb["LBDTC"]),
                        lb["LBTESTCD"],
                        "" if lb["LBORRES"] is None else lb["LBORRES"],
                        lb["LBORRESU"],
                    ]
                )

    with open(raw / "vs_raw.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "STUDYID",
                "SUBJID",
                "SITEID",
                "VISIT",
                "VSDTC",
                "VSTESTCD",
                "VSORRES",
                "VSORRESU",
            ]
        )
        for s in subjects:
            for v in s["VITALS"]:
                w.writerow(
                    [
                        s["STUDYID"],
                        s["SUBJID"],
                        s["SITEID"],
                        v["VISIT"],
                        iso(v["VSDTC"]),
                        v["VSTESTCD"],
                        v["VSORRES"],
                        v["VSORRESU"],
                    ]
                )


def write_golden_adsl(subjects: list[dict]) -> None:
    """Write the deterministic golden ADSL CSV."""
    out = ROOT / "data/golden/adsl_expected.csv"
    cols = [
        "USUBJID",
        "STUDYID",
        "SUBJID",
        "SITEID",
        "ARM",
        "TRT01P",
        "TRT01A",
        "AGE",
        "AGEU",
        "AGEGR1",
        "SEX",
        "RACE",
        "TRTSDT",
        "TRTEDT",
        "TRTDURD",
        "SAFFL",
        "ITTFL",
        "DTHFL",
        "FIRSTAEDT",
        "MAXAEGR",
    ]

    def agegr1(age: int) -> str:
        if age < 18:
            return "<18"
        if age < 65:
            return "18-64"
        if age < 75:
            return "65-74"
        return ">=75"

    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for s in sorted(subjects, key=lambda x: x["USUBJID"]):
            first_ae = min((ae["AESTDTC"] for ae in s["AES"]), default=None)
            max_gr = max((ae["AESEV"] for ae in s["AES"]), default=None)
            w.writerow(
                [
                    s["USUBJID"],
                    s["STUDYID"],
                    s["SUBJID"],
                    s["SITEID"],
                    s["ARM"],
                    s["ARM"],
                    s["ACTARM"],
                    s["AGE"],
                    "YEARS",
                    agegr1(s["AGE"]),
                    s["SEX"],
                    s["RACE"],
                    iso(s["TRTSDT"]),
                    iso(s["TRTEDT"]),
                    s["TRTDURD"],
                    s["SAFFL"],
                    s["ITTFL"],
                    s["DTHFL"],
                    iso(first_ae) if first_ae else "",
                    "" if max_gr is None else max_gr,
                ]
            )


def write_sas_code() -> None:
    """Write all SAS scripts, macros, and the format catalog."""
    (ROOT / "formats/pharma_formats.sas").write_text(
        """/* pharma_formats.sas - PROC FORMAT catalog
   Difficulty: format catalogs must be re-implemented as when/otherwise or
   broadcast lookups in PySpark. */
libname library "./formats";

proc format library=library;
    value agegr1f
        low  -<  18  = '<18'
        18   -<  65  = '18-64'
        65   -<  75  = '65-74'
        75   -  high = '>=75';

    value $sexdec
        'M' = 'Male'
        'F' = 'Female'
        other = 'Unknown';

    value aegrf
        1 = 'Mild'
        2 = 'Moderate'
        3 = 'Severe'
        4 = 'Life-threatening'
        5 = 'Fatal';
run;
"""
    )

    (ROOT / "macros/m_derive_age_group.sas").write_text(
        """/* m_derive_age_group.sas - macro using %if/%do, PUT with format. */
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
"""
    )

    (ROOT / "macros/m_first_dose.sas").write_text(
        """/* m_first_dose.sas - PROC SQL inside macro, dedup, MIN/MAX aggregation. */
%macro m_first_dose(in=, out=);
    proc sql;
        create table &out as
        select  STUDYID, SUBJID, SITEID,
                min(EXSTDTC) as TRTSDT format=yymmdd10.,
                max(EXENDTC) as TRTEDT format=yymmdd10.
        from (select distinct STUDYID, SUBJID, SITEID, EXSTDTC, EXENDTC
              from &in)
        group by STUDYID, SUBJID, SITEID;
    quit;
%mend m_first_dose;
"""
    )

    (ROOT / "macros/m_safety_flag.sas").write_text(
        """/* m_safety_flag.sas - returns a value via %let in caller's scope. */
%macro m_safety_flag(dosed=);
    %global SAFETY_RESULT;
    %if &dosed = 1 %then %let SAFETY_RESULT = Y;
    %else %let SAFETY_RESULT = N;
%mend m_safety_flag;
"""
    )

    (ROOT / "macros/m_merge_check.sas").write_text(
        """/* m_merge_check.sas - BY merge with IN= flags (inner join semantics). */
%macro m_merge_check(a=, b=, out=, by=USUBJID);
    proc sort data=&a; by &by; run;
    proc sort data=&b; by &by; run;

    data &out;
        merge &a(in=ina) &b(in=inb);
        by &by;
        if ina and inb;
    run;
%mend m_merge_check;
"""
    )

    (ROOT / "sas/00_setup.sas").write_text(
        """/* 00_setup.sas - libnames, options, format catalog, macro includes. */
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
"""
    )

    (ROOT / "sas/01_build_sdtm_dm.sas").write_text(
        """/* 01_build_sdtm_dm.sas - raw -> SDTM.DM
   Difficulties: UTF-8 BOM input, LENGTH truncation, ISO date parsing. */
proc import datafile="./data/raw/dm_raw.csv"
            out=work.dm_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

data sdtm.dm;
    length USUBJID $40 STUDYID $20 SUBJID $8 SITEID $4
           ARM $40 ACTARM $40 SEX $1 RACE $40 AGEU $8 DTHFL $1;
    set work.dm_raw;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    RFSTDT = input(RFSTDTC, yymmdd10.);
    if not missing(DTHDTC) then DTHDT = input(DTHDTC, yymmdd10.);
    format RFSTDT DTHDT yymmdd10.;
    keep USUBJID STUDYID SUBJID SITEID ARM ACTARM SEX RACE AGE AGEU
         RFSTDT DTHDT DTHFL;
run;
"""
    )

    (ROOT / "sas/02_build_sdtm_ex.sas").write_text(
        """/* 02_build_sdtm_ex.sas - raw -> SDTM.EX
   Difficulty: dedup duplicate dosing rows (PROC SORT NODUPKEY). */
proc import datafile="./data/raw/ex_raw.csv"
            out=work.ex_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

proc sort data=work.ex_raw out=work.ex_dedup nodupkey;
    by STUDYID SUBJID SITEID EXSTDTC EXENDTC EXTRT EXDOSE;
run;

data sdtm.ex;
    length USUBJID $40;
    set work.ex_dedup;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    EXSTDT = input(EXSTDTC, yymmdd10.);
    EXENDT = input(EXENDTC, yymmdd10.);
    format EXSTDT EXENDT yymmdd10.;
run;
"""
    )

    (ROOT / "sas/03_build_sdtm_ae.sas").write_text(
        """/* 03_build_sdtm_ae.sas - raw -> SDTM.AE
   Difficulties: RETAIN + BY + FIRST., implicit row-sequence accumulator. */
proc import datafile="./data/raw/ae_raw.csv"
            out=work.ae_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

proc sort data=work.ae_raw; by STUDYID SITEID SUBJID AESTDTC; run;

data sdtm.ae;
    length USUBJID $40 AESEVC $20;
    retain AESEQ;
    set work.ae_raw;
    by STUDYID SITEID SUBJID AESTDTC;
    if first.SUBJID then AESEQ = 0;
    AESEQ + 1;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    AESTDT = input(AESTDTC, yymmdd10.);
    AESEVC = put(AESEV, aegrf.);
    format AESTDT yymmdd10.;
run;
"""
    )

    (ROOT / "sas/04_build_sdtm_lb.sas").write_text(
        """/* 04_build_sdtm_lb.sas - raw -> SDTM.LB
   Difficulties: Latin-1 input encoding, char->numeric coercion, missing
   numerics, PROC TRANSPOSE wide pivot. */
filename lbcsv "./data/raw/lb_raw.csv" encoding="latin1";

proc import datafile=lbcsv out=work.lb_raw dbms=csv replace;
    getnames=yes;
    guessingrows=max;
run;

data sdtm.lb;
    length USUBJID $40;
    set work.lb_raw;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    LBDT = input(LBDTC, yymmdd10.);
    if missing(LBORRES) then LBSTRESN = .;
    else LBSTRESN = input(LBORRES, best12.);
    format LBDT yymmdd10.;
run;

proc transpose data=sdtm.lb out=work.lb_wide(drop=_NAME_) prefix=LB_;
    by USUBJID VISIT;
    id LBTESTCD;
    var LBSTRESN;
run;
"""
    )

    (ROOT / "sas/05_build_adam_adsl.sas").write_text(
        """/* 05_build_adam_adsl.sas - SDTM -> ADaM ADSL (MAIN RECONCILIATION TARGET)
   Exercises: macros, PROC SQL HAVING, BY-merge with IN=, INTCK,
   PROC FORMAT/PUT, %put logging, retain for variable order. */

%m_first_dose(in=sdtm.ex, out=work.dose);

proc sql;
    create table work.aesum as
    select  USUBJID,
            min(AESTDT) as FIRSTAEDT format=yymmdd10.,
            max(AESEV)  as MAXAEGR
    from sdtm.ae
    group by USUBJID
    having count(*) >= 1;
quit;

proc sort data=sdtm.dm;   by STUDYID SITEID SUBJID; run;
proc sort data=work.dose; by STUDYID SITEID SUBJID; run;

data work.adsl_pre;
    length USUBJID $40 SAFFL $1 ITTFL $1 TRT01P $40 TRT01A $40;
    merge sdtm.dm(in=indm) work.dose(in=indose);
    by STUDYID SITEID SUBJID;
    if indm;
    USUBJID = catx('-', STUDYID, SITEID, SUBJID);
    if not missing(TRTSDT) and not missing(TRTEDT) then
        TRTDURD = intck('day', TRTSDT, TRTEDT) + 1;
    SAFFL  = 'Y';
    ITTFL  = 'Y';
    TRT01P = ARM;
    TRT01A = ACTARM;
run;

%m_derive_age_group(in=work.adsl_pre, out=work.adsl_age, agevar=AGE, grpvar=AGEGR1);

proc sort data=work.adsl_age; by USUBJID; run;
proc sort data=work.aesum;    by USUBJID; run;

data adam.adsl;
    length AGEGR1 $8;
    merge work.adsl_age(in=ina) work.aesum(in=inb);
    by USUBJID;
    if ina;
run;

data adam.adsl;
    retain USUBJID STUDYID SUBJID SITEID
           ARM TRT01P TRT01A
           AGE AGEU AGEGR1 SEX RACE
           TRTSDT TRTEDT TRTDURD
           SAFFL ITTFL DTHFL FIRSTAEDT MAXAEGR;
    set adam.adsl;
    keep USUBJID STUDYID SUBJID SITEID
         ARM TRT01P TRT01A
         AGE AGEU AGEGR1 SEX RACE
         TRTSDT TRTEDT TRTDURD
         SAFFL ITTFL DTHFL FIRSTAEDT MAXAEGR;
run;

proc export data=adam.adsl
            outfile="./data/adam/adsl_actual.csv"
            dbms=csv replace;
run;

%put NOTE: ADSL build complete. N subjects = &SYSNOBS..;
"""
    )

    (ROOT / "sas/run_all.sas").write_text(
        """/* run_all.sas - driver. */
%include "./sas/00_setup.sas";
%include "./sas/01_build_sdtm_dm.sas";
%include "./sas/02_build_sdtm_ex.sas";
%include "./sas/03_build_sdtm_ae.sas";
%include "./sas/04_build_sdtm_lb.sas";
%include "./sas/05_build_adam_adsl.sas";
"""
    )


def write_log() -> None:
    """Write a synthetic SAS execution log."""
    (ROOT / "logs/run_all.log").write_text(
        """1    The SAS System

NOTE: SAS (r) Proprietary Software 9.4 (TS1M7)

NOTE: LIBNAME RAW refers to ./data/raw (readonly).
NOTE: LIBNAME SDTM refers to ./data/sdtm.
NOTE: LIBNAME ADAM refers to ./data/adam.
NOTE: Format catalog LIBRARY.FORMATS has been updated.

NOTE: 500 records were read from DM_RAW.
NOTE: The data set SDTM.DM has 500 observations and 13 variables.

NOTE: 612 records were read from EX_RAW.
WARNING: 11 duplicate observations removed by PROC SORT NODUPKEY.
NOTE: The data set SDTM.EX has 601 observations and 9 variables.

NOTE: 1043 records were read from AE_RAW.
NOTE: The data set SDTM.AE has 1043 observations and 8 variables.

NOTE: 12000 records were read from LB_RAW.
NOTE: Invalid numeric data, LBORRES=' ', at line 47 column 7.
NOTE: 240 missing values were generated as a result of performing an operation on missing values.
NOTE: The data set SDTM.LB has 12000 observations and 9 variables.

NOTE: %M_FIRST_DOSE executed successfully.
NOTE: %M_DERIVE_AGE_GROUP executed successfully.

NOTE: ADSL build complete. N subjects = 500.
NOTE: The data set ADAM.ADSL has 500 observations and 20 variables.

NOTE: SAS Institute Inc. -- end of run.
"""
    )


def write_readme() -> None:
    """Write the README describing the harness."""
    (ROOT / "README.md").write_text(
        """# SAS -> PySpark Conversion Test Harness (SDTM/ADaM)

Synthetic pharma pipeline used to evaluate an LLM agent that converts SAS
legacy code into PySpark.

## Layout
- `data/raw/`        synthetic EDC extracts (input)
- `data/sdtm/`       SDTM datasets (produced by SAS at runtime)
- `data/adam/`       ADaM datasets (produced by SAS at runtime)
- `data/golden/`     **adsl_expected.csv** = reconciliation target
- `sas/`             SAS code your agent must convert
- `macros/`          SAS macros
- `formats/`         PROC FORMAT catalog
- `logs/`            synthetic execution log

## Difficulties Embedded
1.  RETAIN + BY + FIRST./LAST.
2.  MERGE with IN= flags
3.  PROC FORMAT + PUT(x, fmt.)
4.  %macro / %if / %do / &var resolution
5.  SAS dates, INPUT(yymmdd10.), INTCK
6.  Implicit numeric<->char coercion
7.  PROC SQL with HAVING
8.  PROC TRANSPOSE
9.  Missing-value semantics (. vs '')
10. LENGTH controlling truncation
11. Sequence variables via accumulator (AESEQ + 1)
12. Log-only side effects (%put)
13. LIBNAME paths
14. Mixed encodings (UTF-8 BOM, Latin-1)
15. Duplicate dosing rows

## Reconciliation target
The agent's PySpark pipeline should produce `data/adam/adsl_actual.csv` with
the same rows and columns as `data/golden/adsl_expected.csv`.
"""
    )


def main() -> None:
    """Build the entire sandbox."""
    ensure_dirs()
    subjects = generate_subjects()
    write_raw_csvs(subjects)
    write_golden_adsl(subjects)
    write_sas_code()
    write_log()
    write_readme()


if __name__ == "__main__":
    main()
