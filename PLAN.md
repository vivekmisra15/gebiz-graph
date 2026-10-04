# Project plan (plain language)

This is a reader's guide for the owner. The authoritative instructions are in [CLAUDE.md](CLAUDE.md) (what to build and the hard constraints) and [SCHEMA.md](SCHEMA.md) (the graph design). If this file disagrees with either of them, they win.

**How this file avoids going stale.** It holds only two kinds of content: the plan (which rarely changes) and a dated decision log (which is only ever added to, never edited). It does **not** say which steps are finished. Progress lives in one place only: the Status table in [README.md](README.md). The rule, written into CLAUDE.md: at the end of each step, update the README status table and add any new decisions to the log below. Nothing else needs touching.

## The goal in one paragraph

Show that, in an audited setting, a model should only **select** among definitions that humans wrote, and should say "I'm not sure" instead of guessing. Humans write the category list and the metric definitions. The model picks a category for each tender and, later, picks which fixed query answers a question. Every pick is recorded with its probability. When the model is not confident, the answer is "unclassified" or "I need more information".

## The six steps and when each is done

Do not start a step until the previous step's checks pass.

| # | Step | In plain words | Done when |
|---|---|---|---|
| 1 | Loader | Read the GeBIZ CSV and build the graph in Neo4j | 12,052 tenders and 17,825 award links load, and counts match the profiling facts |
| 2 | Metric layer | Store the four metric definitions (M1 to M4) as fixed, parameterised queries | M1 totals by fiscal year equal an independent pandas calculation |
| 3 | Classification | Jev puts each tender in one of the 10 categories. A keyword-rule version does the same, for comparison | Every tender has a `CLASSIFIED_AS` link with probability, confidence, model, taxonomy version and time. The keyword run exists for the same tenders |
| 4 | Calibration | Check Jev against about 30 hand-labelled tenders and set the confidence threshold (start 0.7, then stop tuning) | Threshold chosen, and the decision on whether it tests `probability` or `confidence` is written down |
| 5 | Router | Turn a typed question into one of the fixed queries, or abstain | About 10 fixed demo questions run; the 2 or 3 deliberately ambiguous ones abstain |
| 6 | Audit log | One line per classification and per router decision | Every router call and classification can be traced from the log |

What the project must produce: a governed query layer (M1 to M4, each shown with its definition, threshold and unclassified share), the audit trail, one finding (M4 classification coverage by count and by value, and the gap), and the Phase 1 private thesis note.

Out of scope: dashboards or visuals, graph algorithms, supplier matching beyond simple name cleanup, extra datasets, evaluation benchmarks beyond the demo questions. Flag these rather than build them.

## Decision log

Append new entries at the bottom. Do not rewrite old ones; if a decision changes, add a new entry that says so.

| Date | Decision |
|---|---|
| 2026-10-03 | Taxonomy frozen as v1.0 (C01 to C10). |
| 2026-10-03 | Malaysian "SDN BHD" suppliers stay separate from Singapore "PTE LTD" ones. |
| 2026-10-04 | Sample relabels: CDVHQ0ETT21000045 to C06; DEF000ETT20300060 to UNCLASSIFIED (used to test abstention, not as a calibration label); HPB000ETT21000028 to C08; MAS server relocation confirmed C09. |
| 2026-10-04 | `CLASSIFIED_AS` stores both `probability` and `confidence`. Which one the threshold tests is decided in step 4 on the hand-labels. Until then queries use `probability`. |
| 2026-10-04 | Secrets (Neo4j password, TypeSafe key) are never pasted into chat or saved in the project. |
| 2026-10-04 | One build script stays the rule; one-off helper scripts live in `helpers/`. Run findings are logged in RESULTS.md. |
| 2026-10-04 | Vague boilerplate descriptions (5 found) get confident C10 answers. Not fixed; reported as a finding in RESULTS.md. |
