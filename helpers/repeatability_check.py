"""Repeatability check: does the same input give the same Jev answer?

Run from the project folder: python helpers/repeatability_check.py
Needs TYPESAFE_API_KEY. No Neo4j. Costs a few cents (30 + 12 inputs, 2 fresh runs each).

For each input it compares three observations: the stored one from the audit log
(classification_log.jsonl, router_log.jsonl) and two fresh calls made now. It reports
the largest probability change, whether the chosen option changed, and whether the
0.7 decision (answer vs UNCLASSIFIED / abstain) would flip. Writes nothing to the logs.
"""
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)                                              # so gebiz_graph can be imported
import gebiz_graph as g

if not os.environ.get("TYPESAFE_API_KEY"):
    sys.exit("Needs TYPESAFE_API_KEY. Nothing was run.")

FRESH_RUNS = 2


def last_lines(path, key, keep):
    """Latest audit line per key, filtered by keep(line)."""
    latest = {}
    for raw in open(path, encoding="utf-8"):
        line = json.loads(raw)
        if keep(line):
            latest[line[key]] = line
    return latest


def compare(name, rows, threshold):
    """rows: list of (id, [obs, obs, obs]) where obs = (choice, probability, distribution)."""
    print(f"\n=== {name} ===")
    print(f"{'id':<40}{'choices':<28}{'max p change':>13}{'max any-option change':>23}{'0.7 flips':>11}")
    n_choice, n_flip, worst, worst_any = 0, 0, 0.0, 0.0
    for ident, obs in rows:
        choices = [o[0] for o in obs]
        probs = [o[1] for o in obs]
        d_top = max(probs) - min(probs)
        options = set().union(*[o[2].keys() for o in obs])
        d_any = max(max(o[2].get(k, 0.0) for o in obs) - min(o[2].get(k, 0.0) for o in obs) for k in options)
        flip = len({p >= threshold for p in probs}) > 1
        changed = len(set(choices)) > 1
        n_choice += changed
        n_flip += flip
        worst, worst_any = max(worst, d_top), max(worst_any, d_any)
        label = ",".join(c[:10] for c in choices) if changed else choices[0][:26]
        print(f"{str(ident)[:39]:<40}{label:<28}{d_top:>13.3f}{d_any:>23.3f}{'YES' if flip else '':>11}")
    print(f"Summary: {len(rows)} inputs; choice changed on {n_choice}; "
          f"{threshold} decision flipped on {n_flip}; "
          f"largest change in the chosen option's probability {worst:.3f}; in any option {worst_any:.3f}.")


# --- 1. Classification: the 30 calibration tenders ---------------------------
labels = pd.read_csv(os.path.join(ROOT, "calibration_labels.csv"), dtype=str, keep_default_na=False)
stored = last_lines(g.LOG_PATH, "tender_no", lambda l: l.get("mode") == "full")
rows = []
for _, r in labels.iterrows():
    old = stored[r["tender_no"]]
    obs = [(old["code"], old["probability"], old["probabilities"])]
    for _ in range(FRESH_RUNS):
        res = g.classify_with_jev(r["description"])
        obs.append((res["code"], res["probability"], res["probabilities"]))
    rows.append((r["tender_no"], obs))
print(f"Stored model: {stored[labels.iloc[0]['tender_no']]['model']}; fresh model: {g.JEV_MODEL}")
compare("Classification, 30 calibration tenders (stored, fresh, fresh)", rows, g.THRESHOLD)

# --- 2. Router: the 12 demo questions ----------------------------------------
stored_q = last_lines(g.ROUTER_LOG_PATH, "question", lambda l: l.get("step") == "route")
rows = []
for question, _expected in g.DEMO_QUESTIONS:
    obs = []
    if question in stored_q:
        old = stored_q[question]
        obs.append((old["template"], old["probability"], old["probabilities"]))
    for _ in range(FRESH_RUNS):
        res = g.route_with_jev(question)
        obs.append((res["template"], res["probability"], res["probabilities"]))
    rows.append((question, obs))
if all(len(o) == FRESH_RUNS + 1 for _, o in rows):
    compare("Router, 12 demo questions (stored, fresh, fresh)", rows, g.ROUTER_THRESHOLD)
else:
    print("\nSome demo questions have no stored router_log.jsonl line; comparing the fresh runs only.")
    compare("Router, 12 demo questions (fresh, fresh)", [(i, o[-FRESH_RUNS:]) for i, o in rows], g.ROUTER_THRESHOLD)
