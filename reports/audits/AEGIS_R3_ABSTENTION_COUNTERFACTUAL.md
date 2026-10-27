# AEGIS R3 — Abstention Counterfactual
**2026-10-27 · read-only research · no model created · no disposition changed · R3 remains research-only**

Question: R3 abstained on every observation it ever made. R2 participated.
**On identical opportunities, did abstaining beat participating?**

---

## 1 · Answer

**Yes, on the resolved admission cohort — by +2.72pp per trade. And this is
not evidence of skill.**

| On the SAME 112 resolved opportunities | Mean/trade | Sum |
|---|---|---|
| 1. **PARTICIPATE** (R2 actual) | **−2.722%** | −304.8pp |
| 2. **ABSTAIN** (R3 actual · cash · 0%) | **+0.000%** | 0.0pp |
| 3. **BENCHMARK** (NIFTY, entry→exit matched) | **−1.514%** | −169.5pp |

```
abstain  −  participate            = +2.722 pp/trade
abstain  −  benchmark              = +1.514 pp/trade
participate − benchmark (alpha)    = -1.208 pp/trade
```

Abstaining beat participating, and also beat the benchmark — because the
benchmark itself fell over these windows. Holding cash beat a falling market.

**Coverage is 0%.** R3 took no position on anything, ever. A policy of
universal abstention mechanically "beats" any losing strategy and would
equally have "lost to" any winning one. It has no discriminating power
because it never discriminates. **This result says R2 lost money. It does
not say R3 has predictive skill.**

---

## 2 · Matched universe

The join had to be constructed externally — see §5 for the fields that made
it necessary.

| | |
|---|---|
| R3 observations total | 1,724 (94 tickers × 38 dates, 2026-09-08 → 2026-10-27) |
| Duplicates | **0** — `(ticker, as_of)` is unique across all 1,724 |
| of which **admission** decisions (`r2_signal == NEW`) | **143** |
| matched → RESOLVED (realized exit) | **116** |
| matched → UNRESOLVED (still open) | **27** |
| **unmatched** | **0** |
| resolved with a computable benchmark window | **112** (4 lack ≥2 index bars) |

**Only `r2_signal == NEW` is a valid comparison universe.** The other 1,581
observations are `ACTIVE+` (1,557) and `ACTIVE` (24) — positions *already
held*. Abstaining on an existing holding is not an entry decision, and
counting them would inflate the sample ~12× with non-decisions.

Evaluation window: entry 2026-09-08 → 2026-10-27. Horizon: each position's
own actual holding period (entry→exit), not a fixed horizon — so the
benchmark leg is matched position-by-position over the identical window.

**Is this the same cohort as the −2.51% R2 figure quoted earlier? No.**
That figure is all 145 India realized exits. This cohort is the 116 that R3
observed as NEW, whose participate mean is **−2.779%**. Different
denominators; reported separately rather than conflated.

---

## 3 · Avoided losses vs sacrificed winners

On the 116 resolved:

| | Trades | Sum |
|---|---|---|
| **Avoided losses** | 101 | **+387.8pp** |
| **Sacrificed winners** | 15 | **−65.4pp** |
| **Net** | 116 | **+322.4pp** |

Worst sacrificed winner: **SUNTV +32.47%**. Worst avoided loss:
**−12.43%**.

So abstention gave up 15 winners to avoid 101 losers — a 6.7:1 ratio. That
ratio is a property of **R2's 13% win rate on this cohort**, not of any
judgement R3 exercised. R3 did not select which to avoid; it avoided all of
them.

---

## 4 · Unresolved positions — reported separately, never as zero

| | n | Mean mark | Sum | Green |
|---|---|---|---|---|
| Still open | **27** | **+4.638%** | +125.2pp | 25 (93%) |

These are **unrealized marks on a survivor subset**, not outcomes. The
forensic report established that this cohort's closed members ran at 12%
green while its open members show 93% — the gap is survivorship, because
losers exit and stop being visible.

**If all 27 eventually realize near their current marks, the abstention
advantage narrows by roughly 125pp** — from +322.4pp to ~+197pp, still
favouring abstention but materially less. They are not counted in §1.

---

## 5 · Fields that are missing, and why it matters

The R3 ledger **cannot support this analysis on its own**:

| Field | Coverage | Consequence |
|---|---|---|
| `outcome` | **0 / 1,724** | R3 records no outcome for any observation |
| `position_id` | **0 / 1,724** | no stable key to join to the lifecycle |
| entry/exit price | absent | no return computable from the ledger |
| `r2_confidence_pct` | 1,663 / 1,724 | 61 observations lack it |

The join was therefore reconstructed on `(ticker, as_of) == (ticker,
entry_date)`. That works here (0 unmatched) but it is **inference, not a
recorded linkage** — if two admissions of the same ticker shared a date the
key would be ambiguous.

**This is the single highest-value R3 fix** and it is pure engineering: give
each observation a `position_id` and record its outcome. Without it, every
future R3 evaluation has to re-derive the join.

---

## 6 · Limitations

1. **Coverage 0%.** The decisive one. See §1.
2. **No costs.** Participating incurs costs, abstaining does not — modelling
   them would *widen* the gap, so the direction is safe but the magnitude is
   understated for participation.
3. **Opportunity cost not modelled.** "Abstain" is treated as cash at 0%.
   Capital could have earned a risk-free rate, or been deployed elsewhere.
4. **Overlapping and dependent observations.** 116 trades across ~30 entry
   dates in one falling regime. These are **not** 116 independent
   observations; no significance is claimed and none should be read in.
5. **Equal-weighted only.** Capital weighting is impossible —
   `portfolio_history.parquet` holds dated weights only to 2026-09-03.
6. **One regime, one market.** India, 2026-09-08 → 2026-10-27, NIFTY falling.
   Abstention's advantage here is partly *because* the market fell.
7. **Post-hoc universe.** The NEW filter was chosen on methodological
   grounds, but it was chosen after seeing the data.

---

## 7 · What this does and does not license

**Does NOT license:**
- any claim that R3 has predictive skill
- promoting any specialist, or changing any disposition
- treating 100% abstention as a validated policy
- inferring that "AEGIS should stop trading"

**Does establish:**
- R2's admission cohort lost **−2.72%/trade** against a benchmark that lost
  −1.51% — **alpha −1.21pp/trade** on identical windows
- the join is feasible and the matched sample is complete (0 unmatched)
- R3's ledger lacks `outcome` and `position_id`, which blocks reuse

---

## 8 · Recommended next research question

Abstention's advantage here is indistinguishable from "cash beat a falling
market." The question that *would* carry information:

> **Does R3's per-observation `abstain_probability` / `take_probability`
> rank outcomes?** R3 records these on all 1,724 observations but has never
> acted on them. If the subset R3 was *least* inclined to abstain on
> outperformed the subset it was *most* inclined to abstain on, that is
> discriminating power — measurable today, on existing data, with no new
> model and no disposition change.

That converts "R3 abstained on everything" from a non-result into a testable
ranking hypothesis, and it is the same method (`rank_separation`) already
applied to `ensemble_score`.

**Prerequisite:** add `position_id` and `outcome` to the R3 ledger (§5).

---

## 9 · Reproduction

```
# matched universe + counterfactual
python -W ignore -c "<§2-§4 blocks>"
#   reads reports/research/r3/shadow/ledger_india.jsonl
#         reports/context/canonical_lifecycle_india.json
#         data/raw/india/NSEI_D1.parquet
```

Ledger as of 2026-10-27 (1,724 rows). Lifecycle asof 2026-10-27.
Benchmark close-to-close, entry+1 → exit.
