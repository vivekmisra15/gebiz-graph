# Phase 1 thesis note: letting a model select, not invent

*Private self-study note. Written after build steps 1 to 6, October 2026. Figures come from RESULTS.md and PLAN.md; check those for detail.*

## What this project is, and what it tries to show

The project turns Singapore's public government procurement awards (GeBIZ open data, 12,052 tenders, FY2021 to FY2025) into a Neo4j graph with a small governed layer on top: ten categories and four metrics, all written by a human.

The thesis fits in one sentence. In an audited setting, a model should not write its own queries or invent its own definitions. It should select among definitions humans have written, record how sure it was, and abstain when it is not sure.

Everything else in the build exists to test that sentence. The model does two jobs, both of them selections from a closed list: it files each tender under one of the ten categories, and it picks which of the fixed queries answers a typed question. Each selection is stored with its probability, so someone can later ask why an answer came out the way it did.

## What shaped the design

Four considerations did most of the work.

**Auditability beats flexibility.** A system that generates Cypher on demand can answer anything, but nobody can say in advance what it will run. Fixed, parameterised templates give up that flexibility. In return, every possible query can be read, reviewed and tested before anyone uses it. Parameterisation is also the precondition for access control later, which is why the rule is "never build Cypher by string concatenation".

**Honest numbers.** The data is awards only. "Awarded value" is contract value at the award date, not cash spent. Multi-year contracts land entirely in their award year, and the median contract is S$178K while the maximum is S$1.8B, so averages mislead and are never reported. The metric definitions say all this in plain words, so the caveats travel with the number.

**Small scope.** The build budget was nine hours, with one script, public data only and no model maths. Anything that did not serve the thesis (a UI, extra datasets, an evaluation benchmark) was flagged instead of built.

**Verification before building on a result.** Each step had a check that had to pass before the next began. The metric layer was checked against a plain pandas calculation, to the dollar.

## Decisions and trade-offs, step by step

**Loader (step 1).** Profiling the data first drove the rules. The 639 "Awarded to No Suppliers" rows create a Tender but no Supplier and no edge, because "Unknown" is not a supplier. Supplier names get deterministic cleanup only (case, punctuation, company suffixes). Malaysian "SDN BHD" firms stay separate from Singapore "PTE LTD" firms with the same trading name. The trade-off: some real duplicates survive, and that is accepted because fuzzy matching is entity resolution, which is out of scope. Where cleanup merges two names within one tender, the amounts are summed.

**Metric layer (step 2).** The four metrics (awarded value, supplier concentration, category spend, classification coverage) are stored as Metric nodes and fixed Cypher templates. Slices such as agency or fiscal year are dimensions, not new metrics, so there are seven templates but four definitions. The trade-off: adding a question means adding a reviewed template, not just asking. That friction is deliberate.

**Classification (step 3).** The taxonomy is human-authored and was frozen as v1.0 after labelling 150 tenders by hand. The model cannot add categories. Changing one means a new version number, so each classification records which taxonomy it used. A keyword-rule fallback sits behind the same function, so the script runs without an API key and gives Jev something to be compared against. One surprise: coverage is higher by value (92.8%) than by count (87.2%), because large contracts are described more clearly than small ones.

**Calibration (step 4).** The threshold was set at 0.7 on `probability` using 30 hand labels, then left alone. Jev was right on 27 of 30. Probability and confidence behaved alike on this set, so the simpler number was kept. A higher threshold (0.9) would have removed the last two errors, but those rest on two arguable boundary cases, so tuning to them would be fitting noise. It would also abstain on about a quarter of tenders. The trade-off is explicit: a higher threshold buys accuracy with coverage. Thirty labels cannot place a threshold precisely, and since the taxonomy's boundary rules came from the same pool, 90% accuracy is probably an upper bound.

**Router (step 5).** One Jev call chooses among the seven templates plus a "no defined metric" option. Plain code, not the model, fills the parameters (fiscal year, agency, top N). That keeps the model to selection and makes a missing parameter easy to detect. It abstains if the template probability is under 0.7, if a parameter is missing, or if the question asks for a slice no template has. Supplier-name matching was deliberately not built: there are 6,151 suppliers against Jev's limit of 255 options, and matching them is entity resolution. A Claude model is the intended later tool for that and for smarter parameter extraction.

**Audit log (step 6).** Every classification and every router call writes one line with the probability distribution, parameters, result and abstention reason. Without this the thesis is only a claim.

## Where Neo4j and the graph fit

Honest answer: the graph is the substrate, not the star. The metrics here are mostly sums and groupings that a relational database would also handle. No graph algorithm is used, and none was meant to be.

What the graph does give is a natural home for the governance. The domain is a handful of entities and relationships (Agency issues Tender, Tender is awarded to Supplier, Tender is classified as Category). The `CLASSIFIED_AS` relationship carries the audit facts (probability, confidence, model, taxonomy version, time) on the edge itself, so provenance sits next to the thing it describes. The Metric nodes keep the definitions in the same store as the data they govern. Uniqueness constraints give the loader safe re-runs. And Cypher's parameter mechanism is exactly what the "templates only" rule needs.

The caution for later phases: choose a graph when relationships are the question (paths, shared suppliers, ownership chains), not because the data can be drawn as one. Here the relationships are shallow, so the graph's payoff is tidiness and governance, not insight.

## Where Jev fits

Jev returns typed answers with probabilities (a choice from a closed list, a score, or a boolean), not free text. That is the property the thesis needs: its output is already a selection with a number attached, so it drops into an audit trail without translation. Output tokens are free and input is billed per token, so short, readable payloads matter; classifying all 12,052 tenders took about 7.6 million input tokens, about US$0.32.

It performed well on the one job it was given: 19 of 20 in the first trial against hand labels where the keyword rules got 10, and 27 of 30 in calibration. It is also well matched to the abstention idea, because low probability is a usable signal for "unclassified".

## What this means for using Jev elsewhere

**It is strongest** where the answer is a pick from a fixed, human-owned list, the text is readable, and being wrong has a cost that a threshold can manage. Classification into a controlled vocabulary, routing to a fixed set of actions and triage are the obvious fits.

**Three limits showed up, and each is a warning for other uses.**

1. *Confident on garbage.* Five tenders with boilerplate-only text ("refer to the attached documents") were all placed in "Other Services" at 0.92 to 0.99. The category was defined as "none of the others", and the model read empty text as fitting none. The lesson: a probability measures how well the input fits an option, not whether the input is meaningful. A catch-all category will absorb nonsense with confidence.
2. *Undefined concepts get routed to the nearest option.* "How much was spent on IT?" went to category spend at 0.87, with "no defined metric" at only 0.13. It abstained only because the question had no year. Closed-set routers need an explicit check for concepts the definitions do not cover, and that check should not rely on the model's probability alone.
3. *Probability is not ambiguity.* "What was the total for FY2023?" got 0.98 for one template. The model picked a reasonable reading confidently. High probability on one option does not mean the question had one meaning.

**The bigger lesson** is about where the control sits. The model's confidence is one input; the safeguards are the closed lists, the human-written definitions, the threshold, the parameter checks and the log. Where those exist, a confident model is usable. Where they do not, confidence is just a number.

**For different scenarios**, scope questions to ask first: Is the option list small and stable enough to be owned by a person (255 is a hard limit, and it stops being governable well before that)? Does the text carry enough information to choose? What is the cost of a wrong confident answer versus an abstention? And what should happen to the abstentions: who reviews them? Phase 1 only counted them, and the review step is where a real deployment would spend its effort.

## Caveats to remember

- The 90% accuracy figure is from 30 labels drawn from the pool the taxonomy was shaped on. Treat it as optimistic.
- The router demo is twelve questions: nine answered, three abstained, and one of the three abstained for the wrong reason. It shows the mechanism works, not how often.
- Value coverage is dominated by a few very large contracts, so a handful of tenders can move the percentages.
- Awarded value is not spend. Every number in the project inherits that.
