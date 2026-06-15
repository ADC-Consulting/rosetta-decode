"""Generate SAS XPORT (.xpt) files with realistic clinical trial metadata.

Run with: uv run python data/medium_test/generate_xport.py
Output files land in data/medium_test/sas_pharma_sandbox/data/raw/
"""

import pathlib
import pyreadstat
import pandas as pd

OUT = pathlib.Path(__file__).parent / "sas_pharma_sandbox" / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)


def write(name: str, df: pd.DataFrame, labels: dict[str, str], formats: dict[str, str]) -> None:
    path = OUT / f"{name}.xpt"
    pyreadstat.write_xport(df, str(path), column_labels=labels, variable_format=formats)
    print(f"  wrote {path.name}  ({len(df)} rows, {len(df.columns)} cols)")


# ── DM_RAW — Demographics ────────────────────────────────────────────────────
dm = pd.DataFrame({
    "STUDYID": ["ADC-XYZ-001"] * 5,
    "SUBJID":  ["0001", "0002", "0003", "0004", "0005"],
    "SITEID":  ["003", "002", "001", "003", "002"],
    "ARM":     ["Drug X 50mg", "Placebo", "Drug X 50mg", "Placebo", "Drug X 50mg"],
    "ACTARM":  ["Drug X 50mg", "Placebo", "Drug X 50mg", "Placebo", "Drug X 50mg"],
    "SEX":     ["M", "F", "F", "M", "F"],
    "RACE":    ["OTHER", "BLACK OR AFRICAN AMERICAN", "WHITE", "WHITE", "ASIAN"],
    "AGE":     [56.0, 69.0, 43.0, 71.0, 58.0],
    "AGEU":    ["YEARS"] * 5,
    "RFSTDTC": [22742.0, 22736.0, 22748.0, 22730.0, 22753.0],  # SAS date numerics
    "DTHFL":   ["N", "N", "N", "N", "N"],
})
write("dm_raw", dm,
    labels={
        "STUDYID": "Study Identifier", "SUBJID": "Subject Identifier",
        "SITEID": "Study Site Identifier", "ARM": "Description of Planned Arm",
        "ACTARM": "Description of Actual Arm", "SEX": "Sex",
        "RACE": "Race", "AGE": "Age", "AGEU": "Age Units",
        "RFSTDTC": "Subject Reference Start Date/Time", "DTHFL": "Subject Death Flag",
    },
    formats={
        "STUDYID": "$20.", "SUBJID": "$4.", "SITEID": "$3.",
        "ARM": "$40.", "ACTARM": "$40.", "SEX": "$1.",
        "RACE": "$40.", "AGE": "8.", "AGEU": "$5.",
        "RFSTDTC": "DATE9.", "DTHFL": "$1.",
    },
)

# ── VS_RAW — Vital Signs ─────────────────────────────────────────────────────
vs = pd.DataFrame({
    "STUDYID":  ["ADC-XYZ-001"] * 8,
    "SUBJID":   ["0001", "0001", "0002", "0002", "0003", "0003", "0004", "0004"],
    "SITEID":   ["003", "003", "002", "002", "001", "001", "003", "003"],
    "VISIT":    ["SCREENING", "BASELINE", "SCREENING", "BASELINE",
                 "SCREENING", "BASELINE", "SCREENING", "BASELINE"],
    "VSDTC":    [22728.0, 22742.0, 22722.0, 22736.0, 22734.0, 22748.0, 22716.0, 22730.0],
    "VSTESTCD": ["SYSBP", "SYSBP", "SYSBP", "SYSBP", "DIABP", "DIABP", "WEIGHT", "WEIGHT"],
    "VSORRES":  [144.0, 125.0, 138.0, 131.0, 88.0, 82.0, 72.5, 71.8],
    "VSORRESU": ["mmHg", "mmHg", "mmHg", "mmHg", "mmHg", "mmHg", "kg", "kg"],
})
write("vs_raw", vs,
    labels={
        "STUDYID": "Study Identifier", "SUBJID": "Subject Identifier",
        "SITEID": "Study Site Identifier", "VISIT": "Visit Name",
        "VSDTC": "Date/Time of Measurements", "VSTESTCD": "Vital Signs Test Short Name",
        "VSORRES": "Result or Finding in Original Units", "VSORRESU": "Original Units",
    },
    formats={
        "STUDYID": "$20.", "SUBJID": "$4.", "SITEID": "$3.",
        "VISIT": "$20.", "VSDTC": "DATE9.", "VSTESTCD": "$8.",
        "VSORRES": "COMMA8.1", "VSORRESU": "$10.",
    },
)

# ── EX_RAW — Exposure ────────────────────────────────────────────────────────
ex = pd.DataFrame({
    "STUDYID": ["ADC-XYZ-001"] * 6,
    "SUBJID":  ["0001", "0001", "0002", "0003", "0003", "0004"],
    "SITEID":  ["003", "003", "002", "001", "001", "003"],
    "EXTRT":   ["Drug X 50mg", "Drug X 50mg", "Placebo", "Drug X 50mg", "Drug X 50mg", "Placebo"],
    "EXDOSE":  [50.0, 50.0, 0.0, 50.0, 50.0, 0.0],
    "EXSTDTC": [22742.0, 22756.0, 22736.0, 22748.0, 22762.0, 22730.0],
    "EXENDTC": [22755.0, 22769.0, 22749.0, 22761.0, 22775.0, 22743.0],
})
write("ex_raw", ex,
    labels={
        "STUDYID": "Study Identifier", "SUBJID": "Subject Identifier",
        "SITEID": "Study Site Identifier", "EXTRT": "Name of Treatment",
        "EXDOSE": "Dose per Administration", "EXSTDTC": "Start Date/Time of Treatment",
        "EXENDTC": "End Date/Time of Treatment",
    },
    formats={
        "STUDYID": "$20.", "SUBJID": "$4.", "SITEID": "$3.",
        "EXTRT": "$30.", "EXDOSE": "COMMA8.",
        "EXSTDTC": "DATE9.", "EXENDTC": "DATE9.",
    },
)

# ── AE_RAW — Adverse Events ──────────────────────────────────────────────────
ae = pd.DataFrame({
    "STUDYID": ["ADC-XYZ-001"] * 6,
    "SUBJID":  ["0001", "0001", "0002", "0003", "0004", "0005"],
    "SITEID":  ["003", "003", "002", "001", "003", "002"],
    "AETERM":  ["HEADACHE", "NAUSEA", "DIZZINESS", "FATIGUE", "RASH", "HEADACHE"],
    "AESEV":   [3.0, 5.0, 2.0, 1.0, 3.0, 2.0],
    "AESTDTC": [22800.0, 22748.0, 22760.0, 22755.0, 22742.0, 22780.0],
})
write("ae_raw", ae,
    labels={
        "STUDYID": "Study Identifier", "SUBJID": "Subject Identifier",
        "SITEID": "Study Site Identifier", "AETERM": "Reported Term for the Adverse Event",
        "AESEV": "Severity/Intensity", "AESTDTC": "Start Date/Time of Adverse Event",
    },
    formats={
        "STUDYID": "$20.", "SUBJID": "$4.", "SITEID": "$3.",
        "AETERM": "$30.", "AESEV": "1.", "AESTDTC": "DATE9.",
    },
)

# ── LB_RAW — Laboratory ──────────────────────────────────────────────────────
lb = pd.DataFrame({
    "STUDYID":  ["ADC-XYZ-001"] * 8,
    "SUBJID":   ["0001", "0001", "0002", "0002", "0003", "0003", "0004", "0004"],
    "SITEID":   ["003", "003", "002", "002", "001", "001", "003", "003"],
    "VISIT":    ["SCREENING", "WEEK 4", "SCREENING", "WEEK 4",
                 "SCREENING", "WEEK 4", "SCREENING", "WEEK 4"],
    "LBDTC":   [22728.0, 22770.0, 22722.0, 22764.0, 22734.0, 22776.0, 22716.0, 22758.0],
    "LBTESTCD": ["ALT", "ALT", "AST", "AST", "ALT", "ALT", "CREAT", "CREAT"],
    "LBORRES":  [23.46, 28.1, 14.69, 17.3, 31.2, 29.8, 0.89, 0.92],
    "LBORRESU": ["U/L", "U/L", "U/L", "U/L", "U/L", "U/L", "mg/dL", "mg/dL"],
})
write("lb_raw", lb,
    labels={
        "STUDYID": "Study Identifier", "SUBJID": "Subject Identifier",
        "SITEID": "Study Site Identifier", "VISIT": "Visit Name",
        "LBDTC": "Date/Time of Specimen Collection", "LBTESTCD": "Lab Test or Examination Short Name",
        "LBORRES": "Result or Finding in Original Units", "LBORRESU": "Original Units",
    },
    formats={
        "STUDYID": "$20.", "SUBJID": "$4.", "SITEID": "$3.",
        "VISIT": "$20.", "LBDTC": "DATE9.", "LBTESTCD": "$8.",
        "LBORRES": "COMMA10.2", "LBORRESU": "$10.",
    },
)

print("Done.")
