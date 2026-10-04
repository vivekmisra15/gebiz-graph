"""Throwaway smoke test: send a few sample tenders to Jev and print the raw answer.

Not part of the build. Kept as a record of the first live check of the Jev call.
Run from the project folder: python helpers/smoke_test_jev.py   (needs TYPESAFE_API_KEY).
Reads the taxonomy from gebiz_graph.py so there is only one copy of it.
"""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project folder
sys.path.insert(0, ROOT)                                              # so gebiz_graph can be imported

from typesafe_sdk import TypeSafeClient, Choice

from gebiz_graph import TAXONOMY

# Jev sees option names and descriptions, not codes, so the label is the option name.
CRITERIA = {label: desc for _code, label, desc in TAXONOMY}
LABEL_TO_CODE = {label: code for code, label, _desc in TAXONOMY}

# One abstention test, three formerly doubtful labels, and the first clear C06 row.
IDS = ["DEF000ETT20300060", "MAS000ETT25000037", "CDVHQ0ETT21000045",
       "HPB000ETT21000028", "MUI000ETT22000005"]

rows = {r["tender_no"]: r
        for r in csv.DictReader(open(os.path.join(ROOT, "sample_150_tenders_classified_reviewed.csv"), newline=""))}

client = TypeSafeClient()  # reads TYPESAFE_API_KEY from the environment
question = Choice(
    instructions="Pick the one category that best describes this Singapore government tender.",
    criteria=CRITERIA,
)

for tender_no in IDS:
    row = rows[tender_no]
    resp = client.system_one(
        state=row["tender_description"],
        questions={"category": question},
        model="jev-1.13.0",
    )
    ans = resp.answers["category"]
    print("=" * 70)
    print(tender_no, "| my label:", row["my_category"])
    print("text:", row["tender_description"][:100])
    print("Jev choice:", LABEL_TO_CODE.get(ans.choice, ans.choice), "-", ans.choice)
    print("confidence:", ans.confidence)
    top3 = sorted(ans.probabilities.items(), key=lambda kv: -kv[1])[:3]
    for label, p in top3:
        print(f"  probability {p:.3f}  {LABEL_TO_CODE.get(label, label)}  {label}")
    print("usage:", resp.usage)
