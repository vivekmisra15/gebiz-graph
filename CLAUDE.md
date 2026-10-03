# CLAUDE.md: GeBIZ Knowledge Graph (Phase 1 capstone)

## What this is

A single-file Python learning project that turns Singapore government procurement awards (GeBIZ open data) into a Neo4j knowledge graph with a small governed semantic layer. It is the Phase 1 capstone of a private, phased self-study on knowledge graphs and the enterprise semantic layer. The design reference is `SCHEMA.md`. Read it before changing anything.

The owner is not a professional developer. Prefer plain, readable code with comments over clever code. Explain non-obvious choices briefly.

## The thesis the build must demonstrate

In an audited environment, a model should never write its own queries or invent definitions. Humans author governed definitions (a taxonomy and metric definitions). The model only **selects among them**, and every selection is recorded with its probability so it can be audited. Where the model is not confident, the system **abstains** instead of guessing.

Concretely:
1. The category taxonomy is authored by a human and versioned. The model classifies into it and cannot add categories.
2. Metrics are defined once as `Metric` nodes with fixed parameterized Cypher templates. Slices are dimensions, never new metrics.
3. Every classification writes a `CLASSIFIED_AS` edge with probability, model name, taxonomy version and timestamp.
4. Below the confidence threshold, a tender is reported as UNCLASSIFIED. It is not forced into a category.

## Jev

Jev is a classification model from TypeSafe AI (released in limited early access on 15 September 2026). It does not generate text. It returns typed answers with probabilities: Choice (pick from a closed list), Score, and a boolean type called Noul. Reported facts: a Choice has a limit of 255 options, output tokens are free, and input is billed per token.

Use Jev for exactly one job here: classify each tender description into one of the taxonomy categories (a closed-set Choice).

- Put the Jev call behind one function, `classify_tender(description) -> (category_code, probability)`.
- Provide a simple rule-based fallback behind the same function (keyword rules), so the script runs without an API key and can be compared against Jev.
- **Confirm the SDK call shape from TypeSafe's documentation before writing the call. Do not guess parameter names or response fields.** If the docs cannot be reached, stop and ask.
- Send readable text only, keep payloads small, and include the category labels with short descriptions in the request.

## Hard constraints

1. **Single file.** All build code lives in one standalone Python script (`gebiz_graph.py`). Standard library, `pandas`, the Neo4j Python driver, and the Jev SDK only. No frameworks, no extra modules.
2. **Public data only.** The project reads the public GeBIZ dataset from data.gov.sg and nothing else. No other datasets or data sources.
3. **No ML math.** No loss functions, embeddings training, or model internals. This project is about the data and semantic layer, not model theory.
4. **Parameterized Cypher only.** Never build Cypher by string concatenation. Parameterization is the precondition for access control later.
5. **Bandwidth.** The build budget is 9 hours. Prefer the smallest thing that demonstrates the thesis. Flag scope creep (extra datasets, UI, evaluation harnesses) instead of building it.

## Data facts (from profiling)

- `gebiz.csv`: 18,464 rows, 12,052 tenders. Columns: `tender_no`, `tender_description`, `agency`, `award_date` (**DD/MM/YYYY**), `tender_detail_status`, `supplier_name`, `awarded_amt`.
- FY2021 to FY2025 only, Singapore fiscal year (April to March), labelled by starting year.
- Status "Awarded to No Suppliers" (639 rows): amount is 0 and `supplier_name` is the literal `Unknown`. Create the Tender, but **no Supplier node and no edge.**
- Status, description, agency and award date are consistent within a `tender_no`, so they live on the Tender node.
- No repeated `(tender_no, supplier_name)` pair. One `AWARDED_TO` edge per pair. If name normalization merges two names in a tender, sum the amounts.
- Median amount S$178K, max S$1.8B. Never report averages. "Awarded value" is contract value at award date, not cash spent.

## Build order

1. Loader: read CSV, apply loader rules (`SCHEMA.md` section 7), create constraints, load nodes and edges. Print counts and check them against the data facts above (12,052 tenders, 17,825 edges before merging).
2. Metric layer: create `Metric` nodes and the parameterized templates. Verify M1 totals by fiscal year against a plain pandas calculation. The two must match.
3. Classification: run `classify_tender` over all tenders, write `CLASSIFIED_AS` edges. Run the rule-based fallback on the same tenders for comparison.
4. Calibration: compare Jev against about 30 clean hand-labels (taken from the labelled 150-tender sample), set the threshold (start at 0.7), and stop tuning there. This comes before the router because M3 and M4 answers depend on the threshold.
5. Router (required, minimal): given a natural-language question, choose one template from the closed set and fill its parameters (agency, fiscal year, category, threshold). It may only pick a listed template. It must abstain and ask when confidence is low or a required parameter is missing (for example a question with no fiscal year, or "how much was spent on IT" with no defined metric). No UI and no free-form query generation. Scope the demo to about 10 fixed questions, of which 2 or 3 are deliberately ambiguous and should trigger abstention. This is a demo set, not an evaluation benchmark. Do not expand it.
6. Audit log: for every router call, print or append one line with the question, chosen template, probability distribution, parameters, result, and whether it abstained. The same log covers the classification step.

Do not start a step until the previous step's checks pass.

## Deliverables

The graph is the substrate, not the end goal. The project produces:
1. A governed query layer: answers come only through the M1 to M4 templates, each shown with its definition, the threshold used, and the UNCLASSIFIED share.
2. An audit trail of every classification and every router decision.
3. One finding: M4 classification coverage, reported by count and by value, and the gap between them.
4. The Phase 1 private thesis note, built from the above.

Out of scope: visualisation or dashboards, graph algorithms (centrality, community detection), supplier entity resolution beyond deterministic name cleanup.

## Working style

- Measured and analytical. No cheerleading or filler. State results, then caveats.
- When a result surprises you, say so and verify it before building on it.
- Before adding a dependency, a file, or a feature, ask whether the thesis needs it.
- Show numbers with units (S$) and say whether they are by count or by value.

## Open items

- Taxonomy is DRAFT v0 until the 150-tender sample is labelled. Do not hard-code categories as final. Load them from one table at the top of the script.
- Confirm whether "Unknown" appears as a supplier on rows that are not "No Suppliers".
- Jev SDK call shape: confirm from documentation.
