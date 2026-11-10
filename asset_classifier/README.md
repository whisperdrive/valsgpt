# Asset classifier training data

Training data for a local classifier (Laya fine-tune) that assigns fixed asset
register rows to a machinery and equipment class, for use in a cost-approach
valuation.

## Files

| File | Purpose |
|---|---|
| `taxonomy.yaml` | Three levels: sector, major category, asset class. Edit this first. |
| `generate_synthetic.py` | Writes labelled, register-style rows from the taxonomy. |
| `jev_label.py` | Labels rows with Jev, or audits synthetic rows against it. |
| `data/synthetic.csv` | Generated training set, with train / validation / test split. |
| `data/jev_audit.csv` | Jev's blind labels for a sample of the synthetic set. |

## Taxonomy status

The taxonomy is a draft. It is organised the way ASA's Machinery & Technical
Specialties material is (industry, then asset type), but it was written from
general knowledge and has not been checked against ASA's licensed tables.
Review it against the ASA Estimated Normal Useful Life Study, then attach a
normal useful life and a cost index series to each class.

## Row format

`state` is the register row as text; the other columns are the answers.

```
state:          description: (3) TOSHIBA INJECTION MOLDING MACH | gl_account: Production Equipment | cost: 917,477 | acquired: 1997-05
in_scope:       yes | no | unclear
sector:         Manufacturing - Plastics, Rubber & Packaging
major_category: Plastics & Rubber Processing
asset_class:    Injection Molding Machines
```

Rows that are not machinery and equipment (software, buildings, land,
construction in progress, expensed items) are `in_scope = no`. Rows too vague
to classify are `in_scope = unclear`. Both carry `not_applicable` in the three
taxonomy columns, so the model learns to reject or escalate them.

## Regenerating

```bash
python generate_synthetic.py --per-class 60
```

```bash
python jev_label.py --in data/synthetic.csv --out data/jev_audit.csv --sample-per-class 5
```

`jev_label.py` reads the key from `TYPESAFE_API_KEY` or `jev_api_key`. One row
costs about 6,600 input tokens, because all classes are sent as options.

## Known limits

- The synthetic rows come from templates and a fixed vocabulary. Accuracy on
  them says little about accuracy on real registers; a hand-labelled set of
  real rows is still needed for testing.
- Model numbers and capacities are random, so they carry no signal.
- No open data has been added yet.
