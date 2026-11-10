"""Attach ASA normal useful life ranges to the taxonomy's asset classes.

Reads local/asa_nul_2024.csv (written by parse_asa_nul.py from a licensed copy
of the ASA study) and writes local/class_lives.csv. Both files stay out of the
repository because the life figures are ASA's copyright.

For each asset class under an ASA heading, the script looks at the life bands
of that ASA classification and picks the band whose asset list shares the most
words with the class's own name and item vocabulary:

    match = band            a band's asset list shares words with the class
    match = classification  no band matched; the range spans the whole classification
    match = none            the class is an extension with no ASA heading

Every match is a word-overlap guess. `matched_on` shows the shared words so a
person can check each one; a match on a single shared word is weak.

Usage:
    python attach_lives.py
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

from generate_synthetic import load_taxonomy

HERE = Path(__file__).parent
STOP = {"and", "or", "the", "of", "for", "to", "with", "other", "equipment", "machine", "machines", "machinery",
        "system", "systems", "unit", "units", "general", "types", "type", "various", "etc", "related", "assets"}


def words(text):
    out = set()
    for w in re.findall(r"[a-z]+", text.lower()):
        w = w[:-1] if len(w) > 4 and w.endswith("s") else w  # crude singular
        if len(w) > 2 and w not in STOP and w + "s" not in STOP:
            out.add(w)
    return out


def name_words(text):
    return set(re.findall(r"[a-z]+", text.lower()))


def main():
    bands = defaultdict(list)
    with open(HERE / "local" / "asa_nul_2024.csv", newline="") as fh:
        for row in csv.DictReader(fh):
            bands[row["sector"]].append(row)

    rows = []
    for cls in load_taxonomy():
        row = {"asset_class": cls["asset_class"], "sector": cls["sector"], "classification": cls["major_category"],
               "basis": cls["basis"], "asa_nul_low": "", "asa_nul_high": "", "match": "none", "shared_words": 0, "matched_on": ""}
        rows.append(row)
        if cls["basis"] != "asa":
            continue
        # the parser can leave stray words on a classification name, so compare names as word sets
        ours = name_words(cls["major_category"])
        group = [b for b in bands[cls["sector"]] if ours <= name_words(b["classification"])]
        if not group:
            group = [b for b in bands[cls["sector"]]
                     if len(name_words(b["classification"])) >= 2 and name_words(b["classification"]) <= ours]
        if not group:
            continue
        vocab = words(cls["asset_class"] + " " + " ".join(cls["items"]))
        scored = sorted(((len(vocab & words(b["assets"])), b) for b in group), key=lambda t: -t[0])
        best_score, best = scored[0]
        if best_score:
            row.update(asa_nul_low=best["nul_low"], asa_nul_high=best["nul_high"], match="band",
                       shared_words=best_score, matched_on=" ".join(sorted(vocab & words(best["assets"]))))
        else:
            row.update(asa_nul_low=min(int(b["nul_low"]) for b in group),
                       asa_nul_high=max(int(b["nul_high"]) for b in group), match="classification")

    out = HERE / "local" / "class_lives.csv"
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    counts = defaultdict(int)
    for row in rows:
        counts[row["match"]] += 1
    print(f"{len(rows)} classes -> {out}")
    for kind in ("band", "classification", "none"):
        print(f"  {kind}: {counts[kind]}")
    print("  band matches resting on one shared word:", sum(r["match"] == "band" and r["shared_words"] == 1 for r in rows))
    unmatched = [r["asset_class"] for r in rows if r["basis"] == "asa" and r["match"] == "none"]
    if unmatched:
        print("  under an ASA heading but no ASA classification found:", "; ".join(unmatched))


if __name__ == "__main__":
    main()
