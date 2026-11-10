"""Generate synthetic fixed-asset-register rows labelled against taxonomy.yaml.

Output is a CSV in the shape Laya's fine-tuning expects: a `state` column
holding the register row as text, plus one column per question
(`in_scope`, `sector`, `major_category`, `asset_class`).

Usage:
    python generate_synthetic.py --per-class 60 --out data/synthetic.csv
"""
import argparse
import csv
import random
import string
from pathlib import Path

import yaml

HERE = Path(__file__).parent
NA = "not_applicable"

ABBREV = {
    "equipment": "EQUIP", "machine": "MACH", "machining": "MACHG", "system": "SYS",
    "hydraulic": "HYD", "vertical": "VERT", "horizontal": "HORIZ", "center": "CTR",
    "generator": "GEN", "compressor": "COMPR", "conveyor": "CONV", "automatic": "AUTO",
    "automated": "AUTO", "assembly": "ASSY", "stainless": "SS", "transformer": "XFMR",
    "refrigerated": "REFRIG", "refrigeration": "REFRIG", "electric": "ELEC",
    "portable": "PORT", "storage": "STOR", "production": "PROD", "processing": "PROC",
    "controller": "CTRL", "control": "CTRL", "truck": "TRK", "trailer": "TRLR",
    "furniture": "FURN", "workstation": "WKSTN", "computer": "COMP", "packaging": "PKG",
    "inspection": "INSP", "measuring": "MEAS", "distribution": "DIST", "building": "BLDG",
    "installation": "INSTALL", "manufacturing": "MFG", "laboratory": "LAB",
    "department": "DEPT", "maintenance": "MAINT", "warehouse": "WHSE", "pump": "PMP",
    "exchanger": "EXCH", "treatment": "TRTMT", "generation": "GEN", "air": "AIR",
}

CAPACITY = ["{n} TON", "{n}T", "{n} HP", "{n}HP", "{n} KW", "{n}KVA", "{n} GAL", "{n} CFM",
            "{n}\"", "{n}' ", "{n} LB CAP", "{n}K LB", "{n} GPM", "{n}MM", "{n} PSI"]
ADDERS = ["INCL INSTALL", "W/ INSTALLATION", "INSTALLED", "FREIGHT & RIGGING", "W/ ACCESSORIES",
          "- ELECTRICAL HOOKUP", "W/ TOOLING", "ADDL COST", "REBUILD", "UPGRADE", "RETROFIT",
          "USED", "REFURBISHED", "W/ CONTROLS", "FOUNDATION & INSTALL", "COMMISSIONING",
          "SALES TAX", "DEPOSIT", "FINAL PAYMENT", "50% PROGRESS PMT"]
LOCATIONS = ["PLANT 1", "PLT 2", "BLDG A", "BLDG 4", "LINE 3", "LINE 12", "CELL 5", "DEPT 410",
             "WHSE", "MAINT SHOP", "BAY 2", "NORTH YARD", "SITE 07", "UNIT 3", "RM 114"]
VENDOR_SUFFIX = ["INC", "LLC", "CORP", "CO", "SALES & SERVICE", "EQUIPMENT CO", "SUPPLY",
                 "INDUSTRIAL", "MACHINERY", "SYSTEMS", "DISTRIBUTING"]
DEALER_NAMES = ["MIDWEST", "TRI-STATE", "ALLIED", "PRECISION", "NATIONAL", "WESTERN", "APEX",
                "SUMMIT", "GREAT LAKES", "SOUTHERN", "PACIFIC", "KEYSTONE", "LIBERTY", "DELTA"]

# Rows the classifier must learn to reject or escalate.
OUT_OF_SCOPE = {
    "Software & Intangibles": (["Software", "Computer Software", "Intangibles"], [
        "ERP software license", "SAP implementation", "Microsoft Office licenses", "website development",
        "CAD software seats", "Oracle license fees", "software implementation consulting", "patent costs",
        "customer list", "trademark registration", "Salesforce configuration", "MES software module"]),
    "Construction in Progress": (["Construction in Progress", "CIP", "Assets Under Construction"], [
        "CIP line 4 expansion", "construction in progress plant 2", "project 2207 progress billing",
        "CIP new warehouse", "capital project in process", "AUC press line"]),
    "Expense-type & Consumables": (["Machinery & Equipment", "Small Tools", "Supplies"], [
        "repair parts", "annual maintenance contract", "spare belts and filters", "consumable tooling",
        "safety supplies", "service call", "extended warranty", "training fees", "permit fees",
        "calibration service", "moving expenses", "legal fees capitalized"]),
}
UNCLEAR = ["misc equipment", "equipment", "additions", "various", "capital additions", "see invoice",
           "equipment purchase", "machinery", "fixed asset additions", "opening balance",
           "acquisition assets", "plant equipment misc", "prior year additions", "lump sum",
           "transferred assets", "per appraisal", "balance fwd", "asset group", "other equipment"]


def load_taxonomy(path=HERE / "taxonomy.yaml"):
    """Return a flat list of class dicts from the nested taxonomy file."""
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    classes = []
    for sector, cats in raw.items():
        for cat, body in cats.items():
            for cls, spec in body["classes"].items():
                classes.append({
                    "sector": sector, "major_category": cat, "asset_class": cls,
                    "items": spec["items"], "makes": spec.get("makes") or [],
                    "gl": body["gl"], "cost": body["cost"],
                })
    names = [c["asset_class"] for c in classes]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ValueError(f"duplicate class names in taxonomy: {sorted(dupes)}")
    return classes


def model_code(rng):
    """A plausible-looking model number, e.g. VF-2SS, 8FGCU25, 320D."""
    letters = "".join(rng.choices(string.ascii_uppercase, k=rng.randint(1, 3)))
    digits = str(rng.randint(1, 9999))
    pattern = rng.choice(["{l}{d}", "{l}-{d}", "{d}{l}", "{l}{d}{s}", "{l} {d}"])
    return pattern.format(l=letters, d=digits, s=rng.choice(string.ascii_uppercase))


def abbreviate(text, rng, rate):
    words = []
    for word in text.split():
        short = ABBREV.get(word.lower())
        words.append(short if short and rng.random() < rate else word)
    return " ".join(words)


def drop_vowels(word):
    if len(word) < 6:
        return word
    return word[0] + "".join(ch for ch in word[1:] if ch.lower() not in "aeiou")


def describe(item, makes, rng):
    """Build one messy register description around an equipment noun."""
    parts = []
    make = rng.choice(makes) if makes and rng.random() < 0.6 else None
    model = model_code(rng) if rng.random() < 0.5 else None
    year = str(rng.randint(1988, 2026)) if rng.random() < 0.2 else None
    if rng.random() < 0.3:
        capacity = rng.choice(CAPACITY).format(n=rng.choice([2, 5, 10, 15, 20, 25, 40, 50, 75, 100, 150, 250, 500]))
    else:
        capacity = None
    core = [year, make, model, capacity, item]
    if rng.random() < 0.35:  # noun first, details after
        core = [item, make, model, capacity, year]
    parts.append(" ".join(p for p in core if p))
    if rng.random() < 0.15:
        qty = rng.randint(2, 24)
        parts[0] = rng.choice([f"({qty}) ", f"{qty} EA ", f"QTY {qty} ", "LOT OF "]) + parts[0]
    if rng.random() < 0.25:
        parts.append(f"S/N {rng.randint(10000, 9999999)}")
    if rng.random() < 0.3:
        parts.append(rng.choice(ADDERS))
    if rng.random() < 0.2:
        parts.append(rng.choice(LOCATIONS))
    if rng.random() < 0.1:
        parts.append(rng.choice([f"PO#{rng.randint(1000, 99999)}", f"CAPEX-{rng.randint(2005, 2026)}-{rng.randint(1, 250):03d}",
                                 f"AFE {rng.randint(100, 9999)}", f"INV {rng.randint(10000, 999999)}"]))
    text = rng.choice([" ", " - ", ", ", " / "]).join(parts)
    return noise(text, rng)


def noise(text, rng):
    text = abbreviate(text, rng, rate=0.5)
    if rng.random() < 0.12:
        text = " ".join(drop_vowels(w) if rng.random() < 0.4 else w for w in text.split())
    style = rng.random()
    if style < 0.7:
        text = text.upper()
    elif style < 0.85:
        text = text.title()
    if rng.random() < 0.2:  # legacy systems cut descriptions at a fixed width
        text = text[: rng.choice([25, 30, 40])].rstrip()
    return text


def vendor(makes, rng):
    if makes and rng.random() < 0.4:
        return f"{rng.choice(makes).upper()} {rng.choice(VENDOR_SUFFIX)}"
    return f"{rng.choice(DEALER_NAMES)} {rng.choice(VENDOR_SUFFIX)}"


def build_state(desc, gl, vend, cost, rng):
    """Render the register row as text, randomly omitting fields as real registers do."""
    fields = [f"description: {desc}"]
    if gl and rng.random() < 0.8:
        fields.append(f"gl_account: {gl}")
    if vend and rng.random() < 0.4:
        fields.append(f"vendor: {vend}")
    if cost and rng.random() < 0.85:
        fields.append(f"cost: {cost:,.0f}")
    if rng.random() < 0.8:
        fields.append(f"acquired: {rng.randint(1985, 2026)}-{rng.randint(1, 12):02d}")
    return " | ".join(fields)


def log_uniform(lo, hi, rng):
    return lo * (hi / lo) ** rng.random()


def in_scope_row(cls, rng):
    desc = describe(rng.choice(cls["items"]), cls["makes"], rng)
    gl = rng.choice(cls["gl"])
    if rng.random() < 0.1:  # registers often post assets to a generic or wrong account
        gl = rng.choice(["Machinery & Equipment", "Fixed Assets", "Plant & Equipment", "Other Equipment"])
    cost = log_uniform(*cls["cost"], rng)
    return {
        "state": build_state(desc, gl, vendor(cls["makes"], rng), cost, rng),
        "in_scope": "yes", "sector": cls["sector"],
        "major_category": cls["major_category"], "asset_class": cls["asset_class"],
    }


def out_of_scope_row(rng):
    kind = rng.choice(list(OUT_OF_SCOPE))
    gls, phrases = OUT_OF_SCOPE[kind]
    desc = noise(rng.choice(phrases) + (f" {rng.choice(LOCATIONS)}" if rng.random() < 0.3 else ""), rng)
    state = build_state(desc, rng.choice(gls), vendor([], rng), log_uniform(500, 2_000_000, rng), rng)
    return {"state": state, "in_scope": "no", "sector": NA, "major_category": NA, "asset_class": NA}


def unclear_row(rng):
    desc = noise(rng.choice(UNCLEAR) + (f" {rng.randint(1995, 2026)}" if rng.random() < 0.4 else ""), rng)
    gl = rng.choice(["Machinery & Equipment", "Fixed Assets", "Plant & Equipment", ""])
    state = build_state(desc, gl, None, log_uniform(1000, 5_000_000, rng), rng)
    return {"state": state, "in_scope": "unclear", "sector": NA, "major_category": NA, "asset_class": NA}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=60)
    ap.add_argument("--reject-share", type=float, default=0.12,
                    help="share of rows that are out-of-scope or unclear")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(HERE / "data" / "synthetic.csv"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    classes = load_taxonomy()
    rows = [in_scope_row(c, rng) for c in classes for _ in range(args.per_class)]
    n_reject = int(len(rows) * args.reject_share / (1 - args.reject_share))
    rows += [out_of_scope_row(rng) if rng.random() < 0.65 else unclear_row(rng) for _ in range(n_reject)]
    rng.shuffle(rows)
    for i, row in enumerate(rows):
        bucket = i % 10
        row["split"] = "test" if bucket == 0 else "validation" if bucket == 1 else "train"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["state", "in_scope", "sector", "major_category", "asset_class", "split"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows, {len(classes)} classes -> {out}")


if __name__ == "__main__":
    main()
