# Trade Selection & Loss Attribution Report
**2026-10-27 · research only · no production writes · nothing promoted**

Answers the five questions set by the 2026-10-27 directive, and states
plainly where the data cannot yet support an answer.

---

## Headline

**The R2 `ensemble_score` does separate better trades from worse ones.**
That is the first genuinely positive, point-in-time result the programme
has produced.

**And every score bucket still lost money.** The score ranks correctly
inside a falling market; it does not make a long-only trade profitable.
So the indicated change is not a better score - it is a regime gate and
the ability to return NO TRADE.

Two further findings matter commercially:

- the workbook displays the **weaker** of the two available scores
- capital-weighted performance **cannot be computed** for the realized
  window, because the weight history died on 2026-09-03

---

## Q1 · Which entry characteristics distinguish winners from losers?

### `ensemble_score` · YES, and monotonically

Measured on 29 **sealed** daily snapshots
(`history/india/<date>/r2_scores.parquet`, 2026-09-15 -> 2026-10-22).
These are written at decision time and never revised, so the score is
genuinely point-in-time - no reconstruction, no leakage.

Forward 20-day return by score bucket, bucket 0 = highest score:

| Bucket | Mean fwd 20d | Dates |
|---|---|---|
| 0 (highest) | **-2.777%** | 29 |
| 1 | -3.128% | 29 |
| 2 | -3.693% | 29 |
| 3 | -4.494% | 29 |
| 4 (lowest) | **-5.495%** | 29 |

Monotonic across all five buckets. Spread top-to-bottom **2.72pp** over
20 days. Top bucket beats the next on **72.4%** of dates.

Per-date Spearman IC (information coefficient):

| Horizon | mean IC | IC>0 on | t naive | t Newey-West | non-overlapping dates |
|---|---|---|---|---|---|
| 10d | 0.112 | 96.6% | 9.54 | **6.35** | 3 |
| 20d | 0.141 | 96.6% | 11.08 | **5.59** | 2 |
| 30d | 0.144 | 96.6% | 10.94 | **6.25** | 1 |

**Why the naive t-stat must be ignored.** The snapshots are daily and
the forward window is 10-30 days, so consecutive dates share almost all
of their forward return. Their ICs are strongly autocorrelated and the
naive t divides by an error bar computed as if each date were
independent - inflating it by roughly sqrt(horizon). Newey-West at
lag=horizon still gives t≈6, but with n=29 against lag=20 that estimator
is itself stretched, and the truly non-overlapping sample is 1-3
observations.

**Verdict: the strongest signal found so far, and NOT established.** The
binding constraint is again date depth - this time the calendar depth of
sealed snapshots, which began only on 2026-09-11.

### `calibrated_confidence` · NO - and it is what the sheet shows

| Score | IC@20d | top-minus-next |
|---|---|---|
| `ensemble_score` | +0.141 | **+0.35pp** |
| `calibrated_confidence` | +0.074 | **-0.27pp** |
| `regime_adjusted_confidence` | +0.018 | +0.57pp |

`calibrated_confidence` has a positive IC but a NEGATIVE top-versus-next
spread: its highest-ranked names underperform its second bucket. The
workbook's `Confidence %` column is from this family, not from
`ensemble_score`.

Visible in a single snapshot (2026-10-26):

| Ticker | `ensemble_score` | Sheet `Confidence %` |
|---|---|---|
| TCS | 0.2402 | 34.9 |
| INFY | 0.2215 | 38.3 |
| HCLTECH | **0.1493** (lowest) | **40.6** (highest) |

The operator is shown an ordering that differs from the informative one.
This is a product defect independent of strategy.

### Other separators

| Characteristic | Winners | Losers |
|---|---|---|
| Sector (worst) | — | Basic Materials 15.6% win, -103.5pp · Utilities 0 of 7 |
| Sector (only positive) | Consumer Defensive 50% win, +0.4pp | — |
| Re-entry into a stopped-out name | — | **10% win rate** vs 18.9% baseline |
| `entry_confidence_pct` | mean **31.4** | mean **33.7** (inverted) |

---

## Q2 · Which losses could realistically have been prevented?

**Re-entry losses: 55 of 116 India losses (47%).** 25 tickers lost more
than once - OFSS x3, ATUL x3, MARUTI x3, COALINDIA x3, OIL x3. The
system has no memory of having just been wrong about a name.

Cooldown replay, walked in entry-date order so no decision uses an exit
that had not yet happened:

| Cooldown | Blocked | Their win rate | Book: -355.7pp -> |
|---|---|---|---|
| 10d | 24 | 12.5% | **-289.5pp** |
| 20d | 29 | 10.3% | **-269.5pp** |
| 30d | 30 | 10.0% | **-262.2pp** |

**Preventable: ~+93.5pp, about 26% of total losses.** It is a real
defect fix, and it is not a rescue - the book remains at -262pp.

USA shows zero re-entries, so no effect there.

---

## Q3 · Which filters improve expectancy without discarding too many winners?

Winner sacrifice, as the directive requires it to be counted:

| Filter | Losers avoided | **Winners sacrificed** | Net |
|---|---|---|---|
| Re-entry cooldown 30d | 27 | **3** | +93.5pp |
| Re-entry cooldown 20d | 26 | 3 | +86.2pp |
| Re-entry cooldown 10d | 21 | 3 | +66.2pp |

A 9:1 ratio of losers avoided to winners sacrificed. This is the only
filter tested so far that survives the winner-sacrifice check.

**Not yet tested:** regime gate, sector caps, entry-quality screens.
The regime gate is the highest-prior candidate because of Q1: the score
ranks correctly while every bucket loses, which is the signature of a
long-only method running in an unfavourable regime.

---

## Q4 · Does the best challenger beat the frozen R2 baseline on unseen data?

**NOT ANSWERABLE YET. No claim is made.**

Blockers, stated rather than worked around:

1. **Sealed-snapshot depth.** 29 daily dates from 2026-09-11. At a
   20-day horizon that is 1-2 non-overlapping observations. An
   out-of-sample split would leave nothing on either side.
2. **The cooldown result is in-sample.** It was measured on the same
   143 trades that motivated it.
3. **Capital-weighted returns are not computable** - see below.

The lever that changes (1) without waiting on the calendar is **CANON-2**:
replaying sealed snapshots from history already on disk. This is now the
first concrete, high-value reason to authorize it.

---

## Q5 · Is performance strong enough to justify production use?

**No.** Unchanged and not a close call.

India R2 was moved to ADVISORY / NOT ACTIONABLE on 2026-10-27
(`backend/delivery/governance/advisory_state.py`). Delivery, the
workbook and Telegram are unchanged; the picks simply no longer read as
instructions.

---

## The reconciled-ledger blocker

The directive requires capital-weighted returns, drawdown, costs and
exposure before any profitability claim. **These cannot be produced for
the realized window.**

- `size` is present on CURRENT rows and **null on every one**
- exit records carry no size at all
- `reports/portfolio_history.parquet` holds dated weights for
  **2026-03-02 -> 2026-09-03** and then stops

The realized window is 2026-08-04 -> 2026-10-23. Weights exist for
roughly its first month. `portfolio_engine` is one of the 35 engine
datasets now 28-43 days past a 1-day SLA.

**Consequence:** every P&L figure in this report - 18.9% win rate,
-2.49% per trade, -355.7pp - is **equal-weighted per-trade percentage**.
Not capital-weighted. No drawdown, no costs, no exposure.

Reviving `portfolio_engine` is therefore a **prerequisite** for Days 1-5,
not a parallel task.

---

## What the evidence actually indicates

1. **Keep `ensemble_score`, stop displaying the confidence family.**
   Cheap, independent of strategy, and the measurement supports it.
2. **Build the regime gate and NO TRADE.** The score ranks while every
   bucket loses - the clearest signature in the data that the method is
   long-only in the wrong conditions. This directly validates Stage 4's
   "a low candidate count is acceptable".
3. **Ship the re-entry cooldown as a defect fix**, on its 9:1 ratio -
   labelled in-sample until it sees dates it was not designed against.
4. **Authorize CANON-2.** Q1 is the first result worth extending, and
   date depth is what gates it.
5. **Revive `portfolio_engine` first.** Without it no profitability
   statement about any filter can be made at all.

## What the evidence does not support

- adding dimensions to the score · the existing one is already the most
  informative thing measured, and is not the binding constraint
- any claim of profitability, for a filter or the product
- promoting the cooldown on in-sample evidence
- reading the Newey-West t≈6 as significance · n=29 against lag=20

---

## Provenance

Every P&L recomputed from entry/exit prices; **0 of 171 mismatches**
against the reported ledger. Scores read from sealed PIT snapshots.
Forward returns measured close-to-close from the bar **after** the
decision date. Inference across dates, never rows, with the overlapping
-window correction applied and reported.

Modules: `backend/research/r3_program/rank_separation.py`,
`reentry_cooldown.py`, `usa_30d_gate.py`, `exit_autopsy.py`.
Artifacts under `reports/research/r3/`.
