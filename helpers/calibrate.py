"""Step 4 calibration: compare Jev with the owner-approved hand labels. Read-only, no Neo4j.

Run from the project folder: python helpers/calibrate.py
Uses calibration_labels.csv (30 labels) and the Jev answers already in
classification_log.jsonl (latest full-run line per tender). Nothing here calls Jev.
"""
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9]

labels = pd.read_csv(os.path.join(ROOT, "calibration_labels.csv"), dtype=str, keep_default_na=False)
log = pd.DataFrame([json.loads(line) for line in open(os.path.join(ROOT, "classification_log.jsonl"))])
log = log[log["mode"] == "full"].drop_duplicates("tender_no", keep="last")
d = labels.merge(log[["tender_no", "code", "probability", "confidence"]], on="tender_no", how="left")
assert d["code"].notna().all(), "a labelled tender is missing from the audit log"
d["right"] = d["code"] == d["hand_label"]

print(f"{len(d)} labelled tenders; Jev right on {d['right'].sum()} ({d['right'].mean():.0%}), counts.\n")
print("Every answer, lowest probability first:")
print(d.sort_values("probability")[["tender_no", "hand_label", "code", "probability", "confidence", "right"]]
      .to_string(index=False))

print("\nWrong answers:")
wrong = d[~d["right"]]
print(wrong[["tender_no", "hand_label", "code", "probability", "confidence", "label_note"]].to_string(index=False)
      if len(wrong) else "  none")

print("\nWhat each threshold would do (counts out of %d):" % len(d))
print(f"{'score':<12}{'thresh':>7}{'answered':>10}{'right':>7}{'wrong':>7}{'abstained':>11}{'abstained & was right':>23}")
for col in ("probability", "confidence"):
    for th in THRESHOLDS:
        ans = d[col] >= th
        print(f"{col:<12}{th:>7}{ans.sum():>10}{(ans & d['right']).sum():>7}{(ans & ~d['right']).sum():>7}"
              f"{(~ans).sum():>11}{(~ans & d['right']).sum():>23}")

# Where the abstention test row sits (hand label UNCLASSIFIED, not part of the 30).
print("\nAbstention test row DEF000ETT20300060 (hand label UNCLASSIFIED):")
t = log[log["tender_no"] == "DEF000ETT20300060"].iloc[0]
print(f"  Jev {t['code']} probability {t['probability']:.2f} confidence {t['confidence']:.2f} "
      f"-> {'would abstain' if t['probability'] < 0.7 else 'would NOT abstain at 0.7'}")
