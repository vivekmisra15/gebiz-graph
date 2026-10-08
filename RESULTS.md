# Results log

Findings from each run, kept for later reference (the thesis note draws on this). Append a new dated section per run; do not rewrite old ones. Design decisions live in [PLAN.md](PLAN.md), not here.

## Step 3: classification run, 2026-10-04

**Setup.** Jev (`jev-1.13.0`) classified all 12,052 tenders into taxonomy v1.0 (C01 to C10), one call per tender, description text only. 0 failures. 7,599,838 input tokens, about US$0.32. One `CLASSIFIED_AS` edge per tender with `probability`, `confidence`, model, taxonomy version and time. The keyword-rule fallback was run on the same tenders for comparison and is recorded in the audit log.

**Reproduce.** `python helpers/analyse_classification_log.py` (reads `classification_log.jsonl`, which is git-ignored; it holds one line per classification including the full probability distribution).

### Trial before the full run (20 tenders from the hand-labelled sample)

Jev 19 of 20 right against hand labels, keyword rules 10 of 20 (counts). The one miss was HPB000ETT21000028 (hand label C08, Jev C01 at probability 0.46), below 0.7 so it would abstain. Caveat: the taxonomy's boundary rules were derived from the same 150 labelled tenders, so this is an upper bound on accuracy, not an estimate for the other ~11,900 tenders.

### Coverage at the starting threshold of 0.7

| | By count | By value |
|---|---|---|
| Classified (probability >= 0.7) | 87.2% (10,504 tenders) | 92.8% (S$114.9B of S$123.8B) |
| UNCLASSIFIED (probability < 0.7) | 12.8% (1,548 tenders) | 7.2% (S$8.9B) |

Surprise: coverage is higher by value than by count. The large contracts are classified more confidently than the small ones, the opposite of what SCHEMA.md anticipated. Preliminary: the threshold is not final, and the figures above are computed from the audit log. The Cypher M4 templates are checked against pandas separately (see the next section once recorded).

Tenders per category, by count: C01 1,867; C02 2,238; C03 1,280; C04 2,126; C05 194; C06 1,240; C07 2,039; C08 262; C09 293; C10 513.

Share below each threshold, by count (probability / confidence): 0.5: 2.7% / 5.3%; 0.6: 7.5% / 9.7%; 0.7: 12.8% / 14.7%; 0.8: 18.4% / 19.9%; 0.9: 26.3% / 27.8%.

### Probability vs confidence

`confidence` is never above `probability`; it is equal or lower by up to 0.09 (mean 0.012). At 0.7, 229 tenders pass on probability and fail on confidence, none the other way. Which one the threshold should test is for step 4 calibration to decide on the hand labels.

### Known weakness: uninformative text gets a confident answer

5 tenders have boilerplate-only descriptions ("Please refer to the attached document ..."). All 5 went to C10 (Other Services) at probability 0.92 to 0.99, so none would abstain at 0.7. Together they hold S$2.9M, about 0.002% of total value. The pattern is narrow, so a few more may exist. The likely cause: C10 is defined as "confidently none of C01 to C09", and Jev appears to read uninformative text as "fits none". Owner decision 2026-10-04: do not fix now; report it as a finding. Other C10 answers sampled (insurance, meals-on-wheels, hotline services) look sensible; 325 tenders are in C10 at 0.7 or above.

### Jev against the keyword rules (all tenders)

Rules answered 9,152 tenders (75.9%) and agreed with Jev on 66.2% of those: 69.3% where Jev is at or above 0.7, 37.5% where it is below. Agreement is not accuracy, because neither side has ground truth outside the 150 hand-labelled tenders. It is consistent with Jev being more reliable where it is confident.

### M3 and M4 from the governed Cypher templates (checked against pandas)

Run on 2026-10-04 with `python gebiz_graph.py`, threshold 0.7 on `probability`. All 15 checks passed (M4 by value and by count against pandas, and M3's categories adding up to M4's classified value, for each fiscal year). The five years sum to the same totals as the audit-log analysis above (S$123,821,872,772 total; S$114,905,742,561 classified), an independent cross-check.

M4 counts here use **awarded tenders only** (11,413 of the 12,052; the 639 "Awarded to No Suppliers" tenders have no value and are excluded). The 87.2% figure in the earlier table uses all 12,052 tenders; on awarded tenders only it is 87.3% (9,958 of 11,413).

| Fiscal year | By value | Classified S$ | Total S$ | By count | Classified | Total |
|---|---|---|---|---|---|---|
| FY2021 | 96.5% | 23,331,330,060 | 24,180,846,937 | 87.2% | 2,036 | 2,334 |
| FY2022 | 89.3% | 17,614,302,099 | 19,725,072,951 | 86.0% | 1,875 | 2,181 |
| FY2023 | 96.3% | 20,879,278,505 | 21,682,674,098 | 87.0% | 1,934 | 2,224 |
| FY2024 | 91.6% | 25,050,510,894 | 27,351,102,095 | 89.0% | 2,110 | 2,371 |
| FY2025 | 90.8% | 28,030,321,003 | 30,882,176,691 | 87.0% | 2,003 | 2,303 |

Reading it: count coverage is steady at 86% to 89% across years, while value coverage moves between 89% and 97% and is always higher than count coverage. The gap (value minus count) ranges from 2.6 points (FY2024) to 9.3 points (FY2021). FY2022 has the lowest value coverage (S$2.1B unclassified). Not yet investigated: which large contracts sit below 0.7 in FY2022 and FY2025. Value is dominated by a few large contracts, so a handful of tenders can move these percentages. Preliminary until the threshold is set in step 4.

## Step 4: calibration, 2026-10-04

**Decision.** Threshold 0.7, tested on `probability`. No further tuning. Both numbers stay stored on `CLASSIFIED_AS`. The setting is the `THRESHOLD` constant in `gebiz_graph.py`; M3 and M4 use it.

**Reproduce.** `python helpers/calibrate.py` (reads `calibration_labels.csv` and the audit log; calls nothing).

### The 30 labels

3 per category (C01 to C10), drawn at random with a fixed seed from the owner's reviewed sample using the labels only (Jev's answers were not looked at before the list was approved). Excluded: the four doubtful tenders (CDVHQ0ETT21000045, DEF000ETT20300060, HPB000ETT21000028, MAS000ETT25000037) and the UNCLASSIFIED row. Owner approved the list after reviewing four borderline labels: NPB000ETT22000047 stays C05; SSC000ETT25000021 stays C08 (awkward fit, closest category); STB000ETT23000026 stays C01 (thin text, owner's educated guess); JUDSUPETT23000007 stays C09 (storage counts as warehousing). Notes are in the `label_note` column.

### Result: Jev right on 27 of 30 (counts)

| Tender | Hand label | Jev | Probability | Confidence |
|---|---|---|---|---|
| NPB000ETT22000047 (biodiversity studies consultancy) | C05 | C04 | 0.53 | 0.47 |
| PUB000ETT23000137 (hydrographic survey, soil investigation) | C05 | C04 | 0.83 | 0.81 |
| SSC000ETT25000021 (sports food) | C08 | C07 | 0.82 | 0.80 |

All three errors sit on boundaries already known to be fuzzy (C04 vs C05; the awkward sports-food fit), and are arguable rather than clear failures. Only the first is caught at 0.7.

### What each threshold does on the 30 (probability)

| Threshold | Answered | Right | Wrong | Abstained (of which right) |
|---|---|---|---|---|
| 0.5 | 30 | 27 | 3 | 0 |
| 0.6 | 29 | 27 | 2 | 1 (0) |
| 0.7 | 28 | 26 | 2 | 2 (1) |
| 0.8 | 28 | 26 | 2 | 2 (1) |
| 0.9 | 25 | 25 | 0 | 5 (2) |

Cost of each threshold across all 12,052 tenders (probability): coverage by count / by value is 0.5: 97.3% / 98.7%; 0.6: 92.5% / 95.4%; 0.7: 87.2% / 92.8%; 0.8: 81.6% / 89.9%; 0.9: 73.7% / 86.5%.

### Why 0.7 on probability

- Probability and confidence gave the same results at 0.7, 0.8 and 0.9 (they differ only at 0.5, where confidence also catches the 0.47 tender). The data does not prefer one, so the simpler number, already used by the stored M3/M4 templates, was kept.
- 0.9 would remove the two remaining errors here, but that rests on two arguable boundary cases in 30 labels (fitting to noise), and it would abstain on about a quarter of all tenders (26.3% by count). CLAUDE.md says start at 0.7 and stop tuning.
- Reading: about 2 of 28 answered tenders were wrong in this small sample, mostly boundary cases.

### Limits

- 30 labels cannot place a threshold precisely; the uncertainty around "2 of 28" is wide.
- The labels come from the pool the taxonomy's boundary rules were derived from, and were picked 3 per category (not a random draw across categories), so 90% accuracy is likely an upper bound for the other tenders.
- The abstention test row (DEF000ETT20300060, "Please refer to the attached tender documents") scores probability 0.99, so it does not abstain at any threshold. This is the vague-text weakness recorded under step 3. Calibration cannot fix it: the cause is how Jev reads C10, not the threshold.
- Agreement here is accuracy only for these 30 labelled tenders.


## Step 5: router demo (2026-10-05)

Run with `python gebiz_graph.py --demo`. Jev (jev-1.13.0) picks the template; plain code fills the parameters. Router threshold 0.7 on the template probability; classification threshold 0.7. 12 questions: 9 answered, 3 abstained. Audit lines are in `router_log.jsonl` (git-ignored).

| # | Question (short) | Jev's choice (probability) | Outcome |
|---|---|---|---|
| 1 | Total awarded value FY2023 | M1_BY_FY (1.00) | Answered: S$21,682,674,098 by value |
| 2 | Housing and Development Board FY2024 | M1_BY_AGENCY_FY (1.00) | Answered: S$9,020,817,207 by value |
| 3 | Land Transport Authority FY2022 | M1_BY_AGENCY_FY (1.00) | Answered: S$5,575,621,106 by value |
| 4 | Top 10 suppliers FY2023 | M2_TOP_N_FY (0.99) | Answered: 31.2% of S$21,682,674,098 |
| 5 | Top 5 suppliers FY2025 | M2_TOP_N_FY (1.00) | Answered: 21.4% of S$30,882,176,691 |
| 6 | Spend by category FY2024 | M3_CATEGORY_SPEND_FY (0.96) | Answered: UNCLASSIFIED 8.4% of S$27,351,102,095 by value |
| 7 | FY2022 value that could be classified | M4_COVERAGE_FY (0.99) | Answered: 89.3% classified by value |
| 8 | FY2021 tenders classified, by count | M4_COVERAGE_COUNT_FY (0.98) | Answered: 87.2% (2,036 of 2,334) by count |
| 9 | Ministry of Education award, no year | M1_BY_AGENCY_FY (0.89) | Abstained: no fiscal year |
| 10 | How much was spent on IT? | M3_CATEGORY_SPEND_FY (0.87) | Abstained, but only because no fiscal year was given |
| 11 | Who are our best suppliers? | NO_DEFINED_METRIC (0.73) | Abstained: no defined metric |
| 12 | What was the total for FY2023? | M1_BY_FY (0.98) | Answered (expected abstention did not happen) |

Cross-checks: Q6 to Q8 equal the step 4 figures above (FY2022 89.3% by value, FY2021 87.2% by count, FY2024 91.6% classified). Q1 equals the M1 value verified against pandas in step 2.

### Surprises and limits

- **Q10 abstained for the wrong reason.** Jev chose M3 at 0.87 and gave `NO_DEFINED_METRIC` only 0.13. "How much was spent on IT in FY2024?" would probably be answered with the whole category table, although "spent" has no metric (M1 is awarded value, not cash spent). Not run, so this is an inference. Decision: left as it is and recorded here (PLAN.md, 2026-10-05). The router needs an explicit check for concepts the metric layer does not define.
- **Q12 did not abstain.** Jev read "total" as M1 at 0.98. That is a reasonable reading, so the expectation in the demo list was probably wrong. Wording and threshold were not changed.
- **Q11 was close:** `NO_DEFINED_METRIC` at 0.73, just above 0.7.
- **Two of the three intended abstentions** (Q9, Q11) abstained for the right reason; Q10 by luck; Q12 not at all. 12 questions show the mechanism works, not how often it works.
- Supplier questions are not supported: the router abstains if Jev picks `M1_BY_SUPPLIER_FY`. Untested on a real question.

## Repeatability check (2026-10-08)

Run with `python helpers/repeatability_check.py` (needs `TYPESAFE_API_KEY`, no Neo4j, about 84 Jev calls). Each input has three observations: the stored audit-log line (2026-10-04 for tenders, 2026-10-05 for router questions) and two fresh calls on 2026-10-08. Model `jev-1.13.0` throughout.

| Set | Inputs | Chosen option changed | 0.7 decision flipped | Largest change, chosen option's probability |
|---|---|---|---|---|
| Calibration tenders (classification) | 30 | 0 | 0 | 0.11 (25 of 30 moved by 0.02 or less) |
| Router demo questions | 12 | 0 | 0 | 0.05 (7 of 12 did not move) |

- The same input gave the same chosen option every time, on the same model version, over four days. Probabilities drift by a few hundredths, up to 0.11.
- **Limit of the check:** none of the 30 tenders sits near 0.7, so no flip could be seen. From the stored full-run probabilities, 239 of 12,052 tenders (2.0%) lie within 0.02 of 0.7, 657 (5.5%) within 0.05, and 1,446 (12.0%) within 0.11. Tenders in that band could land on the other side of the threshold if re-run. This is inferred from the stored probabilities; those tenders were not re-run.
- **What this means for the audit claim:** the audit log is the record of a decision. A re-run is a check on it, not a replacement. A different model version is not covered by this check.
- **Model version is stored** on every audit-log line and, by the write query in `gebiz_graph.py` (`WRITE_CLASSIFICATIONS`), on every `CLASSIFIED_AS` edge (`model`, `taxonomy_version`). The code was read; the live database was not queried.
- **For the router limits:** probability noise of 0.05 to 0.11 is the same size as the gaps a margin rule would use (Q11 sat at 0.73 against 0.7). Tuning such a rule on 12 questions would fit noise.
