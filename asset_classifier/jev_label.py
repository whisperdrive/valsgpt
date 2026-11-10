"""Label register rows with Jev (TypeSafe System One API) against taxonomy.yaml.

Jev does not generate text, so it cannot write training rows. It is used here
as a teacher: it labels unlabelled register rows, and it audits synthetic rows
by labelling them blind so disagreements with the intended label can be found.

Each row costs one request with two questions: whether the row is machinery
and equipment at all, and which asset class it is (all classes as options;
sector and major category follow from the class).

Usage:
    # audit a stratified sample of the synthetic set
    python jev_label.py --in data/synthetic.csv --out data/jev_audit.csv --sample-per-class 5
    # label an unlabelled file that has a `state` column
    python jev_label.py --in my_rows.csv --out my_rows_labelled.csv

The API key is read from TYPESAFE_API_KEY or jev_api_key.
"""
import argparse
import csv
import os
import random
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests

from generate_synthetic import NA, load_taxonomy

URL = "https://api.typesafe.ai/v1/systemone"
SCOPE_OPTIONS = {
    "yes": "An identifiable tangible asset: machinery, equipment, vehicles, furniture, land, buildings or infrastructure.",
    "no": "Not a classifiable tangible asset: software, intangibles, construction in progress, "
          "services, repairs, fees, or consumables.",
    "unclear": "Too vague to tell what the asset is, such as 'misc equipment' or 'additions'.",
}


def build_questions(classes):
    options = {
        c["asset_class"]: f"{c['sector']} > {c['major_category']}. Examples: {', '.join(c['items'][:5])}"
        for c in classes
    }
    return {
        "in_scope": {
            "type": "choice",
            "instructions": "Is this fixed asset register entry an identifiable tangible asset?",
            "criteria": SCOPE_OPTIONS,
        },
        "asset_class": {
            "type": "choice",
            "instructions": "Which asset class does this fixed asset register entry belong to?",
            "criteria": options,
        },
    }


def ask(session, key, state, questions, model, retries=6):
    body = {"model": model, "state": state, "questions": questions}
    for attempt in range(retries):
        try:
            resp = session.post(URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=60)
        except requests.exceptions.ConnectionError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (429, 529, 500, 502, 503):
            time.sleep(float(resp.headers.get("retry-after", 2 ** attempt)))
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sample-per-class", type=int, default=0,
                    help="if the input has labels, take this many rows per class (0 = all rows)")
    ap.add_argument("--model", default="jev-latest")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("jev_api_key")
    if not key:
        raise SystemExit("set TYPESAFE_API_KEY (or jev_api_key)")

    classes = load_taxonomy()
    by_class = {c["asset_class"]: c for c in classes}
    questions = build_questions(classes)

    with open(args.src, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if args.sample_per_class and "asset_class" in rows[0]:
        rng = random.Random(args.seed)
        groups = defaultdict(list)
        for row in rows:
            groups[(row["in_scope"], row["asset_class"])].append(row)
        rows = []
        for (scope, _), members in sorted(groups.items()):
            # rejected rows share one group, so take a larger sample of them
            take = args.sample_per_class if scope == "yes" else args.sample_per_class * 10
            rows += rng.sample(members, min(take, len(members)))

    session = requests.Session()
    tokens = 0

    def label(row):
        answer = ask(session, key, row["state"], questions, args.model)
        scope, cls = answer["answers"]["in_scope"], answer["answers"]["asset_class"]
        spec = by_class[cls["choice"]]
        in_scope = scope["choice"] == "yes"
        return {
            "state": row["state"],
            "jev_in_scope": scope["choice"],
            "jev_in_scope_confidence": scope["confidence"],
            "jev_sector": spec["sector"] if in_scope else NA,
            "jev_major_category": spec["major_category"] if in_scope else NA,
            "jev_asset_class": cls["choice"] if in_scope else NA,
            "jev_class_confidence": cls["confidence"],
            "jev_class_probability": cls["probabilities"][cls["choice"]],
            **{f"intended_{k}": row[k] for k in ("in_scope", "sector", "major_category", "asset_class") if k in row},
            **{k: v for k, v in row.items() if k.startswith("ref_")},
        }, answer["usage"]["input_tokens"]

    results = []
    with ThreadPoolExecutor(args.workers) as pool:
        for i, (result, used) in enumerate(pool.map(label, rows), 1):
            results.append(result)
            tokens += used
            if i % 100 == 0:
                print(f"{i}/{len(rows)} rows, {tokens:,} input tokens")

    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f"{len(results)} rows -> {args.out}; {tokens:,} input tokens")

    if "intended_asset_class" in results[0]:
        for level in ("in_scope", "sector", "major_category", "asset_class"):
            pool_ = results if level == "in_scope" else [r for r in results if r["intended_in_scope"] == "yes"]
            hits = sum(r[f"jev_{level}"] == r[f"intended_{level}"] for r in pool_)
            print(f"agreement on {level}: {hits}/{len(pool_)} = {hits / len(pool_):.1%}")


if __name__ == "__main__":
    main()
