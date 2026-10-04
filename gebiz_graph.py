"""
gebiz_graph.py: GeBIZ knowledge graph, build steps 1 to 3 (loader, metric layer, classification).

Design reference: SCHEMA.md (v0.3). Project rules: CLAUDE.md.
Steps 4 onward (calibration, router, full audit log) are NOT here yet.

WHAT IT DOES
  1. Reads gebiz.csv and applies the loader rules (SCHEMA.md section 7).
  2. Loads Agency, Tender, Supplier and Category nodes plus ISSUED and
     AWARDED_TO edges into Neo4j. Safe to re-run (see RE-RUNNING).
  3. Prints PASS/FAIL checks against the profiling facts.
  4. Creates the Metric nodes (M1 to M4) and the fixed Cypher templates,
     then checks M1 by fiscal year against a plain pandas calculation.

INSTALL (inside a virtual environment, so system Python is untouched)
    python3 -m venv .venv
    source .venv/bin/activate
    pip install pandas==2.2.3 neo4j==6.3.1
  Step 3 also needs:  pip install typesafe-sdk==0.7.2   and   export TYPESAFE_API_KEY=<key>

NEO4J (needs version 5.x or later)
  Docker example:
    docker run -d --name gebiz-neo4j -p 7474:7474 -p 7687:7687 \
        -e NEO4J_AUTH=neo4j/<choose-a-password> neo4j:5
  Credentials come from environment variables only. Never put them in this file:
    export NEO4J_URI=neo4j://localhost:7687
    export NEO4J_USER=neo4j
    export NEO4J_PASSWORD=<the password>
    export NEO4J_DATABASE=neo4j        # optional

RUN
    python gebiz_graph.py --prepare-only   # pandas checks only, no Neo4j needed
    python gebiz_graph.py                  # full load + checks + metric layer
    python gebiz_graph.py --reset          # wipe graph data first, then reload
    python gebiz_graph.py --trial 20       # step 3 dry run on 20 hand-labelled tenders, no Neo4j writes
    python gebiz_graph.py --classify       # step 3 full run: Jev on every tender, writes CLASSIFIED_AS
  Without TYPESAFE_API_KEY, --trial uses the keyword rules instead of Jev.
  Every classification appends a line to classification_log.jsonl (git-ignored).

RE-RUNNING
  Every write uses MERGE on a unique key and SET (not +=), so running twice
  gives identical counts and totals. --reset deletes all Tender, Supplier,
  Agency and Category nodes (and so any CLASSIFIED_AS edges, from step 3 on).
  It does not delete Metric nodes. Use it on purpose, not by habit.
"""

import os
import re
import sys

import pandas as pd

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gebiz.csv")
NO_SUPPLIERS = "Awarded to No Suppliers"   # status with supplier_name == "Unknown"
BATCH_SIZE = 1000                           # rows per UNWIND batch

# The category taxonomy lives HERE and nowhere else. Human-authored, versioned.
# The model may only choose from this table. Keep in step with SCHEMA.md section 5.
TAXONOMY_VERSION = "v1.0"
TAXONOMY = [
    # (code, label, short description)
    ("C01", "IT & Digital Services",
     "Software, systems, networks, cybersecurity, data, IT maintenance and support"),
    ("C02", "Construction & Civil Works",
     "Building, civil, M&E and fit-out works; design-and-build; renovation, upgrading, demolition"),
    ("C03", "Facilities Management",
     "Cleaning, security, landscaping, arboriculture, and routine maintenance, servicing or operation of existing facilities and systems"),
    ("C04", "Professional & Consultancy Services",
     "Advisory, design, engineering, accounting, inspection and surveying consultancy"),
    ("C05", "Research & Studies",
     "Research and scientific or environmental studies and surveys whose output is data or findings"),
    ("C06", "Events, Communications & Training",
     "Events, publicity, design and printing, media, training, assessment programmes"),
    ("C07", "Equipment & Goods Supply",
     "Supply (with delivery, installation, commissioning) of equipment, instruments, materials and consumables"),
    ("C08", "Medical & Healthcare Supplies",
     "Medical, clinical, laboratory-testing and health-product supplies"),
    ("C09", "Transport & Logistics",
     "Transport, delivery, warehousing, cold chain, relocation"),
    ("C10", "Other Services",
     "Confidently none of C01 to C09 (insurance, contact centre, lifeguards, calibration)"),
]

# Expected facts from profiling (CLAUDE.md "Data facts").
EXPECTED_TENDERS = 12052
EXPECTED_EDGE_ROWS = 17825
EXPECTED_NOT_AWARDED = 639
EXPECTED_AGENCIES = 113
EXPECTED_ZERO_EDGES = 4
FISCAL_YEARS = [2021, 2022, 2023, 2024, 2025]


def money(x):
    return f"S${x:,.0f}"


# ---------------------------------------------------------------------------
# STEP 3: classification (Jev, plus a keyword-rule fallback)
# ---------------------------------------------------------------------------

JEV_MODEL = "jev-1.13.0"
RULES_MODEL = "keyword-rules-v1"
JEV_WORKERS = 8                                   # parallel Jev calls
THRESHOLD = 0.7                                   # set in step 4 calibration (PLAN.md): UNCLASSIFIED = probability below this
SAMPLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "sample_150_tenders_classified_reviewed.csv")
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "classification_log.jsonl")

# Jev sees option names and descriptions, not codes, so the label is the option name.
JEV_QUESTION_TEXT = "Pick the one category that best describes this Singapore government tender."
LABEL_TO_CODE = {label: code for code, label, _desc in TAXONOMY}
CODE_TO_LABEL = {code: label for code, label, _desc in TAXONOMY}

# Fallback rules: plain keyword counts. Lower-case substrings; the category with
# the most hits wins, ties go to the category listed first. No hit = no answer.
# This is a crude baseline to compare Jev against, not a classifier to trust.
KEYWORD_RULES = [
    ("C01", ["software", "system", "digital", "cyber", "network", "database", "cloud", "portal",
             "website", "application", " ict ", "server", "licence", "license", "wifi", "wi-fi"]),
    ("C02", ["construction", "civil", "design and build", "design-and-build", "renovation",
             "upgrading", "demolition", "addition and alteration", "a&a", "fit-out", "fitout",
             "proposed ", "erection", "sewer", "drain", "road"]),
    ("C03", ["cleaning", "security services", "landscap", "horticultur", "tree", "maintenance",
             "servicing", "facilities management", "pest control", "air-con", "operation and maintenance"]),
    ("C04", ["consultancy", "consultant", "advisory", "professional services", "engineering services",
             "architect", "audit", "inspection", "valuation"]),
    ("C05", ["research", "study", "studies", "survey", "baseline", "hydrographic"]),
    ("C06", ["event", "publicity", "printing", "media", "training", "course", "workshop",
             "exhibition", "video", "photograph", "advertis", "campaign", "communications"]),
    ("C07", ["supply", "purchase", "equipment", "instrument", "machine", "consumable",
             "furniture", "uniform", "vehicle"]),
    ("C08", ["medical", "clinical", "laborator", "reagent", "test kit", "pharmaceutical",
             "vaccine", "surgical", "health product"]),
    ("C09", ["transport", "delivery", "logistics", "warehous", "cold chain", "relocation",
             "shuttle", "freight", "courier", "bus "]),
    ("C10", ["insurance", "contact centre", "lifeguard", "calibration"]),
]


def classify_with_rules(description):
    """Keyword fallback. Returns (code or None, hit count). It has no probability."""
    text = " " + description.lower() + " "
    best_code, best_hits = None, 0
    for code, words in KEYWORD_RULES:
        hits = sum(1 for w in words if w in text)
        if hits > best_hits:
            best_code, best_hits = code, hits
    return best_code, best_hits


_jev_client = None


def jev_client():
    """One shared client, created on first use. Reads TYPESAFE_API_KEY from the environment."""
    global _jev_client
    if _jev_client is None:
        from typesafe_sdk import TypeSafeClient     # imported here so other steps need no SDK
        _jev_client = TypeSafeClient()
    return _jev_client


def classify_with_jev(description):
    """One Jev call: a closed-set Choice over the taxonomy. Returns a dict."""
    from typesafe_sdk import Choice
    question = Choice(
        instructions=JEV_QUESTION_TEXT,
        criteria={label: desc for _code, label, desc in TAXONOMY},
    )
    resp = jev_client().system_one(state=description, questions={"category": question},
                                   model=JEV_MODEL)
    ans = resp.answers["category"]
    if ans.choice not in LABEL_TO_CODE:
        raise ValueError(f"Jev returned a choice outside the taxonomy: {ans.choice!r}")
    probs = {LABEL_TO_CODE[label]: p for label, p in ans.probabilities.items() if label in LABEL_TO_CODE}
    return {"code": LABEL_TO_CODE[ans.choice], "probability": probs[LABEL_TO_CODE[ans.choice]],
            "confidence": ans.confidence, "probabilities": probs, "model": JEV_MODEL,
            "input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}


def classify_detail(description):
    """Classify with Jev if TYPESAFE_API_KEY is set, otherwise with the keyword rules.
    Returns a dict with code, probability, confidence, probabilities and model.
    The keyword fallback has no probability or confidence, so those are None."""
    if os.environ.get("TYPESAFE_API_KEY"):
        return classify_with_jev(description)
    code, _hits = classify_with_rules(description)
    return {"code": code, "probability": None, "confidence": None, "probabilities": None,
            "model": RULES_MODEL, "input_tokens": 0, "output_tokens": 0}


def classify_tender(description):
    """The one function behind which the model sits (CLAUDE.md): description in,
    (category_code, probability) out. Probability is None when the keyword fallback was used."""
    result = classify_detail(description)
    return result["code"], result["probability"]


def classify_many(tenders, workers=JEV_WORKERS):
    """Run classify_detail over a DataFrame of tenders, in parallel. Never raises on one bad
    tender: failures are returned separately so a long run is not lost to one error."""
    from concurrent.futures import ThreadPoolExecutor

    def one(row):
        try:
            return row["tender_no"], classify_detail(row["description"]), None
        except Exception as exc:                    # noqa: BLE001 (report and carry on)
            return row["tender_no"], None, f"{type(exc).__name__}: {exc}"

    rows = [r for _, r in tenders.iterrows()]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(one, rows))
    ok = {tn: res for tn, res, err in outcomes if err is None}
    failed = {tn: err for tn, res, err in outcomes if err is not None}
    return ok, failed


def append_audit_log(tenders, ok, mode):
    """Audit trail (step 6 covers the classification step too): one JSON line per tender,
    with the full probability distribution and what the keyword rules said."""
    import json
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    desc = dict(zip(tenders["tender_no"], tenders["description"]))
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        for tn, res in ok.items():
            rule_code, _ = classify_with_rules(desc[tn])
            f.write(json.dumps({"time": now, "mode": mode, "step": "classify", "tender_no": tn,
                                "taxonomy_version": TAXONOMY_VERSION, "model": res["model"],
                                "code": res["code"], "probability": res["probability"],
                                "confidence": res["confidence"], "probabilities": res["probabilities"],
                                "rule_code": rule_code}) + "\n")


def run_trial(df_tenders, n):
    """Dry run: classify N tenders from the hand-labelled sample. Writes nothing to Neo4j."""
    hand = pd.read_csv(SAMPLE_PATH, dtype=str, keep_default_na=False).set_index("tender_no")["my_category"]
    pick = df_tenders[df_tenders["tender_no"].isin(hand.index)].sample(n=n, random_state=0)
    use_jev = bool(os.environ.get("TYPESAFE_API_KEY"))
    print(f"\nTRIAL: {n} tenders from the hand-labelled sample, "
          f"classifier = {JEV_MODEL if use_jev else RULES_MODEL}. Nothing is written to Neo4j.")
    ok, failed = classify_many(pick)
    append_audit_log(pick, ok, mode="trial")
    print(f"{'tender_no':<20}{'hand':<14}{'model':<6}{'prob':>6}{'conf':>6}  {'rules':<6} text")
    right_model = right_rules = labelled = below = 0
    tokens = 0
    for _, row in pick.iterrows():
        tn = row["tender_no"]
        if tn not in ok:
            print(f"{tn:<20}FAILED: {failed[tn]}")
            continue
        res = ok[tn]
        rule_code, _ = classify_with_rules(row["description"])
        prob = "-" if res["probability"] is None else f"{res['probability']:.2f}"
        conf = "-" if res["confidence"] is None else f"{res['confidence']:.2f}"
        print(f"{tn:<20}{hand[tn]:<14}{str(res['code']):<6}{prob:>6}{conf:>6}  {str(rule_code):<6} "
              f"{row['description'][:50]}")
        tokens += res["input_tokens"]
        if hand[tn] in CODE_TO_LABEL:               # skip the UNCLASSIFIED hand-label
            labelled += 1
            right_model += res["code"] == hand[tn]
            right_rules += rule_code == hand[tn]
        if res["probability"] is not None and res["probability"] < THRESHOLD:
            below += 1
    print(f"\nAgainst hand labels ({labelled} labelled tenders, counts only):")
    print(f"  {JEV_MODEL if use_jev else RULES_MODEL}: {right_model} right")
    print(f"  keyword rules: {right_rules} right")
    if use_jev:
        print(f"  below the threshold of {THRESHOLD} (would abstain): {below} of {len(ok)}")
        print(f"  input tokens used: {tokens:,}")
    print(f"  failed calls: {len(failed)}")
    print(f"  audit lines appended to {os.path.basename(LOG_PATH)}")


# SCHEMA.md section 4. Deleting any old edge first means re-running never leaves two
# CLASSIFIED_AS edges on one tender, even if the category changed.
WRITE_CLASSIFICATIONS = """
UNWIND $rows AS row
MATCH (t:Tender {tender_no: row.tender_no})
OPTIONAL MATCH (t)-[old:CLASSIFIED_AS]->()
DELETE old
WITH DISTINCT t, row
MATCH (c:Category {code: row.code})
CREATE (t)-[r:CLASSIFIED_AS]->(c)
SET r.probability = row.probability,
    r.confidence = row.confidence,
    r.model = row.model,
    r.taxonomy_version = row.taxonomy_version,
    r.classified_at = datetime(row.classified_at)
"""
ALREADY_CLASSIFIED = """
MATCH (t:Tender)-[r:CLASSIFIED_AS]->()
WHERE r.model = $model AND r.taxonomy_version = $taxonomy_version
RETURN t.tender_no AS tender_no
"""


def run_classification(driver, df_tenders):
    """Full run: classify every tender not yet done by this model and taxonomy version,
    and write the CLASSIFIED_AS edges. Needs the key (rule-only edges have no probability)."""
    from datetime import datetime, timezone
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("--classify needs TYPESAFE_API_KEY (the keyword fallback has no probability, "
                 "so it is only used in --trial). Nothing was changed.")
    with session_for(driver) as session:
        done = {r["tender_no"] for r in session.run(
            ALREADY_CLASSIFIED, model=JEV_MODEL, taxonomy_version=TAXONOMY_VERSION)}
    todo = df_tenders[~df_tenders["tender_no"].isin(done)]
    print(f"\nCLASSIFY: {len(df_tenders):,} tenders, {len(done):,} already done, {len(todo):,} to do.")
    ok, failed = {}, {}
    chunk = 500                                      # write and log in chunks so a crash loses little
    for i in range(0, len(todo), chunk):
        part = todo.iloc[i:i + chunk]
        part_ok, part_failed = classify_many(part)
        ok.update(part_ok)
        failed.update(part_failed)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = [{"tender_no": tn, "code": r["code"], "probability": r["probability"],
                 "confidence": r["confidence"], "model": r["model"],
                 "taxonomy_version": TAXONOMY_VERSION, "classified_at": now}
                for tn, r in part_ok.items()]
        with session_for(driver) as session:
            run_batches(session, WRITE_CLASSIFICATIONS, rows)
        append_audit_log(part, part_ok, mode="full")
        print(f"  {i + len(part):,} / {len(todo):,} processed, {len(failed)} failed so far")
    tokens = sum(r["input_tokens"] for r in ok.values())
    print(f"Done. Written: {len(ok):,}. Failed: {len(failed)}. Input tokens: {tokens:,} "
          f"(about US${tokens / 1e6 * 0.042:.2f} at US$0.042 per million).")
    for tn, err in list(failed.items())[:10]:
        print(f"  FAILED {tn}: {err}")
    return ok, failed


# ---------------------------------------------------------------------------
# STEP 1a/1b: read the CSV and build clean tables in pandas
# ---------------------------------------------------------------------------

# Suffixes removed from the END of a supplier name, repeatedly, longest first.
# This is deterministic cleanup only. No fuzzy matching, no entity resolution.
# "SDN BHD" and "BHD" are deliberately NOT here: a Malaysian company and a Singapore
# company with the same trading name are different legal entities, so they stay separate.
SUPPLIER_SUFFIXES = [
    "PRIVATE LIMITED", "PTE LIMITED", "PTE LTD", "PTY LTD", "CO LTD",
    "LIMITED", "LTD", "LLP", "LLC", "INC", "CORPORATION", "CORP", "PLC", "PTE",
]


def normalise_supplier(raw):
    """Uppercase, strip punctuation, collapse spaces, strip company suffixes."""
    name = raw.upper().replace("&", " AND ")
    name = re.sub(r"[.'\u2019`]", "", name)      # drop dots and apostrophes: "P.T.E." -> "PTE"
    name = re.sub(r"[^\w\s]", " ", name)         # other punctuation becomes a space
    name = re.sub(r"\s+", " ", name).strip()
    stripped = True
    while stripped:                               # "ABC PTE LTD" -> "ABC"
        stripped = False
        for suffix in SUPPLIER_SUFFIXES:
            if name.endswith(" " + suffix):
                name = name[: -len(suffix) - 1].strip()
                stripped = True
    return name


def read_csv():
    """Loader rule 1: explicit dtypes, explicit date format."""
    df = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False)
    for col in ["tender_no", "tender_description", "agency", "tender_detail_status", "supplier_name"]:
        df[col] = df[col].str.strip()
    df["awarded_amt"] = pd.to_numeric(df["awarded_amt"], errors="raise")
    df["award_dt"] = pd.to_datetime(df["award_date"], format="%d/%m/%Y", errors="raise")
    # Loader rule 2: Singapore fiscal year (April to March), labelled by start year.
    df["fiscal_year"] = df["award_dt"].dt.year.where(df["award_dt"].dt.month >= 4,
                                                     df["award_dt"].dt.year - 1)
    return df


def build_tables(df):
    """Return the Tender, Supplier, Agency and edge tables plus stats for the checks."""
    stats = {}

    # Rule 3: one Tender per tender_no, attributes from the first row.
    # Safety net: confirm they really are consistent within a tender.
    for col in ["tender_detail_status", "tender_description", "agency", "award_date"]:
        assert df.groupby("tender_no")[col].nunique().max() == 1, f"{col} varies within a tender"
    first = df.drop_duplicates("tender_no")
    tenders = pd.DataFrame({
        "tender_no": first["tender_no"],
        "description": first["tender_description"],
        "agency": first["agency"],
        "award_date": first["award_dt"].dt.strftime("%Y-%m-%d"),   # Neo4j date() reads ISO text
        "fiscal_year": first["fiscal_year"].astype(int),
        "source_status": first["tender_detail_status"],
        "awarded": first["tender_detail_status"] != NO_SUPPLIERS,   # rule 4
    }).reset_index(drop=True)
    agencies = sorted(tenders["agency"].unique())

    # Rule 5: "No Suppliers" rows make no Supplier and no edge.
    rows = df[df["tender_detail_status"] != NO_SUPPLIERS].copy()
    stats["edge_rows"] = len(rows)
    stats["unknown_on_awarded_rows"] = int((rows["supplier_name"].str.upper() == "UNKNOWN").sum())

    # Rule 6: normalise names. Guard: never let a name become empty.
    rows["normalized_name"] = rows["supplier_name"].map(normalise_supplier)
    empty = rows["normalized_name"] == ""
    stats["empty_name_fallbacks"] = int(empty.sum())
    rows.loc[empty, "normalized_name"] = rows.loc[empty, "supplier_name"].str.upper().str.strip()

    # Rule 7: if two raw names in one tender merge, sum onto one edge.
    edges = (rows.groupby(["tender_no", "normalized_name"], as_index=False)["awarded_amt"].sum()
             .rename(columns={"awarded_amt": "amount_sgd"}))
    stats["edges_after_merge"] = len(edges)
    stats["edges_collapsed"] = stats["edge_rows"] - len(edges)
    # Rule 8: zero-priced line items stay as edges with amount 0.
    stats["zero_edges"] = int((edges["amount_sgd"] == 0).sum())

    # Supplier table, keeping every raw variant.
    raw = rows.groupby("normalized_name")["supplier_name"].agg(lambda s: sorted(set(s)))
    suppliers = pd.DataFrame({"normalized_name": raw.index, "raw_names": raw.values})
    stats["raw_names_total"] = rows["supplier_name"].nunique()
    stats["suppliers"] = len(suppliers)
    stats["merged_suppliers"] = suppliers[suppliers["raw_names"].map(len) > 1]
    return tenders, suppliers, agencies, edges, stats


# ---------------------------------------------------------------------------
# Checks (shared helper) and the pandas-only checks
# ---------------------------------------------------------------------------

def check(results, label, actual, expected):
    ok = actual == expected
    results.append(ok)
    shown = f"{actual:,}" if isinstance(actual, int) and not isinstance(actual, bool) else actual
    want = f"{expected:,}" if isinstance(expected, int) and not isinstance(expected, bool) else expected
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {shown}" + ("" if ok else f" (expected {want})"))


def pandas_checks(df, tenders, suppliers, agencies, edges, stats):
    results = []
    print("\nPandas checks (no Neo4j):")
    check(results, "Tenders", len(tenders), EXPECTED_TENDERS)
    check(results, "Agencies", len(agencies), EXPECTED_AGENCIES)
    check(results, "Edge rows before name merging", stats["edge_rows"], EXPECTED_EDGE_ROWS)
    check(results, "Tenders with awarded = false", int((~tenders["awarded"]).sum()), EXPECTED_NOT_AWARDED)
    check(results, "'Unknown' supplier on rows that are NOT 'No Suppliers'", stats["unknown_on_awarded_rows"], 0)
    check(results, "Zero-amount edges", stats["zero_edges"], EXPECTED_ZERO_EDGES)
    check(results, "Edges after merge + collapsed = edge rows",
          stats["edges_after_merge"] + stats["edges_collapsed"], EXPECTED_EDGE_ROWS)
    print(f"  [INFO] Suppliers: {stats['suppliers']:,} normalised from {stats['raw_names_total']:,} raw names; "
          f"{len(stats['merged_suppliers']):,} suppliers hold more than one raw name; "
          f"{stats['edges_collapsed']:,} edges collapsed inside a tender; "
          f"{stats['empty_name_fallbacks']} empty-name fallbacks")
    print(f"  [INFO] Total edge amount: {money(edges['amount_sgd'].sum())}")
    return results


def print_merge_sample(stats, limit=15):
    """For the owner to eyeball: which raw names were merged together."""
    merged = stats["merged_suppliers"]
    print(f"\nSupplier name merges (first {min(limit, len(merged))} of {len(merged):,}):")
    for _, row in merged.head(limit).iterrows():
        print(f"  {row['normalized_name']!r} <- {row['raw_names']}")


# ---------------------------------------------------------------------------
# STEP 1c: Neo4j connection, constraints and load
# ---------------------------------------------------------------------------

def connect():
    """Credentials come from environment variables only."""
    missing = [k for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD") if not os.environ.get(k)]
    if missing:
        sys.exit("Missing environment variable(s): " + ", ".join(missing) +
                 "\nSee the header of this file for how to set them. Nothing is stored in the code.")
    from neo4j import GraphDatabase          # imported here so --prepare-only needs no driver
    driver = GraphDatabase.driver(os.environ["NEO4J_URI"],
                                  auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    driver.verify_connectivity()
    return driver


def session_for(driver):
    return driver.session(database=os.environ.get("NEO4J_DATABASE") or None)


# SCHEMA.md section 8, verbatim.
CONSTRAINTS = [
    "CREATE CONSTRAINT tender_no IF NOT EXISTS FOR (t:Tender) REQUIRE t.tender_no IS UNIQUE",
    "CREATE CONSTRAINT supplier_norm IF NOT EXISTS FOR (s:Supplier) REQUIRE s.normalized_name IS UNIQUE",
    "CREATE CONSTRAINT agency_name IF NOT EXISTS FOR (a:Agency) REQUIRE a.name IS UNIQUE",
    "CREATE CONSTRAINT category_code IF NOT EXISTS FOR (c:Category) REQUIRE c.code IS UNIQUE",
    "CREATE CONSTRAINT metric_id IF NOT EXISTS FOR (m:Metric) REQUIRE m.id IS UNIQUE",
]

# All load statements take their data through $rows. No Cypher is built from strings.
LOAD_CATEGORIES = """
UNWIND $rows AS row
MERGE (c:Category {code: row.code})
SET c.label = row.label, c.taxonomy_version = row.taxonomy_version
"""
LOAD_AGENCIES = """
UNWIND $rows AS row
MERGE (a:Agency {name: row.name})
"""
LOAD_SUPPLIERS = """
UNWIND $rows AS row
MERGE (s:Supplier {normalized_name: row.normalized_name})
SET s.raw_names = row.raw_names
"""
LOAD_TENDERS = """
UNWIND $rows AS row
MERGE (t:Tender {tender_no: row.tender_no})
SET t.description = row.description,
    t.award_date = date(row.award_date),
    t.fiscal_year = row.fiscal_year,
    t.source_status = row.source_status,
    t.awarded = row.awarded
WITH t, row
MATCH (a:Agency {name: row.agency})
MERGE (a)-[:ISSUED]->(t)
"""
LOAD_EDGES = """
UNWIND $rows AS row
MATCH (t:Tender {tender_no: row.tender_no})
MATCH (s:Supplier {normalized_name: row.normalized_name})
MERGE (t)-[r:AWARDED_TO]->(s)
SET r.amount_sgd = row.amount_sgd
"""
RESET_GRAPH = """
MATCH (n)
WHERE n:Tender OR n:Supplier OR n:Agency OR n:Category
DETACH DELETE n
"""


def native_records(df, casts):
    """DataFrame -> list of dicts with plain Python types (the driver rejects numpy types)."""
    return [{col: casts[col](row[col]) for col in casts} for _, row in df.iterrows()]


def run_batches(session, query, rows):
    for i in range(0, len(rows), BATCH_SIZE):
        session.run(query, rows=rows[i:i + BATCH_SIZE]).consume()


def load_graph(driver, tenders, suppliers, agencies, edges, reset=False):
    with session_for(driver) as session:
        if reset:
            print("--reset: deleting Tender, Supplier, Agency and Category nodes ...")
            session.run(RESET_GRAPH).consume()
        for statement in CONSTRAINTS:
            session.run(statement).consume()

        run_batches(session, LOAD_CATEGORIES,
                    [{"code": c, "label": l, "taxonomy_version": TAXONOMY_VERSION} for c, l, _ in TAXONOMY])
        run_batches(session, LOAD_AGENCIES, [{"name": a} for a in agencies])
        run_batches(session, LOAD_SUPPLIERS,
                    native_records(suppliers, {"normalized_name": str, "raw_names": list}))
        run_batches(session, LOAD_TENDERS, native_records(tenders, {
            "tender_no": str, "description": str, "agency": str, "award_date": str,
            "fiscal_year": int, "source_status": str, "awarded": bool}))
        run_batches(session, LOAD_EDGES, native_records(edges, {
            "tender_no": str, "normalized_name": str, "amount_sgd": float}))
    print("Load finished.")


def scalar(session, query, **params):
    return session.run(query, **params).single()[0]


def neo4j_checks(driver, tenders, suppliers, agencies, edges, stats):
    results = []
    print("\nNeo4j checks:")
    with session_for(driver) as s:
        check(results, "Tender nodes", scalar(s, "MATCH (t:Tender) RETURN count(t)"), EXPECTED_TENDERS)
        check(results, "Agency nodes", scalar(s, "MATCH (a:Agency) RETURN count(a)"), EXPECTED_AGENCIES)
        check(results, "ISSUED edges", scalar(s, "MATCH (:Agency)-[r:ISSUED]->(:Tender) RETURN count(r)"), EXPECTED_TENDERS)
        n_edges = scalar(s, "MATCH (:Tender)-[r:AWARDED_TO]->(:Supplier) RETURN count(r)")
        check(results, "AWARDED_TO edges equal edges built in pandas", n_edges, stats["edges_after_merge"])
        check(results, "AWARDED_TO edges + collapsed by name merging", n_edges + stats["edges_collapsed"], EXPECTED_EDGE_ROWS)
        print(f"  [INFO] AWARDED_TO edges in Neo4j: {n_edges:,} (17,825 before merging; "
              f"{stats['edges_collapsed']:,} collapsed)")
        check(results, "Tenders with awarded = false",
              scalar(s, "MATCH (t:Tender {awarded: false}) RETURN count(t)"), EXPECTED_NOT_AWARDED)
        check(results, "awarded = false tenders that have an AWARDED_TO edge",
              scalar(s, "MATCH (t:Tender {awarded: false})-[:AWARDED_TO]->() RETURN count(DISTINCT t)"), 0)
        check(results, "Supplier nodes named 'Unknown'",
              scalar(s, "MATCH (x:Supplier) WHERE toUpper(x.normalized_name) = $u "
                        "OR any(n IN x.raw_names WHERE toUpper(n) = $u) RETURN count(x)", u="UNKNOWN"), 0)
        check(results, "Supplier nodes", scalar(s, "MATCH (x:Supplier) RETURN count(x)"), stats["suppliers"])
        check(results, "Zero-amount AWARDED_TO edges",
              scalar(s, "MATCH ()-[r:AWARDED_TO]->() WHERE r.amount_sgd = $z RETURN count(r)", z=0), EXPECTED_ZERO_EDGES)
        check(results, "Category nodes", scalar(s, "MATCH (c:Category) RETURN count(c)"), len(TAXONOMY))
        total = scalar(s, "MATCH ()-[r:AWARDED_TO]->() RETURN sum(r.amount_sgd)")
        want = float(edges["amount_sgd"].sum())
        check(results, "Total edge amount (Neo4j vs pandas, within S$0.01)",
              abs(total - want) < 0.01, True)
        print(f"  [INFO] Total edge amount in Neo4j: {money(total)}")
        names = {r["name"] for r in s.run("SHOW CONSTRAINTS YIELD name")}
        needed = {"tender_no", "supplier_norm", "agency_name", "category_code", "metric_id"}
        check(results, "Required constraints present", needed <= names, True)
    return results


# ---------------------------------------------------------------------------
# STEP 2: Metric layer (governed definitions + fixed parameterized templates)
# ---------------------------------------------------------------------------
# A template is a fixed, human-written Cypher string with named parameters.
# run_template() is the ONLY way a metric query is executed, and it refuses any
# template id not listed here. The router (step 5) may only choose from this dict.

TEMPLATES = {
    # M1 awarded value, sliced by fiscal year (verification slice; SCHEMA.md section 9 has no agency-free M1).
    "M1_BY_FY": {
        "metric_id": "M1",
        "params": ["fy"],
        "cypher": """
MATCH (t:Tender {awarded: true, fiscal_year: $fy})-[r:AWARDED_TO]->(:Supplier)
WHERE r.amount_sgd > 0
RETURN sum(r.amount_sgd) AS awarded_value_sgd
""",
    },
    # M1 by agency and fiscal year: verbatim from SCHEMA.md section 9.
    "M1_BY_AGENCY_FY": {
        "metric_id": "M1",
        "params": ["agency", "fy"],
        "cypher": """
MATCH (a:Agency {name: $agency})-[:ISSUED]->(t:Tender {awarded: true, fiscal_year: $fy})
      -[r:AWARDED_TO]->(:Supplier)
WHERE r.amount_sgd > 0
RETURN sum(r.amount_sgd) AS awarded_value_sgd
""",
    },
    # M1 with the supplier dimension.
    "M1_BY_SUPPLIER_FY": {
        "metric_id": "M1",
        "params": ["supplier", "fy"],
        "cypher": """
MATCH (t:Tender {awarded: true, fiscal_year: $fy})
      -[r:AWARDED_TO]->(:Supplier {normalized_name: $supplier})
WHERE r.amount_sgd > 0
RETURN sum(r.amount_sgd) AS awarded_value_sgd
""",
    },
    # M2 supplier concentration: share of M1 held by the top N suppliers in a fiscal year.
    "M2_TOP_N_FY": {
        "metric_id": "M2",
        "params": ["fy", "top_n"],
        "cypher": """
MATCH (t:Tender {awarded: true, fiscal_year: $fy})-[r:AWARDED_TO]->(s:Supplier)
WHERE r.amount_sgd > 0
WITH s.normalized_name AS supplier, sum(r.amount_sgd) AS value
ORDER BY value DESC
WITH collect(value) AS values
WITH reduce(total = 0.0, v IN values | total + v) AS total_sgd,
     reduce(top = 0.0, v IN values[0..$top_n] | top + v) AS top_n_sgd
RETURN top_n_sgd, total_sgd, top_n_sgd / total_sgd AS top_n_share
""",
    },
    # M3 category spend: verbatim from SCHEMA.md section 9. Needs CLASSIFIED_AS (step 3).
    "M3_CATEGORY_SPEND_FY": {
        "metric_id": "M3",
        "params": ["fy", "threshold"],
        "cypher": """
MATCH (t:Tender {awarded: true, fiscal_year: $fy})-[c:CLASSIFIED_AS]->(cat:Category),
      (t)-[r:AWARDED_TO]->(:Supplier)
WHERE r.amount_sgd > 0 AND c.probability >= $threshold
RETURN cat.code AS category, sum(r.amount_sgd) AS awarded_value_sgd
ORDER BY awarded_value_sgd DESC
""",
    },
    # M4 coverage by value: verbatim from SCHEMA.md section 9. Needs CLASSIFIED_AS (step 3).
    "M4_COVERAGE_FY": {
        "metric_id": "M4",
        "params": ["fy", "threshold"],
        "cypher": """
MATCH (t:Tender {awarded: true, fiscal_year: $fy})-[c:CLASSIFIED_AS]->(:Category),
      (t)-[r:AWARDED_TO]->(:Supplier)
WHERE r.amount_sgd > 0
RETURN sum(CASE WHEN c.probability >= $threshold THEN r.amount_sgd ELSE 0 END) AS classified_sgd,
       sum(r.amount_sgd) AS total_sgd
""",
    },
    # M4 coverage by count: the second view of the same metric (SCHEMA.md section 6 asks for both).
    "M4_COVERAGE_COUNT_FY": {
        "metric_id": "M4",
        "params": ["fy", "threshold"],
        "cypher": """
MATCH (t:Tender {awarded: true, fiscal_year: $fy})-[c:CLASSIFIED_AS]->(:Category)
RETURN sum(CASE WHEN c.probability >= $threshold THEN 1 ELSE 0 END) AS classified_tenders,
       count(t) AS total_tenders
""",
    },
}

# Metric nodes (SCHEMA.md section 6). Each points at its base template; the other
# slices of the same metric are further entries in TEMPLATES with the same metric_id.
METRICS = [
    {"id": "M1", "name": "Awarded value", "version": "1.0",
     "definition": "Sum of amount_sgd where amount_sgd > 0 on tenders with awarded = true, attributed to the "
                   "fiscal year of award_date. Contract value at award date, not cash spent. Multi-year "
                   "contracts land entirely in the award year. Some values look like ceilings or estimates; "
                   "the data does not say which.",
     "dimensions": ["agency", "fiscal_year", "category", "supplier"], "cypher_template_id": "M1_BY_FY"},
    {"id": "M2", "name": "Supplier concentration", "version": "1.0",
     "definition": "Share of M1 held by the top N suppliers within a slice. Uses normalized names. "
                   "No entity resolution in v1.",
     "dimensions": ["agency", "fiscal_year", "category"], "cypher_template_id": "M2_TOP_N_FY"},
    {"id": "M3", "name": "Category spend", "version": "1.0",
     "definition": "M1 grouped by category, counting only tenders with probability >= threshold. "
                   "Always reported alongside the UNCLASSIFIED remainder.",
     "dimensions": ["agency", "fiscal_year"], "cypher_template_id": "M3_CATEGORY_SPEND_FY"},
    {"id": "M4", "name": "Classification coverage", "version": "1.0",
     "definition": "Share of M1 held by tenders with probability >= threshold. Report both by value and by "
                   "count. The gap between the two is itself a finding.",
     "dimensions": ["agency", "fiscal_year"], "cypher_template_id": "M4_COVERAGE_FY"},
]
LOAD_METRICS = """
UNWIND $rows AS row
MERGE (m:Metric {id: row.id})
SET m.name = row.name, m.definition = row.definition, m.version = row.version,
    m.dimensions = row.dimensions, m.cypher_template_id = row.cypher_template_id
"""


def run_template(driver, template_id, params):
    """Run one governed template. Unknown ids and wrong parameters are refused."""
    if template_id not in TEMPLATES:
        raise KeyError(f"Unknown template id {template_id!r}. Allowed: {sorted(TEMPLATES)}")
    template = TEMPLATES[template_id]
    if set(params) != set(template["params"]):
        raise ValueError(f"{template_id} needs exactly these parameters: {template['params']}")
    with session_for(driver) as session:
        return [record.data() for record in session.run(template["cypher"], params)]


def create_metrics(driver):
    with session_for(driver) as session:
        session.run(LOAD_METRICS, rows=METRICS).consume()
    print(f"\nMetric layer: {len(METRICS)} Metric nodes written, {len(TEMPLATES)} templates registered.")


def metric_checks(driver, df, rows_edges, edges, suppliers_by_edge):
    """Step 2 verification: Cypher results against plain pandas."""
    results = []
    print("\nMetric checks:")
    with session_for(driver) as s:
        check(results, "Metric nodes", scalar(s, "MATCH (m:Metric) RETURN count(m)"), len(METRICS))
    try:
        run_template(driver, "NOT_A_TEMPLATE", {})
        check(results, "Unknown template id is refused", False, True)
    except KeyError:
        check(results, "Unknown template id is refused", True, True)

    # M1 by fiscal year vs pandas computed straight from the CSV (independent of the loader tables).
    awarded = df[(df["tender_detail_status"] != NO_SUPPLIERS) & (df["awarded_amt"] > 0)]
    pandas_fy = awarded.groupby("fiscal_year")["awarded_amt"].sum()
    print("\n  M1 awarded value by fiscal year (contract value at award date, not cash spent):")
    print(f"  {'FY':<8}{'Cypher':>22}{'pandas':>22}{'difference':>14}")
    for fy in FISCAL_YEARS:
        got = run_template(driver, "M1_BY_FY", {"fy": fy})[0]["awarded_value_sgd"] or 0.0
        want = float(pandas_fy.get(fy, 0.0))
        print(f"  FY{fy:<6}{money(got):>22}{money(want):>22}{got - want:>14,.2f}")
        check(results, f"M1 FY{fy} matches pandas (within S$0.01)", abs(got - want) < 0.01, True)

    # M1 by agency must add up to M1 for the year.
    fy = 2024
    agencies = sorted(df["agency"].unique())
    by_agency = sum((run_template(driver, "M1_BY_AGENCY_FY", {"agency": a, "fy": fy})[0]["awarded_value_sgd"] or 0.0)
                    for a in agencies)
    check(results, f"M1 by agency adds up to M1 for FY{fy} (within S$0.01)",
          abs(by_agency - float(pandas_fy[fy])) < 0.01, True)

    # M1 by supplier and M2 against pandas on the edge table.
    e = edges.merge(rows_edges, on="tender_no")
    e = e[(e["fiscal_year"] == fy) & (e["amount_sgd"] > 0) & (e["awarded"])]
    per_supplier = e.groupby("normalized_name")["amount_sgd"].sum().sort_values(ascending=False)
    top_name, top_value = per_supplier.index[0], float(per_supplier.iloc[0])
    got = run_template(driver, "M1_BY_SUPPLIER_FY", {"supplier": top_name, "fy": fy})[0]["awarded_value_sgd"]
    check(results, f"M1 by supplier FY{fy}, largest supplier {top_name!r} matches pandas",
          abs(got - top_value) < 0.01, True)
    m2 = run_template(driver, "M2_TOP_N_FY", {"fy": fy, "top_n": 10})[0]
    want_share = float(per_supplier.head(10).sum() / per_supplier.sum())
    check(results, f"M2 top-10 supplier share FY{fy} matches pandas",
          abs(m2["top_n_share"] - want_share) < 1e-9, True)
    print(f"  [INFO] FY{fy} top-10 suppliers hold {m2['top_n_share']:.1%} of awarded value "
          f"({money(m2['top_n_sgd'])} of {money(m2['total_sgd'])}). By value, not by count.")
    results += classification_metric_checks(driver, awarded, df)
    return results


def classification_metric_checks(driver, awarded, df):
    """M3 and M4 against pandas, using the classifications as stored in Neo4j.
    Skipped (with a message) if step 3 has not been run yet."""
    with session_for(driver) as s:
        stored = [r.data() for r in s.run(
            "MATCH (t:Tender)-[c:CLASSIFIED_AS]->() RETURN t.tender_no AS tender_no, c.probability AS p")]
    if not stored:
        print("\n  [INFO] No CLASSIFIED_AS edges yet; M3 and M4 not checked (run --classify first).")
        return []
    results = []
    prob = pd.DataFrame(stored).set_index("tender_no")["p"]
    th = THRESHOLD
    print(f"\n  M4 classification coverage at threshold {th} (by value in S$, and by count of awarded tenders):")
    print(f"  {'FY':<8}{'by value':>10}{'classified S$':>22}{'total S$':>22}{'by count':>10}{'classified':>12}{'total':>8}")
    all_tenders = df[df["tender_detail_status"] != NO_SUPPLIERS].drop_duplicates("tender_no")
    for fy in FISCAL_YEARS:
        # Independent pandas version.
        rows = awarded[awarded["fiscal_year"] == fy]
        ok_value = rows["tender_no"].map(prob) >= th
        want_cls, want_tot = float(rows["awarded_amt"][ok_value].sum()), float(rows["awarded_amt"].sum())
        tenders_fy = all_tenders[all_tenders["fiscal_year"] == fy]
        ok_count = int((tenders_fy["tender_no"].map(prob) >= th).sum())
        # Governed templates.
        m4 = run_template(driver, "M4_COVERAGE_FY", {"fy": fy, "threshold": th})[0]
        m4c = run_template(driver, "M4_COVERAGE_COUNT_FY", {"fy": fy, "threshold": th})[0]
        print(f"  FY{fy:<6}{m4['classified_sgd'] / m4['total_sgd']:>10.1%}{money(m4['classified_sgd']):>22}"
              f"{money(m4['total_sgd']):>22}{m4c['classified_tenders'] / m4c['total_tenders']:>10.1%}"
              f"{m4c['classified_tenders']:>12,}{m4c['total_tenders']:>8,}")
        check(results, f"M4 FY{fy} by value matches pandas (within S$0.01)",
              abs(m4["classified_sgd"] - want_cls) < 0.01 and abs(m4["total_sgd"] - want_tot) < 0.01, True)
        check(results, f"M4 FY{fy} by count matches pandas",
              (m4c["classified_tenders"], m4c["total_tenders"]) == (ok_count, len(tenders_fy)), True)
        # M3 splits the same classified value by category, so it must add up to M4.
        m3 = run_template(driver, "M3_CATEGORY_SPEND_FY", {"fy": fy, "threshold": th})
        check(results, f"M3 FY{fy} categories add up to M4 classified value (within S$0.01)",
              abs(sum(r["awarded_value_sgd"] for r in m3) - m4["classified_sgd"]) < 0.01, True)
    return results


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="GeBIZ knowledge graph build (steps 1 to 3).")
    parser.add_argument("--prepare-only", action="store_true", help="pandas checks only, no Neo4j")
    parser.add_argument("--reset", action="store_true", help="wipe graph data first, then reload")
    parser.add_argument("--trial", type=int, metavar="N",
                        help="step 3 dry run: classify N hand-labelled sample tenders, write nothing to Neo4j")
    parser.add_argument("--classify", action="store_true",
                        help="step 3 full run: classify every tender with Jev and write CLASSIFIED_AS edges")
    args = parser.parse_args()
    if args.trial is not None and not 1 <= args.trial <= 150:
        sys.exit("--trial N needs N between 1 and 150 (the size of the hand-labelled sample).")

    df = read_csv()
    print(f"Read {len(df):,} rows, {df['tender_no'].nunique():,} tenders from {os.path.basename(CSV_PATH)}")
    tenders, suppliers, agencies, edges, stats = build_tables(df)

    if args.trial is not None:                       # needs no Neo4j at all
        run_trial(tenders, args.trial)
        return

    results = pandas_checks(df, tenders, suppliers, agencies, edges, stats)
    print_merge_sample(stats)

    if args.prepare_only:
        print("\n--prepare-only: stopping before Neo4j.")
        sys.exit(0 if all(results) else 1)
    if not all(results):
        sys.exit("\nPandas checks failed. Not loading anything into Neo4j.")

    driver = connect()
    try:
        if args.classify:                            # classification only; the graph is already loaded
            run_classification(driver, tenders)
            with session_for(driver) as session:
                n_edges = scalar(session, "MATCH ()-[r:CLASSIFIED_AS]->() RETURN count(r)")
                n_tenders_with = scalar(session, "MATCH (t:Tender)-[:CLASSIFIED_AS]->() RETURN count(DISTINCT t)")
            ok = []
            check(ok, "CLASSIFIED_AS edges", n_edges, len(tenders))
            check(ok, "tenders with exactly one edge", n_tenders_with, n_edges)
            sys.exit(0 if all(ok) else 1)
        load_graph(driver, tenders, suppliers, agencies, edges, reset=args.reset)
        results += neo4j_checks(driver, tenders, suppliers, agencies, edges, stats)
        create_metrics(driver)
        results += metric_checks(driver, df, tenders[["tender_no", "fiscal_year", "awarded"]], edges, None)
    finally:
        driver.close()

    print("\nALL CHECKS PASSED." if all(results) else "\nSOME CHECKS FAILED. See FAIL lines above.")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
