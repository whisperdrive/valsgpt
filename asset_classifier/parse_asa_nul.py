"""Read normal useful life bands out of a licensed copy of the ASA study.

Input: the PDF of the ASA Machinery & Technical Specialties Committee
"Estimated Normal Useful Life Study" (2024). The study is copyright ASA, so
neither the PDF nor anything this script writes belongs in the repository:
output goes to `local/`, which is git-ignored.

Output: local/asa_nul_2024.csv, one row per life band:
    sector, classification, nul_low, nul_high, assets ("; "-separated)

Needs `pdftotext` (poppler-utils) on the path.

Usage:
    python parse_asa_nul.py /path/to/mtsc-normal-useful-life-study-update-2024.pdf
"""
import argparse
import csv
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
BAND = re.compile(r"\s(\d{1,3})\s{2,}(\d{1,3})\s*$")
SKIP = ("Copyright 2024", "Estimated Normal Useful Life Study", "Asset Classification", "Assets Captured")


def contents(lines):
    """Sector names from the table of contents, and the line where the tables start."""
    start = next(i for i, l in enumerate(lines) if l.strip() == "Table of Contents")
    sectors = []
    for i in range(start + 1, len(lines)):
        m = re.match(r"\s{2}(\S.*?)\s*\.{5,}", lines[i])
        if m:
            sectors.append(m.group(1).strip())
        elif sectors and "Copyright" in lines[i]:
            return sectors, i
    raise ValueError("table of contents not found")


def parse(text):
    lines = text.split("\n")
    sectors, first = contents(lines)
    bands, sector, cls, band, in_notes = [], None, None, None, False

    body = lines[first:]
    for n, line in enumerate(body):
        if line and not line.startswith(" "):
            hit = [s for s in sectors if s.startswith(line.strip()[:18])]
            if hit and not line.startswith("Estimated"):
                if len(hit) > 1:  # a heading that wraps: the next line tells the sectors apart
                    following = next((x.strip() for x in body[n + 1:] if x.strip()), "")
                    hit = [s for s in hit if following[:12] in s] or hit
                sector, cls, band, in_notes = hit[0], None, None, False
                continue
        if not sector or in_notes or any(s in line for s in SKIP) or re.fullmatch(r"\s*(NUL\s+NUL|Low\s+High)\s*", line):
            continue
        if line.strip().startswith("Key Considerations"):
            in_notes = True
            continue
        if not line.strip():
            continue

        m = BAND.search(line)
        if m:
            line = line[: m.start()]
        bullet = line.find("•")
        indent = len(line) - len(line.lstrip())
        if bullet > 0 and indent <= 2:
            label, rest = line[:bullet].strip(), line[bullet:]
        elif bullet > 0:
            # text before the first bullet is the tail of a wrapped asset name in the left column
            label, rest = "", line
        elif indent <= 2:
            parts = re.split(r"\s{3,}", line.strip(), maxsplit=1)
            label, rest = parts[0], (" " * 40 + parts[1] if len(parts) > 1 else "")
        else:
            label, rest = "", line

        if m:
            if label:
                cls = label  # a label on the first line of a band starts a new classification
            band = {"sector": sector, "classification": cls, "nul_low": int(m.group(1)),
                    "nul_high": int(m.group(2)), "assets": []}
            bands.append(band)
        elif label and cls is not None:
            # the rest of a classification name that wrapped onto later lines
            new = f"{cls} {label}"
            for b in bands:
                if b["sector"] == sector and b["classification"] == cls:
                    b["classification"] = new
            cls = new

        if band is None:
            continue
        lead = rest.split("•")[0]
        if lead.strip() and band["assets"]:
            # a wrapped asset name: join it to the nearest asset in the same column
            pos = len(lead) - len(lead.lstrip())
            nearest = min(band["assets"], key=lambda a: abs(a[0] - pos) if a[0] <= pos + 6 else 999)
            nearest[1] += " " + lead.strip()
        for piece in re.finditer(r"•\s*([^•]+)", rest):
            band["assets"].append([piece.start(), piece.group(1).strip()])

    for b in bands:
        b["classification"] = re.sub(r"\s+", " ", b["classification"] or "").strip()
        b["assets"] = "; ".join(re.sub(r"\s+", " ", a[1]) for a in b["assets"])
    return sectors, bands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", default=str(HERE / "local" / "asa_nul_2024.csv"))
    args = ap.parse_args()

    text = subprocess.run(["pdftotext", "-layout", args.pdf, "-"], check=True, capture_output=True, text=True).stdout
    sectors, bands = parse(text)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["sector", "classification", "nul_low", "nul_high", "assets"])
        writer.writeheader()
        writer.writerows(bands)
    found = {b["sector"] for b in bands}
    print(f"{len(bands)} life bands in {len(found)} of {len(sectors)} sectors -> {out}")
    for s in sectors:
        if s not in found:
            print(f"  no bands read for: {s}")


if __name__ == "__main__":
    main()
