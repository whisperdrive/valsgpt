# Asset classifier training data

Training data for a local classifier (Laya fine-tune) that assigns fixed asset
register rows to a machinery and equipment class, for use in a cost-approach
valuation.

## Files

| File | Purpose |
|---|---|
| `taxonomy.yaml` | Three levels: sector, asset classification, asset class. Edit this first. |
| `generate_synthetic.py` | Writes labelled, register-style rows from the taxonomy. |
| `jev_label.py` | Labels rows with Jev, or audits synthetic rows against it. |
| `fetch_indiana.py` | Samples real rows from Indiana's public state asset register. |
| `fetch_sector_inventories.py` | Builds labelled rows from public inventories: FAA aircraft, EIA power plants and refineries, FTA transit, BSEE offshore platforms, MSHA mines, and Indiana land and building rows. |
| `parse_asa_nul.py` | Reads life bands from a licensed PDF of the ASA study into `local/` (git-ignored). |
| `attach_lives.py` | Matches each asset class to an ASA life band; writes `local/class_lives.csv` (git-ignored). |
| `build_training_set.py` | Merges synthetic and Jev-labelled real rows; writes the review files. |
| `data/synthetic.csv` | Generated rows, with train / validation / test split. |
| `data/jev_audit.csv` | Jev's blind labels for a sample of the synthetic set. |
| `data/indiana_sample.csv` | 3,093 real register rows, unlabelled, with the state's own categories. |
| `data/indiana_jev_labelled.csv` | The same rows with Jev's labels and confidence. |
| `data/sector_inventories.csv` | 8,864 rows built from real aircraft, generator, refinery, platform, mine, transit and real estate records; labels come from the source's own type field. |
| `data/training_set.csv` | Synthetic rows, sector inventory rows, and Indiana rows Jev labelled at 0.9 confidence or above. The `source` column says which. |
| `data/real_test_to_review.csv` | 500 real rows held out of training. Jev's label is a suggestion; fill the `reviewed_*` columns by hand to make this the test set. |
| `data/review_queue.csv` | Real rows Jev was unsure about, for hand labelling. |

## Taxonomy status

Version 2. Three levels: sector, asset classification, asset class.

- The sector and asset classification headings follow the ASA Machinery &
  Technical Specialties Committee "Estimated Normal Useful Life Study" (2024):
  all 36 ASA sectors are present.
- Seven further sectors, marked "(not in ASA study)", cover assets the study
  has no place for: aircraft, real estate, transport infrastructure, government
  and public safety, electronics and semiconductor, hospitality, and general
  plant support. Extension classifications inside ASA sectors are `basis: extension`.
- The asset classes and their placement under ASA headings are this project's
  own judgment and have not been reviewed by an appraiser.
- ASA normal useful lives are attached by `attach_lives.py`, but only in
  `local/class_lives.csv`. The study's life figures and asset lists are
  copyright ASA and this repository is public, so they are not committed.
  To recreate them: `python parse_asa_nul.py <your ASA PDF>` then
  `python attach_lives.py`.
- The match from class to life band is a word-overlap guess and needs review.

## Classification sources

| Source | Use | Status |
|---|---|---|
| ASA Estimated Normal Useful Life Study 2024 | Sector and classification headings; normal useful lives | Headings used; lives attached locally, not committed |
| US state personal property manuals (NC, CO, NV, NM, UT, KS, AR) | Economic lives by industry, percent-good and cost index tables | Identified, not yet loaded |
| Louisiana Tax Commission rules (Title 61 Part V) | Oil and gas wells, drilling rigs, pipelines: cost and life tables | Identified, not yet loaded |
| Kansas Oil and Gas Appraisal Guide | Lease and well equipment schedules | Identified, not yet loaded |
| FERC Uniform System of Accounts (18 CFR 101, 201, 352) | Plant account lists for electric, gas and oil pipeline utilities | Identified, not yet loaded |
| New Zealand IRD general depreciation rates (IR265) | Useful lives by industry and asset category | Identified, not yet loaded |
| IRS Publication 946, Tables B-1 and B-2 | Tax class lives, reference only | Downloaded, not yet parsed |
| ATO effective life tables | Tax effective lives, reference only | Site refused download |

## Row format

`state` is the register row as text; the other columns are the answers.

```
state:          description: (3) TOSHIBA INJECTION MOLDING MACH | gl_account: Production Equipment | cost: 917,477 | acquired: 1997-05
in_scope:       yes | no | unclear
sector:         Manufacturing - Plastics, Rubber & Packaging
major_category: Plastics & Rubber Processing
asset_class:    Injection Molding Machines
```

Rows that are not classifiable tangible assets (software, intangibles,
construction in progress, expensed items) are `in_scope = no`. Land, buildings
and infrastructure are classes in the taxonomy. Rows too vague
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
- The only real accounting register so far is one US state government register
  (Indiana "Assets Data", licence not specified on the portal). It is heavy on
  office, IT, vehicle and public safety assets and has almost no industrial plant.
- The sector inventory rows use real makes, models, sizes and plant names, but
  the description wording is assembled by `fetch_sector_inventories.py`, so it
  is cleaner and more regular than a real register.
- Oil and gas real rows cover offshore platforms and refinery units only;
  mining real rows are mine sites, not mining equipment.
- Indiana real estate rows are labelled by the state's own ledger category,
  which is sometimes mis-posted.
- Agriculture, airports, toll roads, transmission and distribution, and all
  manufacturing sectors have synthetic rows only (plus a handful from Indiana).
- Real rows in `training_set.csv` carry Jev's labels, unchecked by a person.
- `real_test_to_review.csv` is not a test set until its rows are reviewed.
