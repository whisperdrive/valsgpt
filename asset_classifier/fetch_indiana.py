"""Turn Indiana's public state asset register into unlabelled register rows.

Source: "Assets Data", Indiana Management Performance Hub
https://hub.mph.in.gov/dataset/assets-data  (licence not specified on the portal)

The register lists state assets with an acquisition cost of $500 or more. Each
distinct description is kept once, then a sample is drawn across the
register's own "Profile Description" values so rare asset types are included.

The state's own labels (asset type, category, profile) are kept in `ref_*`
columns for checking. Only the category goes into `state`, standing in for a
general ledger account; the profile is left out because it is close to the
answer.

Usage:
    python fetch_indiana.py --raw /path/to/assets.csv --per-profile 5 --out data/indiana_sample.csv
    python fetch_indiana.py --download /path/to/assets.csv   # fetch the raw file first
"""
import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

import requests

URL = ("https://hub.mph.in.gov/dataset/d59428e9-8e53-4e5f-8b45-4189efc5c5d1/resource/"
       "5cd10ef2-6b82-47f4-a154-c34f581628a6/download/assets.csv")
HERE = Path(__file__).parent


def download(dest):
    with requests.get(URL, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(1 << 20):
                fh.write(chunk)


def to_state(row):
    fields = [f"description: {row['Asset Description'].strip()}"]
    if row["Category Description"].strip():
        fields.append(f"gl_account: {row['Category Description'].strip()}")
    try:
        fields.append(f"cost: {float(row['Acquisition Cost']):,.0f}")
    except ValueError:
        pass
    month, _, year = row["Acquisition Date"].partition("/")[0], None, row["Acquisition Date"][-4:]
    if year.isdigit():
        fields.append(f"acquired: {year}-{int(month):02d}")
    return " | ".join(fields)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", help="path to the downloaded assets.csv")
    ap.add_argument("--download", help="download the raw file to this path and exit")
    ap.add_argument("--per-profile", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(HERE / "data" / "indiana_sample.csv"))
    args = ap.parse_args()

    if args.download:
        download(args.download)
        return
    if not args.raw:
        ap.error("--raw or --download is required")

    by_profile = defaultdict(dict)
    with open(args.raw, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            desc = row["Asset Description"].strip()
            if desc:
                by_profile[row["Profile Description"]].setdefault(desc.upper(), row)

    rng = random.Random(args.seed)
    picked = []
    for profile in sorted(by_profile):
        rows = list(by_profile[profile].values())
        picked += rng.sample(rows, min(args.per_profile, len(rows)))

    with open(args.out, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["state", "ref_asset_type", "ref_category", "ref_profile"])
        for row in picked:
            writer.writerow([to_state(row), row["Asset Type Description"],
                             row["Category Description"], row["Profile Description"]])
    distinct = sum(len(v) for v in by_profile.values())
    print(f"{distinct} distinct descriptions in {len(by_profile)} profiles; sampled {len(picked)} -> {args.out}")


if __name__ == "__main__":
    main()
