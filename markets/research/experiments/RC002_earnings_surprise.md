# RC002 — Earnings Surprise / PEAD (Program B, Sprint 1)

**Status:** CLOSED · **Verdict:** directional lead, underpowered · **Date:** 2026-06-29 · **Script:** `experiments/rc002_earnings_surprise.py`

## Question
Does a naive YoY earnings surprise (this quarter's diluted EPS vs the same quarter last year) predict
post-filing drift? Event = SEC `filed` date (PIT). Free data: no analyst estimates → naive expectation.

## Method
Cached SEC CompanyFacts (Program A dataset, no new ingestion). Quarterly EPS span-filtered to 3-month
periods. Surprise rank-standardized. Forward drift = 42d return from the trading day on/after filing.
Cross-sectional rank-IC per calendar month; significance on NON-overlapping months (embargo discipline).

## Result
- events 359 · names 68 · months 23
- monthly IC +0.150 (IR +1.86, n=13)
- non-overlap IC +0.108 (IR +0.99, n=8)

## Verdict
directional lead, underpowered. Directional lead; insufficient power to promote (74-name SEC overlap, ~2y).
Honest scope: naive expectation is weaker than analyst-estimate surprise; a null is "no evidence with this
proxy/power", not "PEAD is dead." Next in Program B: RC003 guidance, RC004 revisions.
