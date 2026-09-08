# AEGIS · AI RESEARCH EVIDENCE STREAM

**Family:** R3 Research & Decision Intelligence Layer
**Status:** RESEARCH ONLY · no R1/R2 change · no R3 promotion
**Opened:** 2026-09-08
**Governing principle:** *AI is an evidence generator and probabilistic
decision-support layer, not an authority.*

This is a continuous ledger, not a report. Numbers that were later
invalidated are **preserved as audit history and marked**, never deleted —
the record that something was once believed is itself evidence.

---

## 0 · Standing production restrictions

| Restriction | State |
|---|---|
| R2 confidence thresholds | UNCHANGED |
| R2 ensemble weights / ranking / exits | UNCHANGED |
| Momentum thresholds | UNCHANGED |
| R1 advisory semantics | UNCHANGED |
| Dynamic stop / target logic | UNCHANGED |
| R3 promotion | NONE |
| Engine writes from any AI module | NONE |

Every module below reads artifacts and writes one research file. The
discovery layer is source-tested to touch no engine
(`test_discovery_layer_writes_to_no_engine`).

---

## 0.1 · 🔒 THE AI RESEARCH CONTRACT (locked 2026-09-08)

> **No AI technique is considered successful because it improves
> predictive metrics alone. A technique must demonstrate incremental
> decision value over the existing R2 candidate pool on untouched data,
> survive predefined multiple-testing correction, and remain interpretable
> with respect to the available PIT substrate.**

This exists to stop the project drifting into *"try another model because
the previous model didn't work."* AUC is a diagnostic, never a result.

### The three kill switches

| Trigger | Action |
|---|---|
| **Leakage** | kill the RESULT |
| **Tautological target** | kill the RESULT |
| **No incremental R2 value** | kill the MODEL |

All three have already fired in this ledger:
- *leakage* → Wave 1C sequence models (calendar), Wave 1D (split contamination)
- *tautology* → Wave 1D R-multiple targets (`stop_distance` alone = 0.853)
- *no incremental value* → Wave 1D T4 `stop_hit_10d`

### The strategic thesis (locked)

**R2 selects the candidate. R3 estimates whether that candidate is likely
to survive, reach useful payoff, or suffer severe loss.**

```
R2 BUY -> R3 risk/survival intelligence -> calibrated meta-label
       -> research-only decision overlay
```

**NOT** `R3 -> independent BUY -> compete with R2`. The empirical basis:
return prediction is poor, severe-loss classification shows real structure,
lagged/trajectory variables beat contemporaneous levels, sequence models
died under adversarial validation, and Wave 1D's spectacular AUCs were
successfully destroyed by it.

### The loop

```
substrate -> descriptive -> statistical -> temporal -> model
          -> adversarial validation -> OOS -> calibration
          -> economic value -> incremental R2 value
          -> evidence ledger -> R3 knowledge -> repeat
```

---

## 1 · Substrate reality (the binding constraint)

| | India | USA |
|---|--:|--:|
| Cohort rows (fwd_10d) | 456 | 1,082 |
| Distinct tickers | 37 | 495 |
| Prediction dates | 15 | 7 |
| **Effective independent units** | **46** | **495** |
| Exit episodes with a stop | 547 | 79 |
| Entry-price coverage (pre-repair) | 100% | 12.4% |
| Sector | current-time only, **not PIT** | same |
| Regime | `unknown` on all 19 observations | same |
| Market cap | **no source in repository** | same |
| fwd_20d | 116 rows | **0 · not matured** |

**Rows are not evidence.** 456 India rows come from 37 names with
overlapping 10-day windows. A cell once reported as *"61 observations, 0%
winners"* was **6 tickers**, ITC (29) and IRCTC (20) supplying 80%.

---

## 2 · Wave log

### Wave 1A — Entry substrate reconstruction · ✅ ACCEPTED

USA `entry_price_at_pred` **12.4% → 100.0%** (+1,013 rows), 0 unresolvable.
Diagnosed as a **write-path** defect, not missing data: the resolver
returned a price for every ticker tested (CPAY 406.16, TGT 151.13, LH
321.73, RTX 223.12). Coverage gap was specific to USA R2 (8.2%) while USA
R1 was 86.1% and India ~100%.

**Stops deliberately NOT backfilled.** Entry price is an observable fact;
a stop is a decision, and a never-opened candidate never had one.
Fabricating 1,013 stops would let R3-G answer its own question.
Pinned by `test_stops_are_never_fabricated_for_unopened_candidates`.

### Wave 1B — Exit hazard / survival · ✅ ACCEPTED (with caveats)

Daily paths reconstructed from bars; every event timed in R-multiples.

| | India | USA |
|---|--:|--:|
| Episodes | 547 | 79 |
| Stop-hit | 30.7% (median day 8) | 20.3% (median day 5) |
| Reached +1R | 29.4% (median day **1**) | 32.9% (median day 4) |
| P(+1R before stop) | 29.4% | 30.4% |
| Reversed | 18.5% | 19.0% |
| **Mean peak → final** | **+1.573R → +0.274R** | **+2.003R → −1.970R** |

**Headline: 83% of peak favourable excursion is given back (India); USA
peaks at +2R and finishes at −2R.**

Hazard structure (India): the +1R hazard is **17.55% on day 1**, 2.66% on
day 2, **0.38% by day 10 and 0.00% after day 15**. Stop hazard is bimodal —
6.4% day 1, then a second zone at days 10–15. *After ~day 3 a position has
almost no remaining probability of reaching its first R while stop risk is
still ahead of it.*

Model vs baselines — the model earns its place on **one target of three**:

| Target | Model | Stop-dist | Volatility | Beats? |
|---|--:|--:|--:|---|
| India stop_hit | 0.580 | **0.656** | 0.515 | ❌ |
| India 1R-before-stop | **0.768** | 0.720 | 0.735 | ✅ |
| India reversed | 0.750 | 0.629 | **0.797** | ❌ |
| USA 1R-before-stop | **0.757** | 0.655 | 0.711 | ✅ |

**Stop-hit is better predicted by "how wide is the stop". Reversal is just
volatility.**

### Wave 1C — TCN / GRU / Transformer · ❌ REJECTED

torch 2.12.1. Tiny models by design (TCN 649 params, GRU 1,121,
Transformer 2,337) against 547 episodes. Causal by construction — left-
padded dilated convolutions, causal attention mask.

| Target | Split | Baseline | LightGBM | TCN | GRU | Transformer |
|---|---|--:|--:|--:|--:|--:|
| P_1R_before_stop | ticker | 0.735 | 0.842 | **0.892** | 0.871 | 0.852 |
| | **date** | 0.752 | **0.911** | 0.879 | 0.867 | 0.878 |
| P_2R_before_stop | ticker | 0.832 | 0.840 | **0.924** | 0.890 | 0.895 |
| | **date** | 0.845 | **0.891** | 0.845 | 0.825 | 0.867 |
| reversal_20d | ticker | 0.797 | 0.869 | 0.901 | **0.905** | 0.874 |
| | **date** | 0.819 | **0.926** | 0.885 | 0.888 | 0.883 |

**Every sequence advantage inverts under date-disjoint folds.** The
networks were reading the calendar. Two nominal survivors (`tcn`/`gru` on
`stop_hit_1d`) sit on the thinnest target (6.4% event rate) out of **100
counted comparisons** — expected noise.

**VERDICT: killed.** Not revisited until the cohort has materially more
dates; the constraint was substrate, not architecture.

USA correctly refused: 79 episodes < 200 minimum, 21.5% top-date share.

### Wave 1D — LightGBM incremental-value validation · ⚠️ INVALIDATED

**These numbers are audit history. They are NOT evidence.**

| Target | walk-forward | ticker-disjoint | date-disjoint |
|---|--:|--:|--:|
| T1 P(+1R before stop) | 0.928 | 0.768 | 0.974 |
| T2 P(+2R before stop) | **1.000** | 0.942 | 0.988 |
| T3 reversal_20d | 0.846 | 0.750 | 0.958 |
| T4 stop_hit_10d | 0.675 | 0.620 | 0.942 |

An AUC of 1.000 is a symptom, not a finding. Three confounds found:

1. **R-multiple tautology.** `R = stop_distance_pct` is the *denominator*
   of the target. `stop_distance_pct` **alone, no model**, scores AUC
   **0.853** on P(+2R) and **0.700** on P(+1R). Ablation: dropping the risk
   group costs −0.312 on T2.
2. **Half the stops are a rendering default.** India **282/547 (51.6%)**
   and USA **35/79 (44.3%)** have `stop_distance == exactly 5.00%` —
   `detail_xlsx`'s documented fallback for non-actionable rows. Default-stop
   rows reached +1R **34.4%** vs **24.2%** for real-stop rows, and the
   ordering **inverts** on +2R.
3. **Neither split controls both axes.** Ticker-disjoint shares dates;
   date-disjoint shares tickers. Hence 0.768 vs 0.974 on one target.

Surviving from 1D: **T4 stop_hit_10d correctly FAILED** the economic test
(`NO INCREMENTAL VALUE`, top bucket worse than unfiltered) — consistent
with 1B, and trustworthy because nothing in the setup favoured it.

### Wave 1D-C — corrected validator · ⚠️ PARTIAL

All three confounds addressed: **joint ticker × date holdout** (nothing
shared on either axis), **real-stop / default-stop segmentation**,
**absolute-return targets** with no stop term, and `stop_distance_pct`
removed from the feature set.

| Cohort | Target | AUC | Baseline* | n |
|---|---|--:|--:|--:|
| DEFAULT_STOP | hit_2R_before_stop | 0.905 | 0.786 | 282 |
| REAL_STOP | hit_2R_before_stop | 0.887 | 0.801 | 265 |
| ALL | hit_2R_before_stop | 0.878 | 0.765 | 547 |
| REAL_STOP | hit_1R_before_stop | 0.838 | 0.687 | 265 |
| ALL | hit_1R_before_stop | 0.746 | 0.741 | 547 |

\* volatility baseline scored `max(auc, 1−auc)` — a heuristic predicting
inversely is still a heuristic. Scoring it directionally would have let the
model "beat" a baseline stronger than itself.

**Critically: NO absolute-return target survives.** `abs_3_before_-3`,
`abs_5_before_-5`, `abs_10_before_-5` all fail against the corrected
baseline. Since the absolute targets are the ones with no stop term, the
surviving signal may **still** be an artefact of the R definition.

**USA: NO SIGNAL SURVIVES** the joint holdout (79 episodes).

### Wave 1D-E — absolute-target resolution · ❌ MODEL KILLED

**The question:** *does R3 still identify better R2 candidates when the
target cannot mathematically depend on stop width?*

**The answer is NO.**

Absolute races need no stop, which released the full cohort — India 509
rows (vs 265 stop-bearing episodes), USA 1,044 (vs 44). `stop_distance_pct`
absent from the feature contract; joint ticker × date holdout; three
directionless baselines; BH-FDR over the predefined family.

Only **2 of 15** target/market pairs beat their best baseline — and both
fail the economic test:

| | pool return | pool hit | top-20% return | top-20% hit | lift |
|---|--:|--:|--:|--:|---|
| India `5%/-5% @5d` | −1.48% | 7.7% | **−2.16%** | 23.1% | **−0.68pp / +15.4pp** |
| USA `3%/-3% @5d` | +0.282% | 28.9% | **−0.001%** | 52.0% | **−0.28pp / +23.1pp** |

**The model reliably picks names that more often touch +X% before −X%, and
those names have WORSE average returns.** Hit rate rises 15–23pp while
return falls. It is selecting frequent small winners that give more back —
exactly consistent with Wave 1B's peak→final giveback (+1.573R → +0.274R).

Worse, the signal inverts by horizon: India scores 0.778 at 5d and **0.358
at 10d**; `race_3_3_10d` is **0.465** — actively anti-predictive. A real
edge does not flip sign across adjacent horizons.

The trivial baselines (volatility / momentum / trend, scored
`max(auc,1−auc)`) run **0.60–0.83** and mostly win outright.

**KILL SWITCH FIRED: "no incremental R2 value → kill the MODEL."**
The R3-G exit-intelligence edge is **not supported**. Wave 1D-C's
surviving R-multiple result is now best explained as an artefact of the R
definition, since it does not reproduce on any stop-free target.

### 🔒 R3-G PREDICTIVE BRANCH · FROZEN 2026-09-08

No further LightGBM / TCN / GRU / Transformer variants on this substrate.
The validator has demonstrated why this branch must not be endlessly
optimised: five waves, five different failure modes, zero surviving edge.

**Preserve the finding apart from the killed model.** The durable result is
NOT "R3 can predict returns". It is:

> **Entry selection and severe-loss avoidance may contain structure, but
> this dataset cannot demonstrate a promotion-grade predictive edge.**

And even that is research-grade, not production-grade.

**The branch reopens only when the substrate grows — and then as a
different question:** not `market -> R3 -> BUY`, but

```
R2 candidate -> R3 evidence / risk assessment -> ACCEPT | DEPRIORITISE | RESEARCH
```

> *Among stocks R2 already wants, can R3 reliably identify candidates that
> should be avoided because of elevated severe-loss / failure risk?*

That is materially different from forecasting returns, and it is the only
form in which this branch may return.

**The five-wave history is permanent.** It is not to be rewritten as "AI
didn't work". Each wave killed a distinct failure mode:
`1A reconstruction -> 1B hazard -> 1C sequence adversarial kill ->
1D validator -> 1D-E stop-free falsification`. That is the contract
working.

---

### Wave 2A — Prequential evaluation · 🟡 ACCUMULATING

Append-only ledger: predict → record → score later, never re-cut. India 15
dates → 13 predictions (443 skipped, insufficient matured training rows);
USA 7 dates → 0 (1,082 skipped). Both correctly refuse to issue a verdict
below 50 scored predictions. This is the one evaluation that cannot be
tuned after the fact, and it accrues one honest observation per day.

### Wave 2B — Fundamental substrate · ✅ ACCEPTED

India 45 tickers / 265 periods / 1,086 earnings rows / H2-computable 100%.
USA 215 tickers / 1,368 periods and still accumulating toward ~497.

The publication lag is applied at **read** time, not fetch time, so
30/45/60-day sensitivity is testable without re-fetching anything. Rows
carrying a real earnings-calendar date (`PIT_VERIFIED`) ignore the lag
entirely — a fact does not move because an assumption changed.

### Wave 2C — Seven-filter research · ⚠️ METHODOLOGICAL RESULT · MODEL KILLED

**Five of seven filters are computable.** No PIT share count exists, so
there is no P/E; no governance dataset exists at all. The report states
this on every row rather than quietly scoring five and calling it seven.

**The primary result is not about fundamentals. It is about the unit of
analysis.**

Fundamentals are quarterly. Across a one-month cohort a name's fundamental
state does not change, so every dimension tested is not a time-varying
signal but a **label attached to a set of names**. The within-ticker
pairing proved it directly: *zero* India names carried both states.

That single fact destroys the headline finding:

| India · `roe_rising` | value |
|---|---|
| pooled row-level delta | **−2.018 pp** |
| row-level Mann-Whitney p | **0.000** |
| rows claimed as evidence | 333 |
| units that actually vary | **35** |
| ticker-level delta | **−0.712 pp** |
| ticker-level p | **0.386** |
| survives BH-FDR | **no** |

**0 of 4 India dimensions survive** once significance is computed on the
units that vary. USA: **0 of 6**. Every "significant" fundamental finding
in this cohort was an artefact of counting repeated rows of unchanging
names as independent observations.

**Dimension 10 — incremental value over R2 (the non-negotiable test).**

| | India | USA |
|---|---|---|
| rows / severe-loss events / event names | 333 / 33 / 13 | 490 / 49 / 28 |
| AUC · R2 features only | — | 0.7458 |
| AUC · R2 + fundamentals | — | 0.7596 |
| delta AUC | — | **+0.0138** |
| ticker-bootstrap 95% CI | — | **[−0.0741, +0.1048]** |
| verdict | **REFUSED** (below the event gate) | **KILL MODEL** |

The CI is roughly thirteen times wider than the point estimate. The third
kill switch fires: fundamentals demonstrate **no incremental value over
what R2 already sees**. The bootstrap resamples *tickers*, not rows, for
the same reason the significance tests had to move to ticker units.

**PIT lag sensitivity (30/45/60 days), built in rather than bolted on.**
Sample statistics necessarily move with the lag — a longer lag admits
fewer rows, so it is a different sample. Only a **sign flip** shows a
conclusion depending on the assumption. India: `leverage_falling` flips
(+0.279 → −0.025 → −0.022) and is therefore not a finding at all. USA:
`positive_surprise` flips. All other dimensions hold their sign, so
whatever they say, they do not say it because of the 45-day guess.

**The horizon mismatch, stated plainly.** The seven filters are a
multi-year ownership thesis; this cohort measures ten trading days. USA
shows outcomes falling monotonically as more filters pass (0 passed
+1.34% → 5 passed −1.22%). That is **not** evidence the filters are
wrong. It is evidence they are being asked a question they were never
built to answer, in a window dominated by momentum and flow. The report
carries this caveat inline so the number cannot be quoted without it.

**Not promoted. No threshold proposed. No production rule.** Reopens when
the cohort spans multiple earnings dates per name — the condition that
makes fundamentals a variable rather than a label.

### 🔒 R3 AI PROGRAMME · FROZEN 2026-09-08 · `R3_AI_RESEARCH_COMPLETE = TRUE`

The finite AI programme ran all eleven intelligence classes to a final
disposition. **Zero reached VALIDATED. Zero reached CONDITIONAL.**

| Class | Disposition | Why |
|---|---|---|
| R3-A Descriptive | DESCRIPTIVE_ONLY | answered its question; no decision claim was ever made from it |
| R3-B Statistical | RESEARCH_ONLY | confidence effect is largely ticker mix; 0.55 floor untouched |
| R3-C Temporal | INSUFFICIENT_SUBSTRATE | sequence models stay REJECTED; prequential ledger correctly refuses below 50 scored |
| R3-D Forecasting | INSUFFICIENT_SUBSTRATE | history exists, but the decision cohort cannot price a forecast |
| R3-E Fundamental | REJECTED | substrate ACCEPTED and retained; the overlay is rejected |
| R3-F Market/Sector | INSUFFICIENT_SUBSTRATE | USA "sector" is `Large-Cap` on 96.5% of rows; regime null everywhere |
| R3-G Risk/Exit | FROZEN | Wave 1D INVALIDATED, 1D-E REJECTED, both preserved |
| R3-H Unsupervised | DESCRIPTIVE_ONLY | 6/6 lanes die under a ticker-block permutation |
| R3-I Intraday | BLOCKED | no intraday bars exist on disk |
| R3-J Calibration | RESEARCH_ONLY | built and measured; nothing survived to calibrate |
| R3-K Decision synthesis | INSUFFICIENT_SUBSTRATE | no validated specialist exists to put in a committee |

**The binding constraint is dates, not models.**

| | rows | names | dates | ticker units | **date units** |
|---|---|---|---|---|---|
| India | 361 | 37 | 15 | 46 | **2** |
| USA | 1,040 | 495 | 7 | 495 | **1** |

USA looks like the rich market — 495 names, VALIDATION_CANDIDATE tier on
ticker units. It is not. **93.5% of its rows fall on 2026-08-11 and
2026-08-12**, two consecutive mornings whose 10-day forward windows overlap
by nine days. That is 495 names experiencing *one* market move. Ticker-
disjoint folds are structurally blind to this: every fold contains both
dates, so a model can score well on unseen *names* while having seen
exactly one realisation of the market.

**This matters because it nearly produced a false positive.** Before the
single-episode gate existed, the USA meta-label reported logistic AUC
**0.6079**, ECE 0.029, decision value **+1.57 pp** with a ticker-bootstrap
CI of **[0.785, 2.659]** excluding zero, severe-loss rate 10.0% → 6.0%, and
survived every adversarial perturbation (worst ΔAUC −0.0118). By every gate
in place at that moment it passed. It is recorded here permanently as **a
description of two mornings in August, not evidence**, so the number is
never re-quoted as a result.

**Method corrections this programme forced:**

1. **Ticker-block permutation.** India's technical clustering read p=0.013
   under a row-level null and lost it completely once whole names were
   permuted together — the same defect Wave 2C found at row level.
2. **Two unit counts, always.** Ticker units bound cross-sectional claims;
   date units bound temporal ones. Quoting the larger is how a thin cohort
   looks rich.
3. **Coverage before imputation.** India carries operating cash flow on 2%
   of rows. Requiring all eight fundamental features left 9 usable rows of
   361; dropping the feature is honest, imputing it would invent a
   fundamental state that was never observed.
4. **Simplest rung wins ties.** A model within 0.02 AUC of the best loses
   to the simpler one. Complexity must earn its place.

**Governance audit: 6/6 PASS.** R3 isolation enforced by reading the
sources, not asserted. R2 production diff zero. All negative results
preserved.

**R3_DECISION_v1 contract is DEFINED but NOT ACTIVE** — shaped now so it
cannot be renegotiated later under pressure from a result.

**After freeze:** evidence refresh, recalibration, drift detection,
monitoring. No new AI architecture search. Reopens only on 50+ scored
prequential predictions, 10+ populated dates per market, real sector and
regime columns, persisted intraday bars, or an authorised new question.

## 3 · Current AI readiness

| Layer | State |
|---|---|
| LightGBM tabular | **no validated edge** · killed on absolute targets (Wave 1D-E) |
| Sequence models (TCN/GRU/Transformer) | **killed** |
| Descriptive / statistical / temporal | built, running |
| Hazard / survival | built · descriptive value only · no predictive edge |
| Deep learning beyond the above | **not justified by substrate** |
| RAG-as-predictor | not started · needs PIT document store |
| Graph / KG ML | blocked · no historical community substrate |
| RL exit policy | not started · needs environment + simulator |

**Promotion-eligible findings: ZERO.**

---

## 4 · What has been learned (durable, method-level)

1. **Return is not predictable; severe loss is.** r² negative on every fold
   (−0.04 … −1.37); severe-loss AUC 0.73–0.89. Risk identification is
   tractable where return prediction is not.
2. **Lagged information beats current.** `confidence_pct_lag_1d` is a
   stable top-5 severe-loss predictor while current confidence does not
   separate the tails at all (India d=0.51 at t−10).
3. **Trajectory beats level.** `ma20_dist_slope_10d` — a pure lag construct
   — ranked #1 with spread 0.026 across 5/5 folds.
4. **Prior strength is a reversal signature.** USA losers had the larger
   prior day (+0.58 vs +0.01), larger prior 10 days (+4.02 vs +1.83) and a
   steeper MA20 slope (+2.43 vs −0.73).
5. **Confidence does not separate winners from losers** and points the
   wrong way in both markets; the >=90 bucket (n=299) returns +0.067% vs
   +0.487% for <55.

---

## 5 · Next experiments

1. **Continue USA fundamental accumulation** to ~497 tickers (215 done).
2. **Clustering / anomaly laboratory (C1–C6)** — unsupervised fundamental
   states. Must be evaluated at ticker level from the outset; Wave 2C shows
   why row-level anything is untrustworthy on quarterly data.
3. **R2 → R3 meta-label classifier** — the highest-value remaining branch,
   and the form R3-G may reopen in.
4. **Wait for the cohort to span earnings dates.** Most fundamental
   questions are currently unanswerable in principle, not for lack of
   modelling. The prequential ledger accrues toward this daily.

Explicitly **not** in scope: intraday classification, neural models,
knowledge graphs.

## 6 · Evidence-tier vocabulary (existing, not new)

`n<5` OBSERVATION · `5–14` HYPOTHESIS · `15–29` RESEARCH_SIGNAL ·
`30–49` STRONGER_EVIDENCE · `50+` VALIDATION_CANDIDATE

VALIDATION_CANDIDATE ≠ production-ready. R3-A…G are registered in
`backend/research/research_registry.py` against the existing 13-stage
Coverage Tracker — no parallel status vocabulary.
