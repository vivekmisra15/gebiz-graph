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
