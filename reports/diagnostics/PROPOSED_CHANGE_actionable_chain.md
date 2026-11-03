# Proposed change · R2's unreachable evidence gate

**Status: NOT APPLIED. Awaiting CEO approval.**
Measured 2026-11-03 against live `ensemble.json` and `recommendations.json`
for both markets. Reproduce with `python scripts/diagnose_actionable_chain.py --market both`.

---

## First, a correction

I previously reported "India produces ZERO actionable recommendations
(228/228 HOLD)". That was wrong. I read `action_prior_absolute` — the
pre-percentile field — and called it the shipped decision.

India ships **92 actionable calls** every day (23 STRONG BUY, 23 BUY, 23
SELL, 23 STRONG SELL) and its registry admits **5–7 new positions on a
normal trading day** (7 on 10-28, 6 on 10-29, 5 on 10-30, 5 on 11-02).
India is not stuck.

What is wrong is not a HOLD count, which is why nothing below is a
threshold edit.

---

## What is actually wrong

Two classifiers sit at the end of the chain. **The one that consults
evidence cannot fire. The one that decides does not consult evidence.**

### The evidence-gated path is unreachable

Three of India's eleven models never leave the neutral band on **any** of
228 names, while carrying **30.51%** of the ensemble weight:

| model | directional calls | weight |
|---|---|---|
| `aegis.event_driven.v1` | 0 of 228 | 0.1185 |
| `aegis.macro.v1` | 0 of 228 | 0.0508 |
| `aegis.sector_rotation.v1` | 0 of 228 | 0.1357 |

USA shares two of the three (`macro`, `sector_rotation`) at 18.66% of its
weight; `event_driven` is active on USA (473 of 516). `sector_rotation`
being dead in both markets is consistent with the already-reported
substrate defect that `sector` is empty in both.

`conflict.py` then counts a non-signalling model as a **dissenting** one.
The code is

```python
agreement = max(n_pos, n_neg) / n_total      # neutrals INCLUDED
```

while its own docstring says

> Agreement = max fraction on any one side (excluding neutrals from the base)

The consequence, measured: **172 of 228 India names** (and 295 of 516
USA) are flagged "models disagree" when every model that expressed a
direction agreed. The clearest case is `MM.NS` — 1 positive, 0 negative,
10 neutral. Unanimous among models with an opinion, recorded as the most
severe disagreement the system can represent (agreement 0.0909, below
`MAJOR_DISAGREE`). India's top-scored name `GNFC.NS` has 6 of 7
directional models agreeing (0.857) and is flagged at 0.545.

That valve removes **223 of 228** names before any threshold is read.

Calibration then turns the agreement cap into a confidence cap:

```python
calibrated = raw × (0.5 + 0.5 × agreement) × max(0.5, coverage)
```

With 3 dead models the agreement ceiling is 8/11 = 0.7273, so the
calibration multiplier cannot exceed 0.8636. India's observed ceiling is
**0.5462** and its best name, `TORNTPHARM.NS`, reaches **0.4909** against
the **0.50** the BUY arm requires — short by 0.0091. **Zero of 228 names
satisfy `c >= 0.50`.**

The STRONG arms need `c >= 0.70` and are **unsatisfiable at the ceiling in
both markets** (India 0.5462, USA 0.6365). Neither market can ever emit
STRONG_BUY or STRONG_SELL from this classifier, at any score.

### The live path cannot abstain

`MIN_CONFIDENCE_FOR_ACTION = 0.001` in `percentile_classifier.py` is
**350× below** India's own median calibrated confidence of 0.3505, so it
never binds — it removes 0 of 228 names.

At that confidence the classifier returns **exactly**
`{STRONG_BUY 23, BUY 23, HOLD 136, SELL 23, STRONG_SELL 23}` — India's
live distribution, bit for bit — whether the scores carry 0.12 of real
dispersion or **1e-9 of float noise**. India's 92 actionable calls are a
function of universe size, not of signal.

### The markets do not share a decision path

| field | India | USA |
|---|---|---|
| `action` (shipped) | 92 actionable | 18 actionable |
| `percentile_action` | 92 | 208 |
| `action_prior_absolute` | 0 (populated, all HOLD) | **null on all 516 rows** |
| `action == percentile_action` | **True** | **False** |

USA's 18 matches neither its percentile path (208) nor its absolute path
(24 by my funnel). A third code path decides USA. This breaks the
dual-market parity rule and is reported, not fixed.

---

## The proposed change

**One change, in `backend/recommendation/conflict.py`: compute agreement
over models that expressed a direction, as the docstring already says.**

```python
# current
agreement = directional / n_total

# proposed
expressed = n_pos + n_neg
agreement = (directional / expressed) if expressed else 0.0
```

No threshold moves. `DISAGREE_THRESHOLD` stays 0.60, the BUY arm stays
`score >= 0.20 and confidence >= 0.50`, the STRONG arms stay at 0.70.
This corrects a measurement, and it corrects it **towards the behaviour
the module already documents**.

### Measured impact

| | India before | India after | USA before | USA after |
|---|---|---|---|---|
| names flagged as disagreeing | 223 | **51** | 432 | **137** |
| absolute-classifier actionable | 0 | **3** | 0 | **41** |

India's three: `OFSS.NS` (+0.2161, agreement 0.75, calibrated 0.5249),
`JSWSTEEL.NS` (+0.2042, 0.75, 0.5249), `ADANIGREEN.NS` (−0.2894, 0.875,
0.5320).

**Note the size of that number.** The fix yields **3** gated India calls,
not 92. The evidence gate remains strict — which is the point. The choice
on the table is 3 calls backed by an evidence test versus 92 assigned by
rank.

### What the change does not do

- It does not disarm the disagreement valve. A genuine 5-positive /
  5-negative split still scores 0.50 and still flags.
  `test_genuine_split_is_flagged_under_both_measures` asserts this.
- It does not revive the STRONG arms on its own. India's ceiling rises
  but 0.70 still needs near-unanimity at near-maximum raw confidence.
- It does not fix the three dead models, which is the underlying defect.
  A model carrying 13.57% of the vote and emitting zero on every name is
  either not wired or has no input; `sector_rotation` almost certainly
  the latter, since `sector` is empty.

### Not proposed

- **Lowering any threshold.** Explicitly out of scope and not needed.
- **Raising `MIN_CONFIDENCE_FOR_ACTION`.** It would make the percentile
  classifier abstain, but choosing the number without an outcome study
  would be picking a cutoff to get a count — the same error in reverse.
- **Reconciling the two markets' decision paths.** Real, and larger than
  this change.

---

## Decisions needed

1. Apply the `conflict.py` agreement fix? (one function, 2 lines)
2. Investigate the three dead models — are they unwired, or starved of
   input? `sector_rotation` is blocked on the empty `sector` field.
3. Which classifier should decide? Today India uses the rank path and USA
   uses a third path. A gated path producing 3 India calls is a different
   product from a rank path producing 92.

## Evidence

- `reports/diagnostics/actionable_chain_india.json`
- `reports/diagnostics/actionable_chain_usa.json`
- `tests/pipeline/test_actionable_chain_diagnostic.py` — 30 tests, one per
  root cause
- Commit `25f1ac1ab`
