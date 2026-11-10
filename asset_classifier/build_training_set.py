"""Combine synthetic rows with Jev-labelled real rows into the training files.

Real rows are split three ways:
  * a random hold-out, written to data/real_test_to_review.csv. Jev's label is
    only a suggestion there; a person must confirm or correct each row before
    it is used as the test set. These rows never enter training.
  * rows Jev labelled with high confidence, added to training as-is.
  * the remainder, written to data/review_queue.csv for a person to label.

Usage:
    python build_training_set.py --real data/indiana_jev_labelled.csv
"""
import argparse
import csv
import random
from pathlib import Path

HERE = Path(__file__).parent
LABELS = ["in_scope", "sector", "major_category", "asset_class"]


def read(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def write(path, rows, fields):
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows):>6} rows -> {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", default=str(HERE / "data" / "synthetic.csv"))
    ap.add_argument("--real", nargs="+", required=True, help="output files of jev_label.py")
    ap.add_argument("--holdout", type=int, default=500)
    ap.add_argument("--min-confidence", type=float, default=0.9)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    real = [row for path in args.real for row in read(path)]
    random.Random(args.seed).shuffle(real)
    holdout, rest = real[: args.holdout], real[args.holdout:]

    confident, queue = [], []
    for row in rest:
        scope_ok = float(row["jev_in_scope_confidence"]) >= args.min_confidence
        class_ok = row["jev_in_scope"] != "yes" or float(row["jev_class_confidence"]) >= args.min_confidence
        (confident if scope_ok and class_ok else queue).append(row)

    train = [{**row, "source": "synthetic"} for row in read(args.synthetic)]
    for row in confident:
        train.append({"state": row["state"], **{k: row[f"jev_{k}"] for k in LABELS},
                      "split": "train", "source": "real_jev_labelled"})

    data = HERE / "data"
    write(data / "training_set.csv", train, ["state", *LABELS, "split", "source"])
    review_fields = ["state", *[f"jev_{k}" for k in LABELS], "jev_class_confidence",
                     "ref_asset_type", "ref_category", "ref_profile",
                     *[f"reviewed_{k}" for k in LABELS]]
    write(data / "real_test_to_review.csv", holdout, review_fields)
    write(data / "review_queue.csv", queue, review_fields)


if __name__ == "__main__":
    main()
