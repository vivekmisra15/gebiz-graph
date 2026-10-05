# GeBIZ Knowledge Graph

A small learning project that turns Singapore government procurement awards (GeBIZ open data) into a Neo4j knowledge graph with a governed semantic layer. It is the Phase 1 capstone of a private, self-directed study of knowledge graphs and the enterprise semantic layer.

## The idea

In an audited setting, a model should not write its own queries or invent its own definitions. Here:

1. **Humans author the definitions.** The category taxonomy and the metric definitions are written by a person and versioned.
2. **The model only selects.** It picks a category from a closed list, and (later) picks a query template from a closed set. It cannot add categories or write Cypher.
3. **Every selection is recorded** with its probability, model name, taxonomy version and timestamp.
4. **Below the confidence threshold, the system abstains** and reports the tender as UNCLASSIFIED instead of guessing.

## Status

| Step | What | State |
|---|---|---|
| 1 | Loader: CSV to Neo4j, with checks | Done |
| 2 | Metric layer: Metric nodes M1 to M4 and fixed Cypher templates | Done. M1 to M4 all verified against pandas (M3 and M4 after step 3) |
| 3 | Classification of each tender into the taxonomy (Jev, plus a keyword fallback) | Done. 12,052 tenders classified, 0 failures; findings in RESULTS.md |
| 4 | Calibration: set the confidence threshold on about 30 hand labels | Done. Threshold 0.7 on probability; see RESULTS.md |
| 5 | Router: a natural-language question picks one template, or abstains | Done with caveats. 12 demo questions: 9 answered, 3 abstained. Two known limits (spend questions, ambiguity); see RESULTS.md |
| 6 | Audit log of every classification and router decision | Done. `classification_log.jsonl` and `router_log.jsonl` (one line per router call) |

Verified so far: the graph holds 12,052 tenders, 113 agencies and 6,134 suppliers. Awarded value by fiscal year from Cypher matches an independent pandas calculation to the dollar for FY2021 to FY2025.

## Data

Public data only: "Government Procurement via GeBIZ", Ministry of Finance, [data.gov.sg](https://data.gov.sg) (dataset id `d_acde1106003906a75c3fa052592f2fcb`), under the Open Data Licence. `gebiz.csv` is a copy, 18,464 rows covering 12,052 tenders from April 2021 to March 2026.

Things to know before reading any number from it:

- It is **awards only**. Open or unawarded tenders are not in it.
- "Awarded value" is **contract value at the award date, not cash spent**. Multi-year contracts land entirely in the award year, and some values look like ceilings or estimates.
- Amounts are very skewed (median S$178K, maximum S$1.8B). Averages are meaningless, so none are reported.
- Fiscal years run April to March and are labelled by the starting calendar year.
- The 639 rows with status "Awarded to No Suppliers" create a Tender but no Supplier and no award edge.

## Files

| File | Purpose |
|---|---|
| `gebiz_graph.py` | The whole build in one script: loader, checks, metric layer, classification |
| `PLAN.md` | Plain-language plan and a dated decision log (progress is tracked here in the Status table, not there) |
| `RESULTS.md` | Findings from each run, kept for reference |
| `SCHEMA.md` | Design reference: nodes, relationships, taxonomy v1.0, metrics, loader rules, query templates |
| `CLAUDE.md` | Project brief and constraints for the AI coding assistant used on this project |
| `gebiz.csv` | The source dataset |
| `sample_150_tenders_classified_reviewed.csv` | 150 hand-labelled tenders used to set the taxonomy (`sample_150_tenders.csv` is the unlabelled original) |
| `helpers/profile_gebiz_v2.py` | One-off profiling script that produced the facts in SCHEMA.md section 2 and the 150-tender sample |
| `helpers/smoke_test_jev.py` | First live check of the Jev call on 5 tenders |
| `helpers/analyse_classification_log.py` | Reproduces the step 3 figures in RESULTS.md from the audit log |
| `calibration_labels.csv` | The 30 owner-approved hand labels used to calibrate the threshold |
| `helpers/calibrate.py` | Compares Jev with those labels and shows what each threshold would do |
| `classification_log.jsonl` | Audit log of every classification (git-ignored, regenerable) |
| `router_log.jsonl` | Audit log of every router call (git-ignored) |

## Run it

Needs Python 3.10 or newer and a Neo4j 5.x database.

```
python3 -m venv .venv
source .venv/bin/activate
pip install pandas==2.2.3 neo4j==6.3.1
```

Start Neo4j (Docker example) and give the script its connection settings through environment variables. Credentials never go in the code.

```
docker run -d --name gebiz-neo4j -p 7474:7474 -p 7687:7687 \
    -e NEO4J_AUTH="neo4j/<your-password>" neo4j:5

export NEO4J_URI=neo4j://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=<your-password>
```

Then:

```
python gebiz_graph.py --prepare-only   # pandas checks only, no Neo4j needed
python gebiz_graph.py                  # load, check, create metrics, verify
python gebiz_graph.py --reset          # delete graph data first, then reload
```

The script prints PASS or FAIL for each check and exits with an error if any fail. It is safe to re-run: writes use `MERGE` on unique keys. `--reset` deletes all Tender, Supplier, Agency and Category nodes, which in later steps includes the classification edges.

## Design rules

- **One build script.** Standard library, pandas, the Neo4j driver and (from step 3) the Jev SDK only. One-off helper scripts live in `helpers/` and are not part of the build.
- **Parameterized Cypher only.** No query is built by string concatenation.
- **Metrics are defined once.** A slice is a dimension, not a new metric. "Spend" is not a defined term; the metric is "awarded value".
- **UNCLASSIFIED is a query-time bucket**, not a category. It means the model was not confident. It is different from "Other Services", where the model is confident that nothing else fits.

## Known limits

- Supplier names are cleaned deterministically (case, punctuation, company suffixes) and nothing more. There is no entity resolution. Foreign suffixes such as `SDN BHD` are kept, so a Singapore `PTE LTD` and a Malaysian `SDN BHD` with the same trading name stay as separate suppliers.
- Agencies are procuring units as published, with no roll-up to ministries.
- "Award by interface record" (686 rows) has undocumented provenance. It is counted and its status string is kept.

## About the model

Jev is a classification model from TypeSafe AI, in limited early access since 15 September 2026. It returns typed answers with probabilities rather than text. It is used here for one job only: choosing a tender's category from the closed taxonomy. See [docs.typesafe.ai](https://docs.typesafe.ai).
