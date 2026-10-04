# GeBIZ Knowledge Graph: Schema v0.3

Status: taxonomy frozen as v1.0 after hand-labelling `sample_150_tenders_classified_reviewed.csv`. Everything else unchanged from v0.2.

## 1. Source data

- Dataset: "Government Procurement via GeBIZ", Ministry of Finance, data.gov.sg (dataset id `d_acde1106003906a75c3fa052592f2fcb`). Open Data Licence.
- File: `gebiz.csv`. 18,464 rows, 12,052 distinct `tender_no`.
- Columns: `tender_no`, `tender_description`, `agency`, `award_date`, `tender_detail_status`, `supplier_name`, `awarded_amt`.
- `award_date` is **DD/MM/YYYY**. Always parse with an explicit format.
- Coverage: 1 Apr 2021 to 31 Mar 2026 (FY2021 to FY2025). Singapore fiscal year runs April to March and is labelled by its starting calendar year (a 15 Jun 2024 award is FY2024; a 15 Feb 2025 award is also FY2024).
- This is awards only. Open or unawarded tenders are not in it.

## 2. Profiling findings (these drive the rules below)

| Finding | Value |
|---|---|
| Statuses | Awarded to Suppliers 9,294; Awarded by Items 7,845; Award by interface record 686; Awarded to No Suppliers 639 |
| Zero amounts | 643 rows: all 639 "No Suppliers" rows, plus 4 zero-priced line items under "Awarded by Items" |
| "No Suppliers" rows | `supplier_name` is the literal string `Unknown` on all 639. Amount is 0 on all 639. |
| Multi-row tenders | 1,669 of 12,052 tenders have more than one row (median 3, max 135) |
| Tender-level consistency | Status, description, agency and award_date never vary within a `tender_no` |
| Duplicates | No duplicate rows and no repeated `(tender_no, supplier_name)` pair |
| Amount profile | Median S$178K, max S$1.8B, total S$123.8B. The top 10 rows hold 9.1% of the total. Averages are unusable. |
| Nulls | No null amounts, no unparseable dates, no blank supplier names |

## 3. Nodes

| Node | Properties | Notes |
|---|---|---|
| `Agency` | `name` | 113 in the source. This is a procuring unit as published, not a ministry roll-up (e.g. "Ministry of Health-Ministry Headquarter"). v1 does no roll-up. |
| `Tender` | `tender_no`, `description`, `award_date`, `fiscal_year`, `source_status`, `awarded` | `awarded` is false only when status is "Awarded to No Suppliers". `source_status` keeps the original string, including "Award by interface record", whose provenance is undocumented. |
| `Supplier` | `normalized_name`, `raw_names` (list) | Never create a Supplier from `Unknown`. |
| `Category` | `code`, `label`, `taxonomy_version` | Governed taxonomy, section 5. |
| `Metric` | `id`, `name`, `definition`, `version`, `dimensions` (list), `cypher_template_id` | The semantic layer stored as nodes. |

## 4. Relationships

| Relationship | Properties | Notes |
|---|---|---|
| `(Agency)-[:ISSUED]->(Tender)` | none | One agency per tender. |
| `(Tender)-[:AWARDED_TO]->(Supplier)` | `amount_sgd` | One edge per tender-supplier pair, created for every row except "No Suppliers" (17,825 edges before name merging). If name normalization merges two raw names inside one tender, sum their amounts onto one edge. |
| `(Tender)-[:CLASSIFIED_AS]->(Category)` | `probability`, `confidence`, `model`, `taxonomy_version`, `classified_at` | Written for every tender, pointing at the model's top choice. `probability` is that choice's probability; `confidence` is Jev's separate overall-trust number (null for the keyword fallback). This edge is the audit record. |
| `(Metric)-[:SUPPORTS_DIMENSION]->(Dimension)` | none | Optional. A `dimensions` list property on Metric is sufficient for v1. |

## 5. Category taxonomy: v1.0

Frozen after labelling 150 tenders (`sample_150_tenders_classified_reviewed.csv`). Codes C01 to C10 are unchanged from v0; wording and boundary rules were tightened from the labelling patterns. The script loads this table from one place (`TAXONOMY` at the top of `gebiz_graph.py`). Keep the two in step.

| Code | Label | Short description (sent to the model) |
|---|---|---|
| C01 | IT & Digital Services | Software, systems, networks, cybersecurity, data, IT maintenance and support |
| C02 | Construction & Civil Works | Building, civil, M&E and fit-out works; design-and-build; renovation, upgrading, demolition |
| C03 | Facilities Management | Cleaning, security, landscaping, arboriculture, and routine maintenance, servicing or operation of existing facilities and systems |
| C04 | Professional & Consultancy Services | Advisory, design, engineering, accounting, inspection and surveying consultancy |
| C05 | Research & Studies | Research and scientific or environmental studies and surveys whose output is data or findings |
| C06 | Events, Communications & Training | Events, publicity, design and printing, media, training, assessment programmes |
| C07 | Equipment & Goods Supply | Supply (with delivery, installation, commissioning) of equipment, instruments, materials and consumables |
| C08 | Medical & Healthcare Supplies | Medical, clinical, laboratory-testing and health-product supplies |
| C09 | Transport & Logistics | Transport, delivery, warehousing, cold chain, relocation |
| C10 | Other Services | Confidently none of C01 to C09 (insurance, contact centre, lifeguards, calibration) |

**UNCLASSIFIED is not a category node.** It is a query-time bucket: any tender whose `CLASSIFIED_AS.probability` is below the threshold. This lets the threshold change after calibration without reloading the graph.

**"Other Services" and UNCLASSIFIED mean different things.** Other Services: the model is confident the tender fits none of C01 to C09. UNCLASSIFIED: the model is not confident about its top choice. Never merge them.

### Boundary rules (derived from the hand labels)

1. **Design and Construction / Design and Build** goes to C02, including paths, sewers and stations.
2. **Supply plus installation of equipment** goes to C07 (cranes, kitchen equipment, lab instruments, bicycle racks). Exception: works that alter the building fabric (a lift installed in a building under works, HVAC upgrading, renovation) go to C02.
3. **Maintenance follows the asset.** IT systems and network maintenance go to C01. Building, plant, lifts, air-conditioning, roads and fire detection go to C03. Maintenance bundled with A&A or building works goes to C02.
4. **Supply with embedded IT** (supply and commissioning of an IT, cybersecurity or digital-twin system) goes to C01.
5. **Consultancy vs study.** If the deliverable is advice or design, C04. If it is a survey or study that produces findings (environmental baseline, hydrographic survey), C05.
6. **Design and printing for publications and reports** goes to C06, not C04.
7. **C10 only when the tender is clear but fits no other category.** An uninformative description (e.g. "Please refer to the attached tender documents") is not C10. It should fall below the threshold and be reported UNCLASSIFIED.

### Sample label review (resolved by owner, 2026-10-04)

- CDVHQ0ETT21000045 (EIPIC centre at Fernvale Woods): relabelled C10 to C06.
- DEF000ETT20300060 ("Please refer to the attached tender documents"): relabelled C10 to UNCLASSIFIED (rule 7). Not a category; the sample now has one row whose correct answer is abstention. Exclude it from the clean calibration labels, or use it to check that the model abstains.
- HPB000ETT21000028 (panel of premium suppliers to HPB): relabelled C07 to C08. Note C08 is now 4 of 150.
- Relocation of storage and servers (MAS): confirmed C09.
- C08 is thin and holds laboratory kits and sports food. Revisit if calibration shows it is unusable.

## 6. Governed metrics

| ID | Name | Definition | Dimensions |
|---|---|---|---|
| M1 | Awarded value | Sum of `amount_sgd` where `amount_sgd > 0` on tenders with `awarded = true`, attributed to the fiscal year of `award_date`. This is **contract value at award date, not cash spent**. Multi-year contracts land entirely in the award year. Some values look like ceilings or estimates (e.g. a round S$1,000,000,000 cleaning tender; a 135-supplier framework tender). The data does not say which. | agency, fiscal_year, category, supplier |
| M2 | Supplier concentration | Share of M1 held by the top N suppliers within a slice. Uses normalized names. No entity resolution in v1. | agency, fiscal_year, category |
| M3 | Category spend | M1 grouped by category, counting only tenders with `probability >= threshold`. Always reported alongside the UNCLASSIFIED remainder. | agency, fiscal_year |
| M4 | Classification coverage | Share of M1 held by tenders with `probability >= threshold`. Report **both by value and by count**. By value it is dominated by a few hundred very large contracts, so the two figures will differ. The gap is itself a finding. | agency, fiscal_year |

Rules of the semantic layer:
- A metric is defined once. Slices are dimensions, never new metrics. "Spend by agency" is M1 with the agency dimension.
- "Spend" is not a defined term here. Use "awarded value".

## 7. Loader rules

1. Read the CSV with explicit dtypes. Parse `award_date` with `format="%d/%m/%Y"`.
2. Compute `fiscal_year = year if month >= 4 else year - 1`.
3. One Tender per `tender_no`. Take attributes from the first row (they are consistent within a tender).
4. `awarded = (status != "Awarded to No Suppliers")`.
5. For "No Suppliers" tenders: create the Tender, create no Supplier and no `AWARDED_TO` edge.
6. Normalize supplier names deterministically: uppercase, collapse whitespace, strip punctuation, strip common suffixes ("PTE LTD", "PRIVATE LIMITED", "LTD", etc.). Keep every raw variant in `raw_names`.
7. If two raw names in one tender normalize to the same supplier, sum `amount_sgd` on a single edge.
8. Keep the 4 zero-priced line items as edges with `amount_sgd = 0`. M1 filters them out.
9. All queries use parameters (`$agency`, `$fy`, `$threshold`). No string-built Cypher. Parameterization is the precondition for access control in a later phase.

## 8. Constraints (Neo4j)

```cypher
CREATE CONSTRAINT tender_no IF NOT EXISTS FOR (t:Tender) REQUIRE t.tender_no IS UNIQUE;
CREATE CONSTRAINT supplier_norm IF NOT EXISTS FOR (s:Supplier) REQUIRE s.normalized_name IS UNIQUE;
CREATE CONSTRAINT agency_name IF NOT EXISTS FOR (a:Agency) REQUIRE a.name IS UNIQUE;
CREATE CONSTRAINT category_code IF NOT EXISTS FOR (c:Category) REQUIRE c.code IS UNIQUE;
CREATE CONSTRAINT metric_id IF NOT EXISTS FOR (m:Metric) REQUIRE m.id IS UNIQUE;
```

## 9. Query templates (parameterized)

Each Metric node points at one template id. The router may only choose among these.

**M1 by agency and fiscal year**

```cypher
MATCH (a:Agency {name: $agency})-[:ISSUED]->(t:Tender {awarded: true, fiscal_year: $fy})
      -[r:AWARDED_TO]->(:Supplier)
WHERE r.amount_sgd > 0
RETURN sum(r.amount_sgd) AS awarded_value_sgd
```

**M3 category spend for a fiscal year**

```cypher
MATCH (t:Tender {awarded: true, fiscal_year: $fy})-[c:CLASSIFIED_AS]->(cat:Category),
      (t)-[r:AWARDED_TO]->(:Supplier)
WHERE r.amount_sgd > 0 AND c.probability >= $threshold
RETURN cat.code AS category, sum(r.amount_sgd) AS awarded_value_sgd
ORDER BY awarded_value_sgd DESC
```

**M4 coverage by value for a fiscal year**

```cypher
MATCH (t:Tender {awarded: true, fiscal_year: $fy})-[c:CLASSIFIED_AS]->(:Category),
      (t)-[r:AWARDED_TO]->(:Supplier)
WHERE r.amount_sgd > 0
RETURN sum(CASE WHEN c.probability >= $threshold THEN r.amount_sgd ELSE 0 END) AS classified_sgd,
       sum(r.amount_sgd) AS total_sgd
```

Remaining templates (M2, and slices by supplier and category) are written during the build.

## 10. Open items

| Item | Status |
|---|---|
| Taxonomy | Done: frozen as v1.0 (section 5). Four doubtful sample labels await owner confirmation. |
| "Unknown" supplier on non-"No Suppliers" rows | Closed: checked, 0 rows. All 639 "Unknown" rows are "No Suppliers" and vice versa. The loader re-checks this on every run. |
| "Award by interface record" (686 rows) | Provenance undocumented. Counted in M1, `source_status` retained. |
| Threshold | Start at 0.7. Calibrate once on about 30 clean hand-labels. No further tuning. |
| Jev SDK call shape | Read from the docs (docs.typesafe.ai): `TypeSafeClient().system_one(state=..., questions={name: Choice(instructions=..., criteria={option: description})})`; answer has `choice`, `probabilities`, `confidence`. Not yet confirmed by a live call; smoke test at the start of step 3. |
| Probability vs confidence | Decided by owner 2026-10-04: store both on `CLASSIFIED_AS` (`probability` = `probabilities[choice]`, `confidence` = Jev's value). Which one the threshold tests is decided in step 4 calibration, on the hand-labels. Until then queries use `probability` (M3/M4 templates unchanged). |

## 11. Change log

- v0.1: initial draft (GeBIZ, 10 categories + reserved UNCLASSIFIED node).
- v0.2: profiling results folded in. M1 renamed "Awarded value". `AWARDED_TO` skipped for "No Suppliers". UNCLASSIFIED made a query-time bucket. `source_status` retained. Coverage reported by count and value.
- v0.3: taxonomy frozen as v1.0 with descriptions and seven boundary rules; "Unknown" supplier check closed (0 rows); Jev call shape recorded from docs; probability vs confidence noted.
