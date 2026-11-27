# AEGIS exit strategy — dynamic exits, both markets

2026-11-26 · status: **ADVISORY** (flags only; nothing is sold automatically)

## The problem

AEGIS had no profit-taking exit. A position closed only when its trailing
stop was hit, and each recommendation carried a fixed
`suggested_holding_period_days` of **60 (USA) / 90 (India)**.

| measured 2026-11-26 | India (48 held) | USA (160 held) |
|---|---|---|
| held positions up ≥ +10% | 24, median 31 days | 3, median 27 days |
| profit given back if the stop is hit (≥ +10%) | 5.9pp | 11.9pp |
| held positions negative | — | 58 of 160 |

Specific failures:

- **KOTAKBANK** (India) +28.2% after 114 days, stop below entry.
- **SAIC** (USA) +17.5% after 104 days, stop below entry.
- **USA stops walk down with the price.** `monotonic_stops.usa: false` is a
  deliberate decision from 2026-09-11 (`configs/opportunity_registry.yaml`),
  so a falling stock's stop falls with it and rarely triggers. AMAT −26%,
  JBL −22%, VRT −17% were all still "active".
- Two existing engines produced signals and acted on none:
  `apply_dynamic_exits --enforce` made 154 decisions and enforced 0, and
  `capital_rotation` reported `n_positions=0`.

## Research basis

- **Triple-barrier exits, volatility-scaled.** A profit-take barrier, a stop
  barrier and a time barrier, each set as a multiple of the stock's own
  volatility **measured at entry**. Scaling makes "+2σ" mean +1% for a calm
  stock and +6% for a volatile one, and using only entry-time volatility
  prevents look-ahead.
  [quant-lessons](https://5x5x5x5.github.io/quant-lessons/ml/triple-barrier/) ·
  [fixed-horizon critique](https://alm0stsurely.github.io/2026/03/05/triple-barrier-labeling/)
- **Exit replay study, April 2026.** 900+ real trades replayed under
  alternative exit policies; the stronger policies favoured tighter loss
  limits, earlier profit capture and closer trailing protection, with results
  sensitive to regime and evaluation protocol.
  [arXiv 2604.27150](https://arxiv.org/abs/2604.27150)
- **Korean equities.** Best horizon about 29 days with 9% barriers; 36% of
  trades ended at the time barrier.
  [arXiv 2504.02249](https://arxiv.org/pdf/2504.02249)
- **AI-driven exit timing.** No solid public-equity evidence found
  ([survival-analysis survey](https://arxiv.org/pdf/1708.04649)). AEGIS's own
  severe-loss meta-label was **rejected in both markets** (2026-09-15).
  "Dynamic" here therefore means calibrated per stock and per market and
  validated on held-out dates, not a new ML model.

## Method — `scripts/exit_policy_replay.py`

- Population: every R2 episode with price bars, **excluding**
  `ORPHAN_AUTO_CLOSE` and `ADMIN_PHANTOM` closes (they were not investment
  decisions). Entry price is the entry-date close, the reference AEGIS uses
  for P&L.
- 315 policies tested: triple barrier, triple barrier plus give-back trail,
  and chandelier trail; horizons 5/10/15/20/30/45/60 trading days.
- Conservative fills: a gap through a barrier fills at the open; a bar
  touching both barriers counts as the stop. Round-trip costs 20 bps India,
  10 bps USA.
- **Nested cross-validation by entry-date block (K=5).** For each block the
  policy is chosen on the other four and scored on the held-out one. Only
  mature episodes count (closed, or ≥ 20 forward bars), and results are
  reported per entry date because rows are not evidence: 479 of USA's 901
  episodes share one entry date.

## Results (held-out, nested CV)

| | USA: AEGIS | USA: dynamic | India: AEGIS | India: dynamic |
|---|---|---|---|---|
| episodes / entry dates | 241 / 20 | same | 192 / 47 | same |
| mean return | −0.62% | **−0.06%** | −0.63% | +0.08% |
| mean per entry date | −1.44% | **+0.10%** | −0.18% | **−0.71%** |
| mean days held | 35.0 | **8.2** | 12.1 | 7.3 |
| severe losses (≤ −8%) | 23.2% | **8.3%** | 3.1% | 0.5% |
| worst | −53.7% | **−16.6%** | −12.4% | −8.0% |
| held-out blocks improved | | **3 / 5** | | 1 / 5 |
| verdict | | **SUPPORTED** | | **NOT SUPPORTED** |

USA's dominant choice was a **10-day triple barrier, stop and target each at
1σ·√10 from entry**, picked in 3 of 5 folds.

Caveats:

- USA rests on only 20 entry dates, and one block holds 149 of the 241
  episodes, so it carries a large share of the result.
- India's ratcheting stops already contain losses; dynamic barriers cut the
  tail further but made per-date returns worse, so India is unchanged.

## Holding period — should rising winners be held longer?

The question: let a rising position run, but by calculation, without
waiting so long. Three rules were compared on the same 241 mature USA
positions:

| USA, all mature positions | AEGIS today | fixed 10-day | let every winner run |
|---|---|---|---|
| mean per entry date | −1.44% | +1.70% | **+2.23%** |
| severe losses | 23.2% | 5.4% | 5.4% |
| win rate | 48.1% | **50.2%** | 41.1% |
| entry dates where it beats the other dynamic rule | | **16** | 3 |

Letting everything run wins on average only through a handful of large
trends (ADT +5% → +58%, CRM +4% → +27%, CCL +10% → +19%) and loses on 16
of 19 entry dates. That matches the research: short-term reversal and
longer-term momentum coexist, and only genuine trends persist
([Jegadeesh et al., RFS 2025](https://ideas.repec.org/a/oup/rfinst/v38y2025i12p3673-3728..html);
[Alpha Architect](https://alphaarchitect.com/combining-reversals/)).

So a **dynamic hold period** was tested: at the target, or at day h, a
position keeps running only if its **Kaufman efficiency ratio since entry**
(|net move| ÷ path travelled, point-in-time) is above a threshold and it is
in profit. Otherwise it is booked or exited. A runner trails 2–3 ATR under
its post-entry high, up to a hard cap.

Nested CV, on the four held-out blocks where each rule actually ran (one
block had no qualifying policy and is excluded):

| block | trend-quality hold | fixed 10-day | AEGIS today |
|---|---|---|---|
| Aug 10 – Sep 9 | −3.52 | **−2.79** | −5.00 |
| Sep 15 – 23 | −0.89 | **−0.39** | −2.40 |
| Oct 16 – 23 | **+3.18** | −1.24 | −3.47 |
| Oct 27 – Nov 2 | −1.25 | **+0.34** | −6.32 |

**Decision:**

- The fixed 10-day exit stays the rule; it wins 3 of 4 blocks.
- Holding strong trends longer pays only in genuinely trending periods
  (Oct 16–23) and costs in choppy ones, which has so far been the common
  case.
- It ships as **information, not a rule.** When a USA position hits its
  target or time exit while in profit with efficiency ≥ 0.5, the flag adds
  `STRONG TREND (efficiency x.xx) — holding longer is your call, trail it at
  <price>`. On 2026-11-26 that applied to COST (0.52) and EXE (1.00).
- An ML extension model was not built: with 20 USA entry dates it would
  overfit, and the severe-loss meta-label was rejected for that reason on
  2026-09-15.

## Profit booking — book all, or book half and let half run?

The AEGIS replay was too thin to decide (20 USA entry dates; the split won 1
of 5 blocks), so the exit rules were tested on every stock in the universe,
with an entry every 10 trading days across the full price history
(`scripts/exit_rule_robustness.py`, point-in-time volatility, ATR, 200-day
mean and market breadth).

- **USA:** 93,040 episodes, 740 entry dates, May 2022 – Nov 2026, 905 tickers
  (delisted names included).
- **India:** 28,457 episodes, 1,013 entry dates, Apr 2021 – Nov 2026.

**Pre-registered rule, fixed before the results:** prefer the split only if it
wins on more than half of entry dates in both trending and choppy regimes,
with severe-loss rate and worst loss no worse.

| all entries | book all | let all run | book half + run half | split beats book on |
|---|---|---|---|---|
| USA, mean per entry date | +0.67% | +0.85% | +0.76% | 31% of dates |
| India, mean per entry date | −0.47% | −0.25% | −0.36% | 26% of dates |
| USA, return per day held | **0.093%** | 0.076% | 0.083% | |

**Verdict: BOOK ALL stands in both markets.**

- Letting winners run lifts the average slightly, but the result is
  positively skewed: it wins on only 26–41% of entry dates.
- Per day of capital, booking is more efficient in USA, and the freed capital
  is reused.
- Downside is identical across all three rules in every regime; the worst
  losses are overnight gaps through the stop.

Regime pattern, contrary to the "hold longer in trends" hypothesis:

| run vs book, mean per entry date | broad uptrend | choppy | after broad selloffs |
|---|---|---|---|
| USA | +0.10 vs **+0.29** | **+1.34** vs +0.76 | **+4.60** vs +3.18 |
| India | **+0.33** vs −0.08 | −0.75 vs −0.76 | −0.21 vs −0.50 |

In USA, holding pays after selloffs and in chop (rebounds); booking is better
in broad uptrends. In India, holding pays in uptrends. A single regime rule
would be wrong for one market. A market-specific regime hold is a candidate
for a future held-out test, not a production change.

Caveat: these are entries on every stock, not AEGIS's own picks. The
momentum-only subset, closer to what R2 buys, gives the same verdict.

## What is live (advisory)

`backend/risk/exit_advisor.py`, run inside `canonical_daily_lifecycle` for
both markets. It writes `exit_advice`, `exit_advice_detail` and
`suggested_stop` onto each CURRENT row, appends `ADVISORY <label> · <detail>`
to the Reason column, and writes `reports/context/exit_advisory_<market>.json`.
It never moves a stop, sells, or writes the registry.

Precedence:

1. **SIGNAL EXIT** — today's R2 view of a held name is REDUCE/EXIT/SELL (both markets)
2. **DYNAMIC STOP** — price below its own volatility stop (USA)
3. **DYNAMIC TAKE PROFIT** — price above its own volatility target (USA)
4. **TIME EXIT** — 10 trading days held, neither barrier hit (USA)
5. **LOCK PROFIT** — +10/+20/+30% tier crossed and the stop is below the lock (both)
6. **ROTATE** — held ≥ 30 days, stalled between −3% and +5%, and an unheld BUY scores ≥ 10 points higher (both)

Today's preview (2026-11-26 data):

- **USA (160):** HOLD 99 · TIME EXIT 41 · DYNAMIC TAKE PROFIT 10 · DYNAMIC STOP 9 (incl. AMAT, JBL, VRT, CEG) · SIGNAL EXIT 1.
- **India (48):** HOLD 45 · SIGNAL EXIT 1 (ALKEM) · LOCK PROFIT 1 (KOTAKBANK) · ROTATE 1.

All thresholds are in `configs/opportunity_registry.yaml` under
`risk_engine.exit_advisor`.

## Not yet validated

- **ROTATE and SIGNAL EXIT** cannot be replayed: the recommendation archive
  holds about 5 days, and both need the daily R2 view as it was on every
  historical date. They act on signals AEGIS already produces, but their edge
  is unmeasured. Revisit once 30+ archived days exist.
- **Static entry-time targets** are switched off
  (`static_target_take_profit: false`). They had flagged 27 of India's 48
  positions on targets passed weeks earlier.

## Calibration is automatic

Barrier settings are not hand-copied into config. `aegis_run_all.py` runs
stage `exit-calibration:<market>` before the contract, for `--market usa`,
`india` and `both`:

- **When it recalibrates:** only if the last replay is 5 or more days old (about once a trading week).
  A skip costs about a second; a live recalibration about 10 seconds for both
  markets. It runs about weekly rather than daily for stability: with about 20 USA
  entry dates of evidence, a daily refit could flip a position's advice for no
  market reason.
- **What it does:** writes `reports/research/exit_policy_replay_<market>.json`
  with the recommended policy. The advisor uses it if the held-out verdict is
  SUPPORTED, switches the dynamic barriers off if it is not, and falls back to
  config if the replay is older than 35 days.
- **What the operator sees:** every run records which parameters were used
  and why (`params_source` in `exit_advisory_<market>.json`), e.g.
  `replay 2026-11-26: TB h=10d sl=1.0 tp=1.0 (TB nested CV SUPPORTED 3/5 blocks)`.
- **Failures:** a calibration failure never blocks delivery. The script
  exits 0, logs the failure, and the run continues on the previous calibration.

The full research report (all policy families, head-to-head) is still
available manually: `python scripts/exit_policy_replay.py --market both`.

## Switching to enforcement

Enforcement (actually closing positions or moving stops) is not implemented.
It is a strategy change and needs, per market:

1. The CEO's explicit approval.
2. A rerun of `python scripts/exit_policy_replay.py --market both` on fresh
   data, still showing SUPPORTED.
3. An enforcement switch in `risk_engine.exit_advisor`, built in the same
   per-market pattern as `monotonic_stops`.

Recommended cadence: rerun the replay monthly. USA's evidence grows by
roughly one entry date per trading day.
