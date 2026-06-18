"""
generate_finrep_data.py
Generates synthetic CSV input files and golden output files for sas_finrep_sandbox.
Run from repo root: python scripts/generate_finrep_data.py
"""
import csv
import os
import random
import math
from datetime import date, datetime

SEED = 42
random.seed(SEED)

BASE = os.path.join(os.path.dirname(__file__), "..", "sample_data", "sas_finrep_sandbox")

# ── helpers ──────────────────────────────────────────────────────────────────

def write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {len(rows):>4} rows → {os.path.relpath(path)}")


def fmt_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%d%b%Y:%H:%M:%S").upper()


# ── reference data ────────────────────────────────────────────────────────────

DESKS = ["DESK-IG", "DESK-HY", "DESK-EM"]
BOOKS = ["CRDT-EUR-01", "CRDT-USD-01", "CRDT-GBP-01", "CRDT-EUR-02"]
CCYS = ["EUR", "USD", "GBP"]
ASSET_CLASSES = ["CORP", "SVRN", "ABS", "CVRDBND"]
RATINGS = ["AAA", "AA", "A", "BBB", "SUB_IG", "NR"]
SECTORS = ["FINAN", "CORP", "SOVGN", "SUPRA"]
COUNTRIES = ["DE", "FR", "GB", "US", "IT", "ES", "NL", "JP", "AU", "SE", "CH", "CA"]

DESK_ASSET_AFFINITY = {
    "DESK-IG": ["CORP", "SVRN", "CVRDBND"],
    "DESK-HY": ["CORP", "ABS"],
    "DESK-EM": ["SVRN", "CORP"],
}

DESK_RATING_AFFINITY = {
    "DESK-IG": ["AAA", "AA", "A", "BBB"],
    "DESK-HY": ["SUB_IG", "BBB", "NR"],
    "DESK-EM": ["BBB", "SUB_IG", "A", "NR"],
}

DESK_CCY_AFFINITY = {
    "DESK-IG": ["EUR", "EUR", "USD", "GBP"],
    "DESK-HY": ["USD", "USD", "EUR", "GBP"],
    "DESK-EM": ["USD", "EUR", "GBP"],
}


# ── generate counterparty (~40 rows) ─────────────────────────────────────────

def gen_counterparty(n=40):
    rows = []
    for i in range(1, n + 1):
        issuer_id = f"ISS-{i:04d}"
        sector = random.choice(SECTORS)
        country = random.choice(COUNTRIES)
        watchlist = "Y" if i <= 3 else "N"  # first 3 on watchlist
        int_rating = str(random.randint(1, 10))
        rows.append({
            "issuer_id": issuer_id,
            "cpty_nm": f"Counterparty {issuer_id}",
            "country_cd": country,
            "sector_cd": sector,
            "int_rating_cd": int_rating,
            "watchlist_flg": watchlist,
        })
    return rows


# ── generate instrument_ref (~60 rows) ───────────────────────────────────────

def gen_instrument_ref(counterparty_ids, n=60):
    rows = []
    for i in range(1, n + 1):
        instmt_id = f"INST-{i:04d}"
        asset_cls = random.choice(ASSET_CLASSES)
        rating = random.choice(RATINGS)
        issuer_id = random.choice(counterparty_ids)
        isin = f"XS{random.randint(1000000000, 9999999999)}"
        # One instrument with past maturity (before pos_dt 20241231)
        if i == 5:
            maturity_dt = date(2023, 6, 30)
        else:
            month = random.randint(1, 12)
            # Use 28 to be safe across all months
            maturity_dt = date(random.randint(2025, 2045), month, 28)

        cpn_rt = round(random.uniform(0.5, 8.5), 4)
        duration = round(random.uniform(0.5, 15.0), 4)
        ref_load_dt = date(2024, 12, 1)
        rows.append({
            "instmt_id": instmt_id,
            "isin": isin,
            "issuer_id": issuer_id,
            "asset_cls_cd": asset_cls,
            "maturity_dt": fmt_date(maturity_dt),
            "cpn_rt": cpn_rt,
            "ext_rating_cd": rating,
            "duration": duration,
            "ref_load_dt": fmt_date(ref_load_dt),
        })
    return rows


# ── generate positions (~180 rows) ────────────────────────────────────────────

def gen_positions(instrument_ids, n_total=180, n_prior=15):
    rows = []
    load_base = datetime(2024, 12, 31, 22, 0, 0)
    # use only 50 of the 60 instruments — 10 will have no position (intentional unmatched)
    used_inst = instrument_ids[:50]

    desk_per_book = {
        "CRDT-EUR-01": "DESK-IG",
        "CRDT-USD-01": "DESK-HY",
        "CRDT-GBP-01": "DESK-EM",
        "CRDT-EUR-02": "DESK-IG",
    }

    for i in range(1, n_total + 1):
        is_prior = i <= n_prior
        pos_dt = date(2024, 11, 30) if is_prior else date(2024, 12, 31)
        book = random.choice(BOOKS)
        desk = desk_per_book[book]
        instmt = random.choice(used_inst)
        ccy = random.choice(DESK_CCY_AFFINITY[desk])

        qty_nom = round(random.uniform(100_000, 50_000_000), 2)

        # Dirty row: one position with dirty_px=0
        if i == 20:
            dirty_px = 0.0
        else:
            dirty_px = round(random.uniform(85.0, 115.0), 6)

        mkt_val_lcy = round(qty_nom * dirty_px / 100, 2)

        # Dirty rows: two with missing ccy_cd
        if i in (35, 36):
            ccy = ""

        load_dttm = load_base.replace(second=i % 60, minute=i % 60)

        rows.append({
            "trade_id": f"TRD-{i:05d}",
            "pos_dt": fmt_date(pos_dt),
            "book_cd": book,
            "desk_cd": desk,
            "instmt_id": instmt,
            "qty_nom": qty_nom,
            "dirty_px": dirty_px,
            "mkt_val_lcy": mkt_val_lcy,
            "ccy_cd": ccy,
            "load_dttm": fmt_dt(load_dttm),
        })
    return rows


# ── rating band (matches finrep_formats.sas) ──────────────────────────────────

def rating_band(ext_rating_cd):
    mapping = {
        "AAA": "IG_PRIME",
        "AA": "IG_PRIME",
        "A": "IG_STANDARD",
        "BBB": "IG_STANDARD",
        "SUB_IG": "NON_IG",
        "NR": "UNRATED",
    }
    return mapping.get(ext_rating_cd, "UNKNOWN")


# ── FX rates (match 03_enrich_positions.sas) ──────────────────────────────────

FX = {"EUR": 1.00, "USD": 0.92, "GBP": 1.17}


# ── generate golden output ────────────────────────────────────────────────────

def generate_golden(positions, instruments, counterparties):
    inst_by_id = {r["instmt_id"]: r for r in instruments}
    cpty_by_issuer = {r["issuer_id"]: r for r in counterparties}

    # Filter to pos_dt == 20241231
    positions_dec = [p for p in positions if p["pos_dt"] == "20241231"]

    enriched = []
    for p in positions_dec:
        inst = inst_by_id.get(p["instmt_id"], {})
        cpty = {}
        if inst:
            cpty = cpty_by_issuer.get(inst.get("issuer_id", ""), {})

        # Compute DV01 (may be NaN if fields missing)
        try:
            qty_nom = float(p["qty_nom"])
            duration = float(inst["duration"]) if inst.get("duration") else None
            dirty_px = float(p["dirty_px"])
            dv01 = round(qty_nom * duration * dirty_px / 10000, 6) if duration is not None else ""
        except (ValueError, TypeError, KeyError):
            dv01 = ""

        # FX normalisation
        ccy = p.get("ccy_cd", "")
        fx = FX.get(ccy, 1.0) if ccy else 1.0
        try:
            mkt_val_eur = round(float(p["mkt_val_lcy"]) * fx, 2)
        except (ValueError, TypeError):
            mkt_val_eur = ""

        # Rating band
        rb = rating_band(inst.get("ext_rating_cd", "")) if inst else "UNKNOWN"

        row = {
            "trade_id": p["trade_id"],
            "pos_dt": p["pos_dt"],
            "book_cd": p["book_cd"],
            "desk_cd": p["desk_cd"],
            "instmt_id": p["instmt_id"],
            "qty_nom": p["qty_nom"],
            "dirty_px": p["dirty_px"],
            "mkt_val_lcy": p["mkt_val_lcy"],
            "ccy_cd": p["ccy_cd"],
            "isin": inst.get("isin", ""),
            "issuer_id": inst.get("issuer_id", ""),
            "asset_cls_cd": inst.get("asset_cls_cd", ""),
            "maturity_dt": inst.get("maturity_dt", ""),
            "cpn_rt": inst.get("cpn_rt", ""),
            "ext_rating_cd": inst.get("ext_rating_cd", ""),
            "duration": inst.get("duration", ""),
            "cpty_nm": cpty.get("cpty_nm", ""),
            "country_cd": cpty.get("country_cd", ""),
            "sector_cd": cpty.get("sector_cd", ""),
            "int_rating_cd": cpty.get("int_rating_cd", ""),
            "watchlist_flg": cpty.get("watchlist_flg", ""),
            "dv01": dv01,
            "mkt_val_eur": mkt_val_eur,
            "rating_band": rb,
        }
        enriched.append(row)

    # Exposure summary: desk_cd × asset_cls_cd × rating_band
    from collections import defaultdict
    summary_key = lambda r: (r["desk_cd"], r["asset_cls_cd"], r["rating_band"])
    summary = defaultdict(lambda: {"tot_qty_nom": 0.0, "tot_mkt_val_eur": 0.0, "tot_dv01": 0.0, "trade_count": 0})
    for r in enriched:
        # Only include rows where mkt_val_lcy is not missing (SAS WHERE clause)
        if r["mkt_val_lcy"] == "" or r["mkt_val_lcy"] is None:
            continue
        k = summary_key(r)
        try:
            summary[k]["tot_qty_nom"]    += float(r["qty_nom"]) if r["qty_nom"] != "" else 0
            summary[k]["tot_mkt_val_eur"] += float(r["mkt_val_eur"]) if r["mkt_val_eur"] != "" else 0
            summary[k]["tot_dv01"]        += float(r["dv01"]) if r["dv01"] != "" else 0
            summary[k]["trade_count"]     += 1
        except (ValueError, TypeError):
            pass

    summary_rows = []
    for (desk_cd, asset_cls_cd, rating_band_val), agg in sorted(summary.items()):
        summary_rows.append({
            "desk_cd": desk_cd,
            "asset_cls_cd": asset_cls_cd,
            "rating_band": rating_band_val,
            "tot_qty_nom": round(agg["tot_qty_nom"], 2),
            "tot_mkt_val_eur": round(agg["tot_mkt_val_eur"], 2),
            "tot_dv01": round(agg["tot_dv01"], 6),
            "trade_count": agg["trade_count"],
        })

    return enriched, summary_rows


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Generating sas_finrep_sandbox data...")

    counterparties = gen_counterparty(40)
    cpty_ids = [r["issuer_id"] for r in counterparties]

    instruments = gen_instrument_ref(cpty_ids, n=60)
    inst_ids = [r["instmt_id"] for r in instruments]

    positions = gen_positions(inst_ids, n_total=180, n_prior=15)

    # Write input CSVs
    write_csv(
        os.path.join(BASE, "data", "raw", "positions.csv"),
        positions,
        ["trade_id", "pos_dt", "book_cd", "desk_cd", "instmt_id",
         "qty_nom", "dirty_px", "mkt_val_lcy", "ccy_cd", "load_dttm"],
    )
    write_csv(
        os.path.join(BASE, "data", "raw", "instrument_ref.csv"),
        instruments,
        ["instmt_id", "isin", "issuer_id", "asset_cls_cd", "maturity_dt",
         "cpn_rt", "ext_rating_cd", "duration", "ref_load_dt"],
    )
    write_csv(
        os.path.join(BASE, "data", "staging", "counterparty.csv"),
        counterparties,
        ["issuer_id", "cpty_nm", "country_cd", "sector_cd", "int_rating_cd", "watchlist_flg"],
    )

    # Generate golden output
    enriched, summary = generate_golden(positions, instruments, counterparties)
    write_csv(
        os.path.join(BASE, "golden", "pos_enriched_20241231.csv"),
        enriched,
        ["trade_id", "pos_dt", "book_cd", "desk_cd", "instmt_id", "qty_nom", "dirty_px",
         "mkt_val_lcy", "ccy_cd", "isin", "issuer_id", "asset_cls_cd", "maturity_dt",
         "cpn_rt", "ext_rating_cd", "duration", "cpty_nm", "country_cd", "sector_cd",
         "int_rating_cd", "watchlist_flg", "dv01", "mkt_val_eur", "rating_band"],
    )
    write_csv(
        os.path.join(BASE, "golden", "exposure_summary_20241231.csv"),
        summary,
        ["desk_cd", "asset_cls_cd", "rating_band", "tot_qty_nom", "tot_mkt_val_eur",
         "tot_dv01", "trade_count"],
    )

    print("Done.")


if __name__ == "__main__":
    main()
