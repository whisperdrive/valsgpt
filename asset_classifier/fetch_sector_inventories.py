"""Build labelled register rows from public US asset inventories.

Sources (all US federal, public):
  * FAA Releasable Aircraft Database  - registry.faa.gov/database/ReleasableAircraft.zip
  * EIA Form 860 (2025)               - www.eia.gov/electricity/data/eia860/
  * FTA National Transit Database     - data.transportation.gov (revenue vehicles,
                                        service vehicles, facilities)

These are inventories, not accounting registers: one clean record per aircraft,
generator, vehicle or facility. The label comes from the source's own type
field, so it is reliable. The description text is assembled here from the real
attributes (year, maker, model, size) in a few register-like layouts, so the
wording is partly templated.

Owner names, addresses, registration and serial numbers are not used.

Usage:
    python fetch_sector_inventories.py --raw /path/to/raw --out data/sector_inventories.csv

`--raw` must contain the unzipped FAA files (MASTER.txt, ACFTREF.txt,
ENGINE.txt), the unzipped EIA-860 workbooks, and the three NTD CSV exports
named ifzt-j53d.csv, 5en4-yiki.csv and mbm2-ck6q.csv.
"""
import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

import openpyxl

from generate_synthetic import abbreviate, load_taxonomy

HERE = Path(__file__).parent

EIA_CLASS = {
    "Solar Photovoltaic": "Solar Generation Equipment",
    "Solar Thermal without Energy Storage": "Solar Generation Equipment",
    "Solar Thermal with Energy Storage": "Solar Generation Equipment",
    "Conventional Hydroelectric": "Hydroelectric Generating Units",
    "Hydroelectric Pumped Storage": "Hydroelectric Generating Units",
    "Natural Gas Fired Combustion Turbine": "Combustion Turbine & Combined Cycle Plants",
    "Natural Gas Fired Combined Cycle": "Combustion Turbine & Combined Cycle Plants",
    "Natural Gas Internal Combustion Engine": "Reciprocating Engine Power Plants",
    "Landfill Gas": "Reciprocating Engine Power Plants",
    "Onshore Wind Turbine": "Wind Turbines",
    "Offshore Wind Turbine": "Wind Turbines",
    "Batteries": "Battery Energy Storage Systems",
    "Flywheels": "Battery Energy Storage Systems",
    "Natural Gas Steam Turbine": "Steam & Nuclear Generating Units",
    "Conventional Steam Coal": "Steam & Nuclear Generating Units",
    "Nuclear": "Steam & Nuclear Generating Units",
    "Petroleum Coke": "Steam & Nuclear Generating Units",
    "Wood/Wood Waste Biomass": "Biomass, Geothermal & Other Renewable Units",
    "Other Waste Biomass": "Biomass, Geothermal & Other Renewable Units",
    "Geothermal": "Biomass, Geothermal & Other Renewable Units",
    "Municipal Solid Waste": "Biomass, Geothermal & Other Renewable Units",
}
# Petroleum liquids units are engines or turbines depending on the prime mover.
EIA_PETROLEUM = {"IC": "Reciprocating Engine Power Plants",
                 "GT": "Combustion Turbine & Combined Cycle Plants",
                 "ST": "Steam & Nuclear Generating Units"}
PRIME_MOVER = {"IC": "internal combustion engine", "GT": "gas turbine", "ST": "steam turbine",
               "CT": "combined cycle combustion turbine", "CA": "combined cycle steam turbine",
               "CS": "combined cycle single shaft", "HY": "hydro turbine", "PS": "pumped storage unit",
               "PV": "solar PV", "WT": "wind turbine", "BA": "battery storage", "BT": "binary cycle turbine"}

NTD_CLASS = {
    "Bus": "Buses & Transit Vehicles", "Articulated Bus": "Buses & Transit Vehicles",
    "Over-the-road Bus": "Buses & Transit Vehicles", "Cutaway": "Buses & Transit Vehicles",
    "School Bus": "Buses & Transit Vehicles", "Double Decker Bus": "Buses & Transit Vehicles",
    "Trolleybus": "Buses & Transit Vehicles",
    "Van": "Passenger Cars & Light Trucks", "Minivan": "Passenger Cars & Light Trucks",
    "Sports Utility Vehicle": "Passenger Cars & Light Trucks", "Automobile": "Passenger Cars & Light Trucks",
    "Commuter Rail Passenger Coach": "Rail Transit Vehicles", "Commuter Rail Locomotive": "Rail Transit Vehicles",
    "Commuter Rail Self-Propelled Passenger Car": "Rail Transit Vehicles",
    "Heavy Rail Passenger Car": "Rail Transit Vehicles", "Light Rail Vehicle": "Rail Transit Vehicles",
    "Vintage Trolley": "Rail Transit Vehicles", "Cable Car": "Rail Transit Vehicles",
    "Ferryboat": "Vessels & Barges",
}
# "Trucks and other Rubber Tire Vehicles" mixes SUVs, pickups and heavy trucks, so it is not used.
NTD_SERVICE_CLASS = {"Automobiles": "Passenger Cars & Light Trucks"}
FAA_AIRCRAFT_CLASS = {"4": "Fixed-Wing Aircraft", "5": "Fixed-Wing Aircraft",
                      "6": "Helicopters & Rotorcraft", "9": "Helicopters & Rotorcraft"}
FAA_AIRCRAFT_WORD = {"4": ["aircraft", "airplane", "single engine aircraft", ""],
                     "5": ["aircraft", "twin engine aircraft", "multi-engine airplane", ""],
                     "6": ["helicopter", "rotorcraft", "helo", ""], "9": ["gyroplane", "gyrocopter"]}
FAA_ENGINE_WORD = {"1": "reciprocating engine", "2": "turboprop engine", "3": "turboshaft engine",
                   "4": "turbojet engine", "5": "turbofan engine", "7": "2-cycle engine", "8": "4-cycle engine"}


def style(text, rng):
    """Apply the casing and abbreviation habits of a register, without truncating."""
    text = " ".join(text.split())
    text = abbreviate(text, rng, rate=0.3)
    roll = rng.random()
    return text.upper() if roll < 0.6 else text.title() if roll < 0.75 else text


def stratified(records, key, per_group, rng):
    groups = defaultdict(list)
    for rec in records:
        groups[key(rec)].append(rec)
    out = []
    for name in sorted(groups, key=str):
        out += rng.sample(groups[name], min(per_group, len(groups[name])))
    return out


def faa_rows(raw, rng, per_group):
    def table(name):
        with open(raw / name, newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            header = [h.strip() for h in next(reader)]
            for line in reader:
                yield {h: v.strip() for h, v in zip(header, line)}

    models = {r["CODE"]: r for r in table("ACFTREF.txt")}
    aircraft = []
    for rec in table("MASTER.txt"):
        ref = models.get(rec["MFR MDL CODE"])
        # BUILD-CERT-IND 0 = type-certificated. Amateur-built aircraft are skipped because
        # their "manufacturer" is the name of the private individual who built them.
        if (ref and ref["TYPE-ACFT"] in FAA_AIRCRAFT_CLASS and ref["BUILD-CERT-IND"] == "0"
                and rec["YEAR MFR"].isdigit()):
            aircraft.append((rec["YEAR MFR"], ref))
    # sample across aircraft type and seat count so airliners are not swamped by light piston aircraft
    def seat_band(item):
        seats = int(item[1]["NO-SEATS"] or 0)
        return item[1]["TYPE-ACFT"], item[1]["TYPE-ENG"], min(seats // 20, 10)
    for year, ref in stratified(aircraft, seat_band, per_group, rng):
        word = rng.choice(FAA_AIRCRAFT_WORD[ref["TYPE-ACFT"]])
        layout = rng.choice(["{y} {m} {d} {w}", "{m} {d} {w}", "{w} {m} {d} {y}", "{m} {d}", "{y} {m} {d}"])
        desc = layout.format(y=year, m=ref["MFR"], d=ref["MODEL"], w=word)
        yield desc, FAA_AIRCRAFT_CLASS[ref["TYPE-ACFT"]], "FAA aircraft registry"

    engines = [r for r in table("ENGINE.txt") if r["TYPE"] in FAA_ENGINE_WORD and r["MFR"] != "NONE"]
    for ref in stratified(engines, lambda r: r["TYPE"], per_group * 2, rng):
        word = rng.choice([FAA_ENGINE_WORD[ref["TYPE"]], "aircraft engine", "spare engine", "engine"])
        power = int(ref["HORSEPOWER"] or 0)
        size = f" {power} HP" if power and rng.random() < 0.4 else ""
        yield f"{ref['MFR']} {ref['MODEL']} {word}{size}", "Aircraft Engines & Rotables", "FAA aircraft registry"


def sheet_records(path):
    ws = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    rows = ws.iter_rows(values_only=True)
    next(rows)
    header = list(next(rows))
    for row in rows:
        yield dict(zip(header, row))


def eia_rows(raw, rng, per_group):
    def mw(value):
        try:
            return f"{float(value):g} MW"
        except (TypeError, ValueError):
            return ""

    gens = [g for g in sheet_records(raw / "3_1_Generator_Y2025.xlsx") if g.get("Technology")]
    for g in stratified(gens, lambda g: (g["Technology"], g["Prime Mover"]), per_group, rng):
        tech, mover = g["Technology"], g["Prime Mover"]
        cls = EIA_PETROLEUM.get(mover) if tech == "Petroleum Liquids" else EIA_CLASS.get(tech)
        if not cls or tech in ("Onshore Wind Turbine", "Offshore Wind Turbine", "Solar Photovoltaic", "Batteries"):
            continue  # wind, solar and storage come from their own, more detailed sheets
        what = rng.choice([tech, PRIME_MOVER.get(mover, tech), f"{tech} generating unit"])
        layout = rng.choice(["{p} unit {u} - {c} {w}", "{c} {w} - {p} #{u}", "{p} gen {u} {w} {c}",
                             "{w} {c} ({p})", "{p} {w}"])
        desc = layout.format(p=g["Plant Name"], u=g["Generator ID"], c=mw(g["Nameplate Capacity (MW)"]), w=what)
        yield desc, cls, "EIA-860"

    wind = [w for w in sheet_records(raw / "3_2_Wind_Y2025.xlsx") if w.get("Predominant Turbine Manufacturer")]
    for w in stratified(wind, lambda w: w["Predominant Turbine Manufacturer"], max(2, per_group // 8), rng):
        layout = rng.choice(["({n}) {m} {d} wind turbines - {p}", "{p} wind farm {c} - {m} {d}",
                             "{m} {d} wind turbine generators qty {n}", "{p} {c} wind turbines"])
        desc = layout.format(n=w["Number of Turbines"], m=w["Predominant Turbine Manufacturer"],
                             d=w["Predominant Turbine Model Number"] or "", p=w["Plant Name"],
                             c=mw(w["Nameplate Capacity (MW)"]))
        yield desc, "Wind Turbines", "EIA-860"

    solar = [s for s in sheet_records(raw / "3_3_Solar_Y2025.xlsx") if s.get("Plant Name")]
    for s in rng.sample(solar, min(per_group * 6, len(solar))):
        mount = ("single-axis tracker" if s.get("Single-Axis Tracking?") == "Y"
                 else "fixed tilt" if s.get("Fixed Tilt?") == "Y" else "")
        module = "thin film" if s.get("Thin-Film (CdTe)?") == "Y" else rng.choice(["", "crystalline silicon"])
        layout = rng.choice(["{p} {c} solar PV array {m}", "{c} AC solar photovoltaic plant - {p}",
                             "{p} PV modules {k} {m}", "solar array {c} {m} {p}", "{p} solar {c}"])
        yield layout.format(p=s["Plant Name"], c=mw(s["Nameplate Capacity (MW)"]), m=mount, k=module), \
            "Solar Generation Equipment", "EIA-860"

    storage = [b for b in sheet_records(raw / "3_4_Energy_Storage_Y2025.xlsx") if b.get("Plant Name")]
    for b in rng.sample(storage, min(per_group * 6, len(storage))):
        chem = {"LIB": "lithium-ion", "FLB": "flow battery", "NIB": "nickel", "PBB": "lead acid"}.get(
            b.get("Storage Technology 1"), "")
        energy = f"/ {b['Nameplate Energy Capacity (MWh)']} MWh" if b.get("Nameplate Energy Capacity (MWh)") else ""
        layout = rng.choice(["{p} battery energy storage system {c} {e}", "BESS {c} {e} {k} - {p}",
                             "{k} battery storage {c} {p}", "{p} energy storage {c}"])
        yield layout.format(p=b["Plant Name"], c=mw(b["Nameplate Capacity (MW)"]), e=energy, k=chem), \
            "Battery Energy Storage Systems", "EIA-860"


def ntd_rows(raw, rng, per_group):
    def read(name):
        with open(raw / name, newline="", encoding="utf-8-sig") as fh:
            return list(csv.DictReader(fh))

    vehicles = [v for v in read("ifzt-j53d.csv") if v["Vehicle Type"] in NTD_CLASS]
    for v in stratified(vehicles, lambda v: v["Vehicle Type"], per_group * 2, rng):
        maker = v["Manufacturer"].split("(")[0].split("—")[0].strip()
        length = f"{v['Vehicle Length']}'" if v["Vehicle Length"] and rng.random() < 0.5 else ""
        fuel = v["Fuel Type"] if rng.random() < 0.4 else ""
        qty = f"({v['Total Fleet Vehicles']}) " if v["Total Fleet Vehicles"] not in ("", "1") and rng.random() < 0.3 else ""
        layout = rng.choice(["{q}{y} {m} {d} {l} {t} {f}", "{q}{t} {m} {d} {y}", "{q}{m} {d} {t}", "{q}{y} {m} {d}"])
        desc = layout.format(q=qty, y=v["Manufacture Year"], m=maker, d=v["Model"], l=length,
                             t=v["Vehicle Type"], f=fuel)
        yield desc, NTD_CLASS[v["Vehicle Type"]], "FTA National Transit Database"

    # fleet names that are only an ID number carry no description, so they are skipped
    service = [s for s in read("5en4-yiki.csv") if s["Vehicle Type"] in NTD_SERVICE_CLASS
               and sum(ch.isalpha() for ch in s["Service Fleet Name"]) >= 4]
    for s in stratified(service, lambda s: s["Vehicle Type"], per_group * 4, rng):
        desc = f"{s['Year of Manufacture']} {s['Service Fleet Name']}" if rng.random() < 0.6 else s["Service Fleet Name"]
        yield desc, NTD_SERVICE_CLASS[s["Vehicle Type"]], "FTA National Transit Database"

    facilities = [f for f in read("mbm2-ck6q.csv") if f["Facility Name"]]
    for f in stratified(facilities, lambda f: f["Facility Type"], per_group, rng):
        kind = f["Facility Type"].split("(")[0].split(",")[0].strip()
        layout = rng.choice(["{n} - {k}", "{n}", "{k} {n}", "{n} {k} {sf}"])
        sf = f"{f['Square Feet']} SF" if f["Square Feet"] else ""
        yield layout.format(n=f["Facility Name"], k=kind, sf=sf), \
            "Transit Stations & Maintenance Facilities", "FTA National Transit Database"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="directory holding the unpacked source files")
    ap.add_argument("--per-group", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(HERE / "data" / "sector_inventories.csv"))
    args = ap.parse_args()

    raw, rng = Path(args.raw), random.Random(args.seed)
    by_class = {c["asset_class"]: c for c in load_taxonomy()}
    rows, seen = [], set()
    for maker in (faa_rows, eia_rows, ntd_rows):
        for desc, cls, source in maker(raw, rng, args.per_group):
            spec = by_class[cls]
            desc = style(desc, rng)
            if desc in seen:
                continue
            seen.add(desc)
            fields = [f"description: {desc}"]
            if rng.random() < 0.7:
                fields.append(f"gl_account: {rng.choice(spec['gl'])}")
            rows.append({"state": " | ".join(fields), "in_scope": "yes", "sector": spec["sector"],
                         "major_category": spec["major_category"], "asset_class": cls, "source": source})

    rng.shuffle(rows)
    for i, row in enumerate(rows):
        row["split"] = "test" if i % 10 == 0 else "validation" if i % 10 == 1 else "train"
    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["state", "in_scope", "sector", "major_category",
                                                "asset_class", "split", "source"])
        writer.writeheader()
        writer.writerows(rows)
    counts = defaultdict(int)
    for row in rows:
        counts[(row["source"], row["asset_class"])] += 1
    for key in sorted(counts):
        print(f"{counts[key]:>5}  {key[0]}: {key[1]}")
    print(f"{len(rows)} rows -> {args.out}")


if __name__ == "__main__":
    main()
