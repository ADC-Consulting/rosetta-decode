"""
generate_kyc_data.py
Generates synthetic CSV input files and golden output files for sas_kyc_aml_sandbox.
Run from repo root: python scripts/generate_kyc_data.py
"""
import csv
import os
import random
import unicodedata
from datetime import date, datetime, timedelta

SEED = 42
random.seed(SEED)

BASE = os.path.join(os.path.dirname(__file__), "..", "sample_data", "sas_kyc_aml_sandbox")


def write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {len(rows):>4} rows → {os.path.relpath(path)}")


def fmt_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%d%b%Y:%H:%M:%S").upper()


AS_OF_DT = date(2024, 12, 31)
DELTA_START = date(2024, 12, 1)

# ── reference data ────────────────────────────────────────────────────────────

STANDARD_COUNTRIES = ["DE", "FR", "GB", "NL", "SE", "CH", "AU", "CA", "AT", "BE", "DK", "NO"]
ELEVATED_COUNTRIES = ["RU", "BY", "CN", "VN", "TH", "BR", "MX", "TR", "ZA", "IN", "PH"]
HIGH_RISK_COUNTRIES = ["AF", "IR", "IQ", "KP", "SY", "YE", "NG", "PK", "MM"]
ALL_COUNTRIES = STANDARD_COUNTRIES + ELEVATED_COUNTRIES + HIGH_RISK_COUNTRIES

CUST_TYPES = ["IND", "IND", "IND", "CORP", "TRUST", "FUND"]  # weighted to individual
OCC_CODES = ["EXEC", "MGMT", "ENGG", "FINC", "RETL", "DEAL", "GAMB", "CASI", "HLTH", "EDUC"]
SRC_OF_WEALTH = ["SAL", "SAL", "INVST", "BUSPRT", "INHRT", "OTHR"]
CHANNELS = ["BRANCH", "BRANCH", "DIGITAL", "DIGITAL", "INTRO"]

# Watchlist names — these will have near-matches seeded into onboarding
WATCHLIST_NAMES_SANCTION = [
    ("WL-SANC-001", "AHMAD KARIMI"),
    ("WL-SANC-002", "IBRAHIM AL-RASHIDI"),
    ("WL-SANC-003", "SERGEI VOLKOV"),
    ("WL-SANC-004", "HASSAN NAZARI"),
    ("WL-SANC-005", "PYONGYANG TRADING CO"),
    ("WL-SANC-006", "TEHRAN EXPORT BANK"),
    ("WL-SANC-007", "DIMITRI SOKOLOV"),
    ("WL-SANC-008", "MARIA PETROV"),
    ("WL-SANC-009", "JOSE ESCOBAR REYES"),
    ("WL-SANC-010", "FATIMA KHALIL"),
]

WATCHLIST_NAMES_PEP = [
    ("WL-PEP-001", "JEAN-PAUL MARCHAND"),
    ("WL-PEP-002", "CHEN WEI"),
    ("WL-PEP-003", "OLUWASEUN ADEYEMI"),
    ("WL-PEP-004", "RAJESH KUMAR SHARMA"),
    ("WL-PEP-005", "ALEKSANDR PETROV"),
    ("WL-PEP-006", "MARIE-CLAIRE FONTAINE"),
    ("WL-PEP-007", "ABDULLAHI IBRAHIM"),
    ("WL-PEP-008", "LUIGI FERRARI"),
    ("WL-PEP-009", "SVETLANA MOROZOVA"),
    ("WL-PEP-010", "MEHMET YILMAZ"),
]

WATCHLIST_NAMES_ADVMEDIA = [
    ("WL-ADV-001", "GLOBAL RESOURCES LTD"),
    ("WL-ADV-002", "PACIFIC HOLDINGS TRUST"),
    ("WL-ADV-003", "VIKTOR KOZLOV"),
    ("WL-ADV-004", "EASTERN COMMERCE GROUP"),
    ("WL-ADV-005", "JAMES OKONKWO"),
]

# Near-match variants to seed into onboarding (close but not exact — above threshold)
# These are designed to score comfortably above the COMPGED/SOUNDEX threshold
NEAR_MATCH_SEEDS = [
    # (wl_id, onboarding_name_variant, wl_type)  — variant close enough to trigger screening
    ("WL-SANC-001", "AHMAD KARIMI",    "SANCTION"),   # exact — certain match
    ("WL-SANC-003", "SERGEI WOLKOV",   "SANCTION"),   # near-match (V/W swap)
    ("WL-PEP-002",  "CHEN WEI",        "PEP"),         # exact — PEP confirmed
    ("WL-PEP-005",  "ALEXANDER PETROV","PEP"),          # near-match (Aleksandr/Alexander)
]

RANDOM_NAMES = [
    "Sophie Müller", "James Richardson", "Amelia Patel", "Lucas Dubois",
    "Fatou Diallo", "Henrik Bergström", "Yuki Tanaka", "Carlos Mendez",
    "Priya Nair", "Tom O'Brien", "Valentina Rossi", "David Cohen",
    "Aisha Mohammed", "Lars Andersen", "Emma Johansson", "Patrick Murphy",
    "Ngozi Okafor", "Michael Zhang", "Isabel Santos", "Robert Wilson",
    "Anna Kowalski", "Samuel Osei", "Claire Fontaine", "Hiroshi Nakamura",
    "Maria Garcia", "Peter Novak", "Kenji Watanabe", "Sarah Thompson",
    "Ahmed Hassan", "Julia Fischer", "Kwame Mensah", "Elena Ivanova",
    "François Leroy", "Nadia Hoffmann", "Oscar Lindqvist", "Hannah Schmidt",
    "Tunde Adebayo", "Mei-Ling Chen", "Bruno Cavalcanti", "Rosa Ferreira",
    "Andrei Popescu", "Katarzyna Wiśniewska", "Jean-Marc Perrin",
    "Chiara Bianchi", "Sven Eriksson", "Amara Diop", "Diana Popova",
    "Rodrigo Almeida", "Charlotte Webb", "Olusegun Babalola",
    "Stefan Weber", "Ingrid Hansen", "Babatunde Okonkwo", "Min-Jun Lee",
    "Miriam Khoury", "Alexei Smirnov", "Patricia O'Connor", "Youssef Benali",
    "Anya Sharma", "Lukas Becker", "Giulia Lombardi", "Sean Gallagher",
    "Zanele Dlamini", "Tobias Müller", "Haruto Yamamoto", "Vera Sorokin",
    "Marco Russo", "Nkechi Eze", "Dominique Bernard", "Florian Braun",
    "Ada Osei-Bonsu", "Nikolaj Christensen", "Paula Herrera", "Ivan Novikov",
    "Linnea Gustafsson", "Emeka Onwueme", "Sabine Lehmann", "Thomas Carey",
    "Blessing Osei", "Casimir Kowalczyk", "Monique Laurent", "Riku Mäkinen",
    "Silvia Torres", "Damian Kozlowski", "Fatimata Coulibaly",
    "Ole-Christian Hagen", "Ximena Vargas", "Benedikt Schwarz",
    "Adaeze Nwosu", "Mikael Lindqvist", "Saoirse Murphy", "Wilhelm Koch",
    "Aminata Traoré", "Konstantinos Papadopoulos", "Fiona MacLeod",
    "Ravi Krishnamurthy", "Léa Moreau", "Tobi Femi", "Sigrid Olsen",
    "Catalina Ionescu", "Wojciech Zielinski", "Astrid Andersen",
    "Chiamaka Obi", "Maximilian Schneider", "Layla Al-Farsi",
    "Bruno Martins", "Brigitte Hoffmann", "Seun Adesanya", "Nils Larsen",
    "María José Rodríguez", "Kofi Asante", "Hanne Nielsen",
    "Stavros Karagiannidis", "Lena Fischer", "Emre Yıldız",
    "Chinyere Nwachukwu", "Antoine Dubois", "Tuulikki Virtanen",
    "Pedro Ferreira", "Ingeborg Svensson", "Olumide Adewale",
    "Ester Johansson", "Klaus Bergmann", "Chidinma Okonkwo",
    "Theodoros Alexiou", "Marie Gustavsson", "Abdul Rahman Al-Qasim",
    "Nora Andersen", "Festus Okafor", "Petra Novotná", "Bjorn Magnusson",
    "Abigail Kessler", "Henrique Sousa", "Sofía Herrera", "Akosua Boateng",
    "Matthias Zimmermann", "Elif Demir", "Simone Pellegrini",
    "Björn Lindberg", "Esther Owusu", "Fredéric Lecomte",
    "Agnieszka Woźniak", "Akinola Bamidele", "Ruth Eichmann",
    "Petros Georgiou", "Alba Ortega", "Konrad Nowak", "Imane Berrada",
    "Søren Madsen", "Ekanem Effiong", "Vasiliki Papadaki",
    "Dieter Hoffmeister", "Oyin Akerele", "Marcelino Fernández",
    "Vigdis Larssen", "Uchenna Nwosu", "Bogumił Kowalski",
    "Renata Szabó", "Mikko Nieminen", "Ifeoma Eze",
]


def soundex(name: str) -> str:
    """Simple Soundex implementation matching SAS SOUNDEX behaviour."""
    name = name.upper().strip()
    if not name:
        return "0000"
    codes = {c: d for d, chars in {
        '1': 'BFPV', '2': 'CGJKQSXYZ', '3': 'DT',
        '4': 'L', '5': 'MN', '6': 'R',
    }.items() for c in chars}
    result = [name[0]]
    last = codes.get(name[0], '0')
    for c in name[1:]:
        code = codes.get(c, '0')
        if code != '0' and code != last:
            result.append(code)
        last = code
        if len(result) == 4:
            break
    while len(result) < 4:
        result.append('0')
    return ''.join(result)


def compress_name(name: str) -> str:
    """Uppercase, strip and compress multiple spaces."""
    return ' '.join(name.upper().split())


def simple_ged(a: str, b: str) -> int:
    """Levenshtein distance."""
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        new_dp = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            new_dp[j] = min(new_dp[j - 1] + 1, dp[j] + 1, dp[j - 1] + cost)
        dp = new_dp
    return dp[n]


# ── country risk tier ─────────────────────────────────────────────────────────

def country_risk_pts(cntry: str) -> int:
    if cntry in HIGH_RISK_COUNTRIES:
        return 5
    if cntry in ["PK", "JO", "TN", "NG", "GH", "UG", "ZW", "ML", "NI"]:
        return 4
    if cntry in ELEVATED_COUNTRIES:
        return 3
    if cntry in ["IN", "ID", "PH", "EG", "MA", "SA", "AE", "QA", "KW"]:
        return 2
    return 1


# ── risk weights reference ────────────────────────────────────────────────────

def gen_risk_weights():
    rows = [
        {"factor_cd": "CNTRY_RISK", "factor_val": "5", "weight_pts": 50},
        {"factor_cd": "CNTRY_RISK", "factor_val": "4", "weight_pts": 40},
        {"factor_cd": "CNTRY_RISK", "factor_val": "3", "weight_pts": 30},
        {"factor_cd": "CNTRY_RISK", "factor_val": "2", "weight_pts": 20},
        {"factor_cd": "CNTRY_RISK", "factor_val": "1", "weight_pts": 10},
        {"factor_cd": "PEP",       "factor_val": "CONFIRMED", "weight_pts": 40},
        {"factor_cd": "PEP",       "factor_val": "POSSIBLE",  "weight_pts": 30},
        {"factor_cd": "SANCTION",  "factor_val": "CONFIRMED", "weight_pts": 50},
        {"factor_cd": "SANCTION",  "factor_val": "POSSIBLE",  "weight_pts": 20},
        {"factor_cd": "SOW",       "factor_val": "OTHR",      "weight_pts": 15},
        {"factor_cd": "SOW",       "factor_val": "BUSPRT",    "weight_pts": 10},
        {"factor_cd": "CHNL",      "factor_val": "INTRO",     "weight_pts": 15},
        {"factor_cd": "CHNL",      "factor_val": "DIGITAL",   "weight_pts": 10},
        {"factor_cd": "CHNL",      "factor_val": "BRANCH",    "weight_pts": 5},
        {"factor_cd": "CUST_TYP",  "factor_val": "TRUST",     "weight_pts": 20},
        {"factor_cd": "CUST_TYP",  "factor_val": "FUND",      "weight_pts": 20},
        {"factor_cd": "CUST_TYP",  "factor_val": "CORP",      "weight_pts": 10},
        {"factor_cd": "CUST_TYP",  "factor_val": "IND",       "weight_pts": 0},
        {"factor_cd": "CASH_OCC",  "factor_val": "DEAL",      "weight_pts": 25},
        {"factor_cd": "CASH_OCC",  "factor_val": "GAMB",      "weight_pts": 25},
        {"factor_cd": "CASH_OCC",  "factor_val": "CASI",      "weight_pts": 25},
        {"factor_cd": "CASH_OCC",  "factor_val": "PAWN",      "weight_pts": 25},
        {"factor_cd": "CASH_OCC",  "factor_val": "CURR",      "weight_pts": 25},
        {"factor_cd": "CASH_OCC",  "factor_val": "REAG",      "weight_pts": 25},
    ]
    return rows


# ── generate watchlist ────────────────────────────────────────────────────────

def gen_watchlist():
    rows = []
    list_dt = date(2024, 1, 1)
    # Sanctions
    for wl_id, name in WATCHLIST_NAMES_SANCTION:
        cntry = random.choice(HIGH_RISK_COUNTRIES + ELEVATED_COUNTRIES)
        src = random.choice(["OFAC", "EU", "UN"])
        dob_dt = date(random.randint(1950, 1985), random.randint(1, 12), random.randint(1, 28))
        rows.append({
            "wl_id": wl_id, "wl_nm": name, "wl_typ_cd": "SANCTION",
            "wl_cntry_cd": cntry, "list_src_cd": src,
            "list_dt": fmt_date(list_dt), "wl_dob": fmt_date(dob_dt),
        })
    # Add spelling variants for sanctions
    rows.append({
        "wl_id": "WL-SANC-011", "wl_nm": "AHMED KARIMI", "wl_typ_cd": "SANCTION",
        "wl_cntry_cd": "IR", "list_src_cd": "EU",
        "list_dt": fmt_date(list_dt), "wl_dob": "",
    })
    rows.append({
        "wl_id": "WL-SANC-012", "wl_nm": "IBRAHIM RASHIDI", "wl_typ_cd": "SANCTION",
        "wl_cntry_cd": "IQ", "list_src_cd": "OFAC",
        "list_dt": fmt_date(list_dt), "wl_dob": "",
    })
    # PEP
    for wl_id, name in WATCHLIST_NAMES_PEP:
        cntry = random.choice(ALL_COUNTRIES)
        dob_dt = date(random.randint(1945, 1975), random.randint(1, 12), random.randint(1, 28))
        rows.append({
            "wl_id": wl_id, "wl_nm": name, "wl_typ_cd": "PEP",
            "wl_cntry_cd": cntry, "list_src_cd": "INTERNAL",
            "list_dt": fmt_date(list_dt), "wl_dob": fmt_date(dob_dt),
        })
    # ADVMEDIA
    for wl_id, name in WATCHLIST_NAMES_ADVMEDIA:
        cntry = random.choice(ALL_COUNTRIES)
        rows.append({
            "wl_id": wl_id, "wl_nm": name, "wl_typ_cd": "ADVMEDIA",
            "wl_cntry_cd": cntry, "list_src_cd": "INTERNAL",
            "list_dt": fmt_date(list_dt), "wl_dob": "",
        })
    # Pad to ~120 with random names
    generic_names = [
        "OSCAR SILVA", "NINA BERGMAN", "PIERRE LAMBERT", "TATYANA VOLKOV",
        "ADNAN MALIK", "BORIS NEKRASOV", "CARMEN DELGADO", "FRANK MUELLER",
        "GEORGIA BATES", "HENRIK DAHL", "IMANI OSEI", "JANUSZ WOŹNIAK",
        "KATHARINA ERNST", "LOTTE VAN DER BERG", "MARCO BIANCHI",
        "NADIA PETROVA", "OLAF CHRISTIANSEN", "PITA HAVILI",
        "QUIRINO FERREIRA", "RASHIDA KAMARA", "STEFAN BRAUN",
        "TOMAS NOVAK", "ULF LINDGREN", "VERA SMIRNOVA",
        "WOLFGANG GRUBER", "XIAOMING LI", "YOLANDA TORRES",
        "ZLATKO HORVAT", "AMARA KONE", "BEATRIZ CASTRO",
        "CEMAL YILDIRIM", "DOROTA KOWALCZYK", "ENRIQUE MORALES",
        "FLORENCE ROUX", "GUNNAR HAAKONSEN", "HANNELORE BRUNNER",
        "ISIDORO RICCI", "JARI HEIKKINEN", "KAROLINA WIŚNIEWSKA",
        "LEIF ERIKSEN", "MARTA KOWALSKA", "NIKLAS BERG",
        "OPHELIA CRANE", "PATRYK DĄBROWSKI", "QUIRINE SMITS",
        "RAGNHILD ANDERSEN", "SIMON TREMBLAY", "THORSTEN KELLER",
        "UMBERTO GALLO", "VERONIKA MÜLLER", "WALDEMAR NOWAK",
        "XIULAN CHEN", "YVONNE GIRARD", "ZUZANNA PAWLAK",
        "ALEKSEI GORBACHEV", "BARBARA KOWALSKA", "CRISTIANO FERREIRA",
        "DENISE DUPONT", "ERIKA LINDQVIST", "FILIPPO MORETTI",
        "GRZEGORZ ADAMSKI", "HELENA NOVAK", "IVAN PETROV",
        "JÓZEF KOWALSKI", "KATERINA NOVAKOVA", "LUDOVICO RUSSO",
        "MAGDALENA WOŹNIAK", "NORBERT HARTMANN", "OCTAVIA SMITH",
        "PASCAL FONTAINE", "RAPHAËLLE MARTIN", "SIGBJØRN BREKKE",
        "TEODOR POPA", "URSULA HOFMANN", "VINCENT MOREL",
        "WANDA SZCZEPAŃSKA", "XANDER DE VRIES", "YASEMIN DOĞAN",
        "ZBIGNIEW KOWALCZYK", "ANTTI VIRTANEN", "BLANCA RUIZ",
        "CÉDRIC LEFEBVRE", "DRAGANA MARKOVIĆ", "ELODIE SIMON",
        "FRANK OLSEN", "GENEVIÈVE TREMBLAY", "HANS SCHULZ",
        "IRINA POPOVA", "JAN NOVÁK", "KIRSTEN PEDERSEN",
    ]
    for i, nm in enumerate(generic_names):
        cntry = random.choice(ALL_COUNTRIES)
        wl_typ = random.choice(["SANCTION", "PEP", "ADVMEDIA"])
        src = random.choice(["OFAC", "EU", "UN", "INTERNAL"])
        rows.append({
            "wl_id": f"WL-GEN-{i+1:03d}", "wl_nm": nm, "wl_typ_cd": wl_typ,
            "wl_cntry_cd": cntry, "list_src_cd": src,
            "list_dt": fmt_date(list_dt), "wl_dob": "",
        })
    return rows[:120]


# ── generate client master (SCD-2, ~50 rows) ─────────────────────────────────

def gen_client_master(n=50):
    rows = []
    for i in range(1, n + 1):
        cust_id = f"CUS-{i:07d}"
        cust_sk = i * 10
        last_review = date(
            random.randint(2021, 2023),
            random.randint(1, 12),
            random.randint(1, 28),
        )
        crr = random.choice(["LOW", "LOW", "MED", "HIGH"])
        rows.append({
            "cust_id": cust_id,
            "cust_sk": cust_sk,
            "full_nm_std": random.choice(RANDOM_NAMES).upper(),
            "crr_band_cd": crr,
            "crr_score": random.randint(10, 120),
            "valid_from_dt": fmt_date(date(random.randint(2019, 2023), 1, 1)),
            "valid_to_dt": "99991231",
            "curr_flg": "Y",
            "last_review_dt": fmt_date(last_review),
        })
    return rows


# ── generate onboarding (~220 rows) ──────────────────────────────────────────

def gen_onboarding(n=220, n_prior=20):
    rows = []
    load_base = datetime(2024, 12, 31, 21, 0, 0)
    names_pool = RANDOM_NAMES[:]
    random.shuffle(names_pool)

    for i in range(1, n + 1):
        cust_id = f"CUS-{1000 + i:07d}"
        is_prior = i <= n_prior
        eff_dt = date(2024, 11, 30) if is_prior else date(2024, 12, 31)

        # Mostly standard countries, some elevated, a few high-risk
        roll = random.random()
        if roll < 0.05:
            cntry = random.choice(HIGH_RISK_COUNTRIES)
        elif roll < 0.20:
            cntry = random.choice(ELEVATED_COUNTRIES)
        else:
            cntry = random.choice(STANDARD_COUNTRIES)

        cntry_ctznshp = cntry  # usually same
        cust_typ = random.choice(CUST_TYPES)
        occ = random.choice(OCC_CODES)
        sow = random.choice(SRC_OF_WEALTH)
        chnl = random.choice(CHANNELS)
        pep_decl = "Y" if i == 50 else ("N" if random.random() > 0.02 else "Y")

        # Name selection
        if i <= len(NEAR_MATCH_SEEDS):
            _, nm_raw, _ = NEAR_MATCH_SEEDS[i - 1]
            full_nm = nm_raw.title()
        else:
            idx = (i - len(NEAR_MATCH_SEEDS) - 1) % len(names_pool)
            full_nm = names_pool[idx]

        # Dirty rows
        if i == 55:  # future DOB
            dob = date(2030, 1, 1)
        elif i == 60:  # implausible (>120 years)
            dob = date(1890, 6, 15)
        else:
            birth_year = random.randint(1945, 2000)
            birth_month = random.randint(1, 12)
            birth_day = random.randint(1, 28)
            dob = date(birth_year, birth_month, birth_day)

        # Missing cntry_ctznshp for rows 70,71
        if i in (70, 71):
            cntry_ctznshp = ""

        # Unknown cust_typ for row 80
        if i == 80:
            cust_typ = "PART"

        # Unicode stray punctuation in name for row 85
        if i == 85:
            full_nm = full_nm + " ​’"

        load_dttm = load_base + timedelta(seconds=i * 7)

        rows.append({
            "cust_id": cust_id,
            "eff_dt": fmt_date(eff_dt),
            "full_nm": full_nm,
            "dob": fmt_date(dob),
            "cntry_resdnc_cd": cntry,
            "cntry_ctznshp_cd": cntry_ctznshp,
            "cust_typ_cd": cust_typ,
            "occ_cd": occ,
            "pep_self_decl_flg": pep_decl,
            "src_of_wlth_cd": sow,
            "onbrd_chnl_cd": chnl,
            "load_dttm": fmt_dt(load_dttm),
        })
    return rows


# ── screening logic (mirrors SAS 03_screen_watchlist + m_screen_pass) ────────

# Match thresholds: max Levenshtein distance for a confirmed or possible match.
# SAS COMPGED operates on a different (larger) scale than plain Levenshtein;
# we use raw edit distance here so thresholds are deliberately low.
SANCTION_MAX_GED = 2   # distance ≤ 2 → confirmed match (COMPGED ≤ 100 analogue)
PEP_MAX_GED = 3        # distance ≤ 3 → confirmed PEP match
POSSIBLE_MAX_GED = 4   # soundex match + distance ≤ 4 → possible match


def screen_client(full_nm_upper: str, watchlist: list) -> dict:
    best = {"match_flg": "N", "best_wl_id": "", "best_sim": 0, "match_method": ""}
    for wl in watchlist:
        wl_nm = wl["wl_nm"].upper()
        wl_typ = wl["wl_typ_cd"]

        ged = simple_ged(full_nm_upper, wl_nm)
        # Invert so higher = better match (mirrors SAS sim = max(0, 200 - COMPGED))
        sim = max(0, 200 - ged * 20)  # scale so GED=0→200, GED=10→0
        sdx_match = soundex(full_nm_upper) == soundex(wl_nm)

        if wl_typ == "SANCTION":
            confirmed_threshold = SANCTION_MAX_GED
        else:
            confirmed_threshold = PEP_MAX_GED

        if ged <= confirmed_threshold:
            if sim > best["best_sim"]:
                best = {
                    "match_flg": "Y",
                    "best_wl_id": wl["wl_id"],
                    "best_sim": sim,
                    "match_method": "COMPGED",
                }
        elif sdx_match and ged <= POSSIBLE_MAX_GED:
            if sim > best["best_sim"]:
                best = {
                    "match_flg": "P",
                    "best_wl_id": wl["wl_id"],
                    "best_sim": sim,
                    "match_method": "SOUNDEX+LEV",
                }
    return best


CASH_INTENSIVE_OCCS = {"DEAL", "GAMB", "CASI", "PAWN", "CURR", "REAG"}


def score_client(client: dict, screen: dict) -> dict:
    crr_score = 0
    cntry = client.get("cntry_resdnc_cd", "")
    cntry_pts = country_risk_pts(cntry)
    crr_score += cntry_pts * 10

    pep_self = client.get("pep_self_decl_flg", "N")
    match_flg = screen.get("match_flg", "N")
    best_sim = screen.get("best_sim", 0)
    match_method = screen.get("match_method", "")

    pep_flag = "N"
    if pep_self == "Y":
        crr_score += 40
        pep_flag = "Y"
    elif match_flg in ("Y", "P") and best_sim >= 100:
        crr_score += 30
        pep_flag = "P"

    if match_flg == "Y" and match_method == "COMPGED":
        crr_score += 50
    elif match_flg == "P":
        crr_score += 20

    sow = client.get("src_of_wlth_cd", "")
    if sow == "OTHR":
        crr_score += 15
    elif sow == "BUSPRT":
        crr_score += 10

    chnl = client.get("onbrd_chnl_cd", "")
    chnl_pts_map = {"INTRO": 3, "DIGITAL": 2, "BRANCH": 1}
    chnl_pts = chnl_pts_map.get(chnl, 2)
    crr_score += chnl_pts * 5

    cust_typ = client.get("cust_typ_cd", "")
    if cust_typ in ("TRUST", "FUND"):
        crr_score += 20
    elif cust_typ == "CORP":
        crr_score += 10

    occ = client.get("occ_cd", "")
    if occ in CASH_INTENSIVE_OCCS:
        crr_score += 25

    if crr_score >= 80:
        crr_band = "HIGH"
    elif crr_score >= 40:
        crr_band = "MED"
    else:
        crr_band = "LOW"

    return {"crr_score": crr_score, "crr_band_cd": crr_band, "pep_flag": pep_flag}


def edd_reason(scored: dict, screen: dict) -> tuple[bool, int, str]:
    crr_band = scored["crr_band_cd"]
    pep_flag = scored["pep_flag"]
    match_flg = screen.get("match_flg", "N")
    match_method = screen.get("match_method", "")
    cntry_pts = country_risk_pts(scored.get("cntry_resdnc_cd", ""))

    trig_high = crr_band == "HIGH"
    trig_pep = pep_flag in ("Y", "P")
    trig_sanc = match_flg == "Y" and match_method == "COMPGED"
    trig_cntry = cntry_pts >= 4

    required = trig_high or trig_pep or trig_sanc or trig_cntry
    if not required:
        return False, 0, ""

    if trig_sanc:
        priority = 1
    elif pep_flag == "Y":
        priority = 2
    elif trig_high:
        priority = 3
    else:
        priority = 4

    reasons = []
    if trig_sanc:
        reasons.append("Sanctions near-match")
    if pep_flag == "Y":
        reasons.append("Confirmed PEP")
    if pep_flag == "P":
        reasons.append("Possible PEP")
    if trig_high and not trig_sanc and pep_flag == "N":
        reasons.append("High CRR score")
    if trig_cntry:
        reasons.append("High-risk jurisdiction")
    return True, priority, "; ".join(reasons)


# ── golden generation ─────────────────────────────────────────────────────────

def generate_golden(onboarding: list, watchlist: list):
    # Filter to eff_dt >= 01DEC2024
    delta = [c for c in onboarding if c["eff_dt"] >= "20241201"]

    wl_all = watchlist

    screened_rows = []
    edd_rows = []

    for client in delta:
        # Standardise name
        raw = client["full_nm"]
        clean = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
        full_nm_upper = compress_name(clean)

        screen = screen_client(full_nm_upper, wl_all)

        scored = score_client(
            {**client, "cntry_resdnc_cd": client["cntry_resdnc_cd"]},
            screen,
        )

        row = {
            "cust_id": client["cust_id"],
            "eff_dt": client["eff_dt"],
            "full_nm": client["full_nm"],
            "full_nm_upper": full_nm_upper,
            "dob": client["dob"],
            "cntry_resdnc_cd": client["cntry_resdnc_cd"],
            "cntry_ctznshp_cd": client["cntry_ctznshp_cd"],
            "cust_typ_cd": client["cust_typ_cd"],
            "occ_cd": client["occ_cd"],
            "pep_self_decl_flg": client["pep_self_decl_flg"],
            "src_of_wlth_cd": client["src_of_wlth_cd"],
            "onbrd_chnl_cd": client["onbrd_chnl_cd"],
            "match_flg": screen["match_flg"],
            "best_wl_id": screen["best_wl_id"],
            "best_sim": screen["best_sim"],
            "match_method": screen["match_method"],
            "crr_score": scored["crr_score"],
            "crr_band_cd": scored["crr_band_cd"],
            "pep_flag": scored["pep_flag"],
        }
        screened_rows.append(row)

        req, priority, reason = edd_reason(
            {**scored, "cntry_resdnc_cd": client["cntry_resdnc_cd"]},
            screen,
        )
        if req:
            edd_rows.append({
                **row,
                "case_priority": priority,
                "edd_reason_txt": reason,
            })

    # Sort EDD queue by case_priority then crr_score desc
    edd_rows.sort(key=lambda r: (r["case_priority"], -r["crr_score"]))

    return screened_rows, edd_rows


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Generating sas_kyc_aml_sandbox data...")

    risk_weights = gen_risk_weights()
    watchlist = gen_watchlist()
    client_master = gen_client_master(50)
    onboarding = gen_onboarding(220, n_prior=20)

    write_csv(
        os.path.join(BASE, "data", "ref", "risk_weights.csv"),
        risk_weights,
        ["factor_cd", "factor_val", "weight_pts"],
    )
    write_csv(
        os.path.join(BASE, "data", "raw", "watchlist.csv"),
        watchlist,
        ["wl_id", "wl_nm", "wl_typ_cd", "wl_cntry_cd", "list_src_cd", "list_dt", "wl_dob"],
    )
    write_csv(
        os.path.join(BASE, "data", "staging", "client_master.csv"),
        client_master,
        ["cust_id", "cust_sk", "full_nm_std", "crr_band_cd", "crr_score",
         "valid_from_dt", "valid_to_dt", "curr_flg", "last_review_dt"],
    )
    write_csv(
        os.path.join(BASE, "data", "raw", "client_onboarding.csv"),
        onboarding,
        ["cust_id", "eff_dt", "full_nm", "dob", "cntry_resdnc_cd", "cntry_ctznshp_cd",
         "cust_typ_cd", "occ_cd", "pep_self_decl_flg", "src_of_wlth_cd",
         "onbrd_chnl_cd", "load_dttm"],
    )

    screened, edd = generate_golden(onboarding, watchlist)

    screened_fields = [
        "cust_id", "eff_dt", "full_nm", "full_nm_upper", "dob",
        "cntry_resdnc_cd", "cntry_ctznshp_cd", "cust_typ_cd", "occ_cd",
        "pep_self_decl_flg", "src_of_wlth_cd", "onbrd_chnl_cd",
        "match_flg", "best_wl_id", "best_sim", "match_method",
        "crr_score", "crr_band_cd", "pep_flag",
    ]
    edd_fields = screened_fields + ["case_priority", "edd_reason_txt"]

    write_csv(
        os.path.join(BASE, "golden", "client_screened_20241231.csv"),
        screened,
        screened_fields,
    )
    write_csv(
        os.path.join(BASE, "golden", "edd_work_queue_20241231.csv"),
        edd,
        edd_fields,
    )

    print(f"  EDD queue: {len(edd)} cases out of {len(screened)} screened")
    print("Done.")


if __name__ == "__main__":
    main()
