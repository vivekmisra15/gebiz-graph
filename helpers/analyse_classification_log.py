"""Analyse a full classification run from classification_log.jsonl. Read-only, needs no Neo4j.

Run from the project folder: python helpers/analyse_classification_log.py
Reproduces the figures in RESULTS.md (step 3 run). Uses the lines with mode "full";
trial lines are ignored. If the log holds several full runs, the latest line per
tender wins.
"""
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9]
START_THRESHOLD = 0.7

log = pd.DataFrame([json.loads(line) for line in open(os.path.join(ROOT, "classification_log.jsonl"))])
log = log[log["mode"] == "full"].drop_duplicates("tender_no", keep="last")

raw = pd.read_csv(os.path.join(ROOT, "gebiz.csv"), dtype=str, keep_default_na=False)
raw["amt"] = pd.to_numeric(raw["awarded_amt"])
tenders = raw.groupby("tender_no").agg(description=("tender_description", "first"),
                                       value=("amt", "sum")).reset_index()
d = log.merge(tenders, on="tender_no")
total_value = d["value"].sum()
print(f"Tenders: {len(d):,}   total awarded value: S${total_value:,.0f}   model: {d['model'].unique()}")

print("\nTenders per category (by count):")
print(d["code"].value_counts().sort_index().to_string())

print("\nShare below each threshold (UNCLASSIFIED), by count:")
for th in THRESHOLDS:
    print(f"  < {th}:  probability {(d['probability'] < th).mean():6.1%}   confidence {(d['confidence'] < th).mean():6.1%}")

gap = d["probability"] - d["confidence"]
print(f"\nprobability minus confidence: mean {gap.mean():.3f}, 90th percentile {gap.quantile(.9):.3f}, max {gap.max():.3f}")
by_p, by_c = d["probability"] >= START_THRESHOLD, d["confidence"] >= START_THRESHOLD
print(f"At {START_THRESHOLD}: pass on probability only: {(by_p & ~by_c).sum()}, on confidence only: {(~by_p & by_c).sum()}")

print(f"\nCoverage at {START_THRESHOLD}:")
for name, mask in (("probability", by_p), ("confidence", by_c)):
    print(f"  {name:<12} by count {mask.mean():.1%} ({mask.sum():,} tenders)   "
          f"by value {d['value'][mask].sum() / total_value:.1%} (S${d['value'][mask].sum():,.0f}; "
          f"unclassified S${d['value'][~mask].sum():,.0f})")

boiler = d[d["description"].str.strip().str.contains(
    r"^(?:please )?refer to (?:the )?(?:attached|tender|invitation|request)[^.]*(?:document|details|information)[^.]*\.?$",
    case=False, regex=True)]
print(f"\nBoilerplate-only descriptions ('refer to the attached ...'): {len(boiler)}; "
      f"categories {boiler['code'].value_counts().to_dict()}; "
      f"answered at probability >= {START_THRESHOLD}: {(boiler['probability'] >= START_THRESHOLD).sum()}; "
      f"value S${boiler['value'].sum():,.0f}")
print(f"C10 total {(d['code'] == 'C10').sum()}, of which at >= {START_THRESHOLD}: {((d['code'] == 'C10') & by_p).sum()}")

answered = d["rule_code"].notna()
agree = d["rule_code"] == d["code"]
print(f"\nKeyword rules answered {answered.sum():,} ({answered.mean():.1%}); agree with Jev on {agree[answered].mean():.1%} of those"
      f" ({agree[answered & by_p].mean():.1%} where Jev >= {START_THRESHOLD}, {agree[answered & ~by_p].mean():.1%} where below).")
print("Agreement with Jev is not accuracy: neither side has ground truth outside the 150 hand-labelled tenders.")
