# RISK001-A — EXIT ANALYTICS RESEARCH

**Document type:** Research specification & preliminary evidence report
**Status:** DRAFT · design + evidence only · NO code change · NO strategy change · NO implementation
**Owner role:** Principal Quant Researcher · Risk Scientist · Portfolio Risk Engineer
**Author:** AEGIS engineering
**Date opened:** 2026-07-17
**Supersedes:** none
**Reads (read-only):** `data/aegis_recommendation_db.csv`, `data/aegis_registry.csv`, `data/aegis_scorecard.csv`, `data/raw/india/*.parquet`
**Writes:** nothing (this document only)
**Sealed files touched:** zero
**Certification impact:** none — measurement-only research

---

## 0.  Non-negotiables (repeated here so no reader misses them)

1. This document is **research**, not implementation.
2. **No production code is changed** by this document.
3. **No strategy parameter is changed** by this document (HOLD=63, rebal=63, method=hrp, sector_cap=2, name_cap=0.30, cumulative_strategy_search=38 all remain frozen).
4. **No sealed file is touched** — the MON001 fingerprint `e4c070673568c52d…` must remain byte-identical after this document lands.
5. **No implementation of RISK001-C is recommended** by this document unless the counterfactual simulation (section 9) demonstrates statistically-significant improvement over Policy A (current production) on the primary metric.

---

## 1.  Executive summary — why this study exists

On the first live production run of the fixed post-OPS001-F pipeline (2026-07-17 11:48 IST), the daily Telegram report showed two exits:

| Ticker | Held | Return | Exit reason surfaced to user |
|:--|:-:|:-:|:--|
| ICICIGI | 21d | **−11.5%** | ROTATED — replaced by stronger candidate |
| TORNTPHARM | 3d | **−4.5%** | PORTFOLIO REBALANCE — dropped from top-N |

The operator's field observation: *"A system targeting +4–8% upside shouldn't routinely allow double-digit losses before exiting."*

The scorecard, computed the same run, corroborates that this is not a two-example anecdote:

| Signal | Value | What it says |
|:--|:-:|:--|
| **Worst historical exit** | **−26.0%** | A single position lost 5× the average winner in one trade |
| **Average MAE (Maximum Adverse Excursion) before exit** | **−6.3%** | Average position drops 6.3% below entry at some point before being exited |
| **Poor-quality exits (scorecard bucket)** | **28% (79 of 285)** | Almost 1-in-3 exits are graded "Poor" by the scorecard |
| **Worst per-ticker contributors** | RELAXO −3.8pp · RATNAMANI −1.8pp · TCS −1.5pp | Individual tickers dragging total return down materially |

The scorecard measures what actually happened. It does not measure what would have happened under a different exit policy. This document defines the study that answers that counterfactual.

**Central research question:**
> Would a Risk Controller with hard-loss authority (Policy B/C/D/E/F below) have improved AEGIS's risk-adjusted performance on the 285-recommendation historical dataset compared with the current portfolio-rotation-only exit logic (Policy A), and is the improvement statistically robust?

**Deliverable:** a decision that says either
- **RECOMMEND-IMPLEMENT** (RISK001-B design proceeds, RISK001-C implementation authorized), or
- **STAND-DOWN** (current policy is optimal on the evidence; no code change).

---

## 2.  Scope

### 2.1  In scope

- Every recommendation in `data/aegis_recommendation_db.csv` with a completed lifecycle (`state ∈ {ARCHIVED, EXITED, ROTATED}`)
- Every recommendation in `data/aegis_registry.csv` with an entry price and any post-entry price path
- 6 exit policies (A through F, defined in §8)
- Portfolio-level metrics (11 measures, defined in §7)
- Per-position metrics (7 measures, defined in §6.2)
- Counterfactual simulation with realistic slippage + fill assumptions (defined in §9.4)
- Statistical significance test vs Policy A (defined in §10)

### 2.2  Out of scope

- Any change to entry logic (score, HRP weights, sector caps, name caps)
- Any change to holding-period constants (HOLD=63)
- Any change to rebalance cadence (rebal=63)
- Any change to production code
- Any change to sealed files
- Design of the Risk Controller itself — that is RISK001-B
- Implementation of RISK001-C
- Live paper-trading validation — that is RISK001-D (not yet chartered)
- LAB011 outcome-intelligence dashboards — separate track

---

## 3.  Data inventory

### 3.1  Sources

| File | Purpose | Read-only guarantee |
|:--|:--|:-:|
| `data/aegis_recommendation_db.csv` | Lifecycle-tracked recommendation history | ✅ read-only, no mutations |
| `data/aegis_registry.csv` | Every score computed over 5-year history | ✅ read-only |
| `data/aegis_scorecard.csv` | Rolled-up performance metrics | ✅ read-only (produced by `india/scorecard.py`) |
| `data/raw/india/*.parquet` | 229 tickers' daily bars (OHLCV, adjusted close) | ✅ read-only |
| `india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json` | Sealed baseline hash | ✅ read-only, checked after study completes |

### 3.2  Coverage as of 2026-07-17

- **285 scored recommendations** with completed price paths
- **71 distinct tickers** touched over the lifetime
- **2021-07-01 → 2026-01-27** — 4.6-year window (scorecard's own boundary)
- **48 recommendations** currently in the live DB (ARCHIVED=24, LIVE=24)
- **~1,150 trading days** of price history per ticker

### 3.3  Data quality prerequisites

Before any analysis runs, the study must confirm:

1. Every historical exit has both `entry_price` and `exit_price` non-null
2. Every historical exit has `entry_date`, `exit_date`, and holding period computable
3. Every ticker referenced has a parquet file covering `[entry_date, exit_date]` inclusive
4. No price gap > 20% is silently reconciled (splits / bonuses must be adjusted-close only)
5. All dates are IST calendar; no DST edge cases

Any recommendation failing (1)–(3) is dropped from the study and reported in the "excluded" appendix, with reason.

---

## 4.  Methodology overview

The study proceeds in five deterministic stages:

```
Stage 1 — LOAD          → build the exit universe (target: N ≈ 285)
Stage 2 — CLASSIFY      → tag each historical exit by cause (§6.1)
Stage 3 — MEASURE       → compute the 7 per-position metrics (§6.2)
Stage 4 — SIMULATE      → replay 6 policies over the same universe (§8)
Stage 5 — DECIDE        → run significance tests + emit recommendation (§10)
```

Every stage is idempotent — rerunning with the same inputs produces byte-identical outputs. Every stage writes its outputs to a fresh `research/RISK001-A/outputs/` subdirectory, timestamped, and never overwrites prior runs. The final report `RISK001-A_EXIT_ANALYTICS_FINAL.md` incorporates the latest run's numbers by reference (not by paste), so re-runs stay reviewable.

---

## 5.  Definitions — canonical vocabulary

These terms are used with fixed meanings throughout the rest of the document. Any future RISK001 spec (B, C, D…) reuses them without redefinition.

| Term | Definition |
|:--|:--|
| **Entry price** | `close` on `entry_date` (adjusted for splits/bonuses) |
| **Exit price** | `close` on `exit_date` if signal-based; `open` on next session if gap-based (documented per case) |
| **MFE (Maximum Favorable Excursion)** | `max(high) over [entry_date, exit_date] − entry_price`, expressed as % of entry |
| **MAE (Maximum Adverse Excursion)** | `min(low) over [entry_date, exit_date] − entry_price`, expressed as % of entry (always ≤ 0) |
| **Realized return** | `(exit_price − entry_price) / entry_price` (excludes cost) |
| **Held (days)** | Trading-day count between entry_date and exit_date (weekends/holidays excluded) |
| **Terminal state** | one of `EXITED` (natural close), `ROTATED` (portfolio-optimizer swap), `STOPPED` (would-be stop trigger under counter-factual policy), `TIMED_OUT` (holding-period expired) |
| **Path** | The full close-to-close series from `entry_date` to `exit_date`, inclusive |
| **Policy** | A deterministic function `f(path, entry_price, position_state) → (would_exit: bool, would_exit_price: float, reason: str)` evaluated bar-by-bar |
| **Slippage assumption** | Fixed 5 bps applied on both entry and simulated exit (conservative for NSE mid-cap and above) |
| **Fill assumption** | Same-bar close for signal exits; next-bar open for stop-trigger exits (mimics realistic execution) |

---

## 6.  Per-position classification and measurement

### 6.1  Exit-cause taxonomy (for historical exits)

Every completed exit in the current dataset is classified as **exactly one** of the following, using the recorded lifecycle event + `why_exited` field where present:

| Code | Description | Expected count on current dataset |
|:--|:--|:-:|
| `HIST_ROTATED` | Portfolio optimizer replaced position with higher-ranked candidate | high (majority per scorecard) |
| `HIST_TIMED_OUT` | Position held to `HOLD=63` days and closed naturally | moderate |
| `HIST_REGIME_EXIT` | Regime flip triggered a policy exit (if any historical rule) | low or zero (regime exits are not currently implemented as an explicit rule) |
| `HIST_MANUAL_UNCLASSIFIED` | Cannot be attributed — flagged for manual review | should be zero; any non-zero count is a data-quality finding |

The distribution across these buckets is one of the study's headline tables (Table 1 in the final report). If `HIST_MANUAL_UNCLASSIFIED > 5%`, the study pauses and refuses to continue until classification is resolved.

### 6.2  Per-position measured fields

For each recommendation in scope, the study computes:

| # | Field | Type | Formula |
|:-:|:--|:--|:--|
| 1 | `ticker` | str | as-is |
| 2 | `entry_date` | ISO date | as-is |
| 3 | `exit_date` | ISO date | as-is |
| 4 | `held_days` | int | trading-day count |
| 5 | `realized_return_pct` | float | (§5) |
| 6 | `mfe_pct` | float | (§5) |
| 7 | `mae_pct` | float | (§5) |
| 8 | `sector` | str | from ClientProfile sector map (tenant-generic; no hardcoded list here) |
| 9 | `regime_at_entry` | enum | Strong/Neutral/Weak (from `india/regime.py` snapshot) |
| 10 | `volatility_at_entry` | float | 63d annualized realized vol |
| 11 | `exit_cause` | enum | §6.1 |
| 12 | `mae_pre_exit_bar_index` | int | which trading day within the hold produced the MAE — critical for stop-simulation |
| 13 | `mfe_pre_exit_bar_index` | int | same for MFE |

Fields 12 and 13 are the ones the counterfactual simulator uses to determine whether a hypothetical hard stop would have triggered before the historical exit.

---

## 7.  Portfolio-level metrics — the 11 measures

These are computed **on the full 285-position universe** under each of the 6 policies. Every future RISK001 policy proposal must produce all 11.

| # | Metric | Formula | Interpretation |
|:-:|:--|:--|:--|
| 1 | **Win rate** | `count(return > 0) / N` | Coarse hit rate; not a sufficient metric on its own |
| 2 | **Average return** | `mean(realized_return_pct)` | Mean is sensitive to tails; report alongside median |
| 3 | **Median return** | `median(realized_return_pct)` | Robust to outliers; the operator's intuition anchors here |
| 4 | **Profit factor** | `sum(returns[returns>0]) / abs(sum(returns[returns<0]))` | > 1.0 = net positive; > 1.5 = strong; > 2.0 = excellent |
| 5 | **Sharpe (position-level)** | `mean(returns) / std(returns) * sqrt(252/avg_holding_days)` | Annualized; conservative denominator |
| 6 | **Max drawdown (portfolio)** | `min(cumulative_equity − running_max) / running_max` on equal-weighted portfolio | The core capital-preservation metric — smaller (less negative) is better |
| 7 | **Average holding days** | `mean(held_days)` | Turnover proxy |
| 8 | **Largest loss** | `min(realized_return_pct)` | Worst single trade |
| 9 | **Largest gain** | `max(realized_return_pct)` | Best single trade |
| 10 | **Portfolio turnover** | `total_positions_opened / avg_positions_live * (252/window_days)` | Cost proxy — every rotation costs slippage + brokerage |
| 11 | **Ulcer index** | `sqrt(mean(drawdown_pct²))` over daily equity path | Captures depth *and* duration of drawdowns; a stop-loss policy should reduce this materially or the change is not worth making |

The **primary decision metric** is #6 (Max drawdown) subject to non-degradation of #4 (Profit factor). The decision rule is:

> Adopt a new policy only if **Max drawdown improves by ≥ 30% (relative)** AND **Profit factor degrades by ≤ 10% (relative)** AND the improvement is statistically significant (§10).

Any policy that improves #1 (Win rate) or #2 (Average return) alone is **not** grounds for adoption. Capital preservation, not hit-rate optimisation, is the RISK001 mandate.

---

## 8.  Policies to simulate

Every policy is deterministic given the path. Every policy is applied bar-by-bar to the same 285-position universe. Every policy uses the same slippage + fill assumptions (§5).

### Policy A — Current production (baseline)

- Exit triggered only by:
  - `HOLD=63` day expiry (natural time exit), or
  - Portfolio-optimizer rotation (position drops out of top-N at rebalance)
- No hard stop; no trailing stop.
- **This is the null hypothesis.** Every other policy is compared against A.

### Policy B — 5% hard stop

- If `low ≤ entry_price × (1 − 0.05)` at any bar in the hold, exit at `open` of the next bar.
- Otherwise identical to Policy A (rotation + time expiry still apply).
- Stop is not trailing; it's fixed at 5% below entry.

### Policy C — 7% hard stop

- Same as B but with 7% threshold.
- Included to test sensitivity of any B result to a slightly-looser threshold — protects against overfitting to 5%.

### Policy D — ATR-based stop

- Compute 20-day ATR (Average True Range) as of `entry_date − 1`.
- Stop set at `entry_price − 2 × ATR`.
- Volatility-aware: pharma might get a 6.5% stop; a utility might get a 3.5% stop.
- This is the policy most likely to survive statistical scrutiny because it respects each ticker's normal noise.

### Policy E — Trailing stop

- Initial hard stop at 6% below entry.
- Once the position gains 3%, the stop is trailed: `max(stop, high × 0.97)` — trails 3% below the running high.
- Locks in profit on runners while cutting losers early.

### Policy F — Break-even stop

- No hard stop for the first 5 trading days (gives the position room).
- After 5 days, if `close < entry_price`, exit at next open.
- Effectively a "must have shown momentum by end of week one" rule.

### 8.1  Combinations not tested (out of scope)

The following combinations are **not** simulated because they multiply the search space to the point where multiple-testing bias becomes serious:

- ATR-based + trailing hybrid
- Sector-specific stops
- Regime-dependent stops
- Stops adjusted by confidence bucket
- Volatility-scaled stops with an ATR multiplier ≠ 2

These are candidates for a **RISK001-A2** follow-up study, only if the primary study identifies volatility-awareness (Policy D) as the winner.

---

## 9.  Counterfactual simulation framework

### 9.1  Simulator design principles

- **Bar-by-bar replay.** Every policy is a function `evaluate_bar(bar, position_state) → action`. No look-ahead. No hindsight.
- **Same entry universe.** All 6 policies enter the same 285 positions on the same days. The only variable is when/how they exit.
- **Position-state independence.** Each of the 285 positions is simulated independently. Portfolio-level effects (concentration, HRP re-weighting) are applied only in the aggregation step, not per-position — because per-position independence is the only way the counterfactual is honest given the historical HRP output is fixed.
- **Costs modelled.** 5 bps slippage on entry + 5 bps on exit. 3 bps brokerage each side. These are conservative for NSE mid-cap and above; if any policy's edge disappears when costs rise to 10 bps, that must be flagged.

### 9.2  Simulator output

Per policy, the simulator emits:

- `research/RISK001-A/outputs/<timestamp>/policy_<X>_positions.parquet` — one row per position, with the 13 per-position fields (§6.2) plus policy-specific `sim_exit_date`, `sim_exit_price`, `sim_return_pct`
- `research/RISK001-A/outputs/<timestamp>/policy_<X>_daily_equity.parquet` — daily equal-weighted equity curve
- `research/RISK001-A/outputs/<timestamp>/policy_<X>_metrics.json` — the 11 portfolio-level metrics

### 9.3  Comparison table (the headline output)

The final report contains one table shaped as:

| Metric | Policy A (baseline) | Policy B (5% stop) | Policy C (7% stop) | Policy D (ATR) | Policy E (trailing) | Policy F (BE) |
|:--|:-:|:-:|:-:|:-:|:-:|:-:|
| Win rate | — | — | — | — | — | — |
| Average return | — | — | — | — | — | — |
| Median return | — | — | — | — | — | — |
| Profit factor | — | — | — | — | — | — |
| Sharpe | — | — | — | — | — | — |
| **Max drawdown** | — | — | — | — | — | — |
| Avg holding days | — | — | — | — | — | — |
| Largest loss | — | — | — | — | — | — |
| Largest gain | — | — | — | — | — | — |
| Turnover | — | — | — | — | — | — |
| Ulcer index | — | — | — | — | — | — |

Cells stay `—` until the simulator has run. This document must not contain fabricated numbers.

### 9.4  Charts included in the final report

1. **Equity curves overlay** — one line per policy, cumulative equal-weighted return over the 4.6-year window
2. **Drawdown envelope overlay** — running drawdown per policy on the same axis
3. **Return distribution histograms** — per policy, side-by-side; visualizes fat-tail reshaping
4. **Loss magnitude bucket chart** — count of exits in each of {[−5%, 0], (−5%, −7%], (−7%, −10%], > −10%} for each policy
5. **MAE-vs-Realized scatter** — one point per historical position, colored by exit-cause; motivation for the whole study
6. **Sector heatmap** — did any policy hurt one sector while helping the portfolio overall? (necessary diagnostic — a policy that fixes the average by systematically killing one sector's positions is not neutral)

---

## 10.  Statistical significance

### 10.1  Test structure

- **Paired difference test.** For each of the 285 positions, compute `Δ_i = return_policy_X_i − return_policy_A_i`. The pairing means path-level regime effects cancel.
- **Bootstrap 95% CI** over the 285 `Δ_i` values (10,000 resamples).
- **Sign test** for robustness — does policy X produce a better outcome in a majority of positions, not just on average?
- **Deflated Sharpe ratio** (Bailey & López de Prado) for each policy — corrects the Sharpe for multiple-testing across the 5 candidate policies.

### 10.2  Adoption threshold

A policy is a "winner" only if **all** of the following hold:

1. Max drawdown improves by ≥ 30% (relative to Policy A)
2. Profit factor drops by ≤ 10% (relative to Policy A)
3. Bootstrap 95% CI on Δ_max_drawdown excludes zero
4. Deflated Sharpe of the winner ≥ 0.5 above deflated Sharpe of Policy A
5. No single sector shows > 2× worse median return under the winner vs Policy A (the sector-neutrality guard)

If more than one policy passes, the winner is the one with the best combination of (1) and (2). Ties broken by lower Ulcer index.

If **no** policy passes, the study concludes **STAND-DOWN**: current design is defensible on the evidence, and no RISK001-C implementation is authorised. The three uncomfortable numbers (worst −26%, avg MAE −6.3%, 28% Poor exits) are acknowledged as characteristic of the current design's operating envelope, and any future revisit requires new evidence (more data, different regime, or a new policy class).

### 10.3  Guardrails against p-hacking

- The 6 policies (A–F) are **frozen at the start of the study**. No new policies may be added after the simulator has been run against the dataset even once.
- Threshold values inside each policy (5%, 7%, 2× ATR, 3% trail, 5-day break-even window) are **frozen at the start of the study**. No optimisation of these values against the dataset is permitted.
- The 285-position universe is **not** further subdivided (no "in-sample" / "out-of-sample" splits after the fact — the whole 4.6-year window is the sample).
- All bootstraps use a fixed seed (documented in the final report).
- The final report is committed as a single artifact — no cherry-picking of favourable metrics.

---

## 11.  Evidence already available (baseline snapshot, 2026-07-17)

This section reports what the scorecard already tells us, without any simulation. It defines the Policy-A baseline against which the simulator's output will be compared.

### 11.1  Aggregate performance (Policy A, current production)

| Metric | Value |
|:--|:-:|
| Total scored recommendations | 285 |
| Distinct tickers | 71 |
| Window | 2021-07-01 → 2026-01-27 |
| Win rate | 63.9% |
| Median return | +3.26% |
| Average return | +4.48% |
| Best single trade | +101.2% |
| Worst single trade | **−26.0%** |
| Average MFE before exit | +10.7% |
| Average MAE before exit | **−6.3%** |
| Rolling 12M win rate | 56.7% |
| Rolling 12M median | +1.48% |
| Exit-quality bucket "Poor" | 79 (28%) |
| Exit-quality bucket "Excellent" | 77 (27%) |

### 11.2  Interpretation

- **MAE > Median return.** Average positions drop 6.3% below entry before being exited, but median exit return is only 3.26%. Positions are moving through more downside than upside on average — a signature of loose exits.
- **28% Poor.** By the scorecard's own quality bucket, one exit in four is graded poor.
- **-26% floor.** A −26% single-trade loss on a portfolio of ~10–12 positions represents ~2.6% of total portfolio value — potentially breaching any reasonable per-position risk budget (RISK001-B will define the budget explicitly).
- **Sector concentration in the loss tail.** Worst contributors are RELAXO (Consumer Discretionary), RATNAMANI (Industrials), TCS (IT). This is *not* concentrated in a single sector — which is good for the diagnosis (no single-sector fluke) and bad for any sector-specific stop policy.

### 11.3  What the baseline snapshot does *not* answer

- Whether a 5% stop would have improved max DD without cutting winners short
- Whether an ATR stop would have avoided the −26% loss specifically
- Whether trailing stops would have preserved MFE gains
- What the return distribution would look like under each alternative

Only the counterfactual simulator (§9) can answer those.

---

## 12.  Deferred computation — what this document does NOT deliver

To keep this document design-only and to preserve the "no code" constraint, the actual simulator has not been implemented in this deliverable. The following are **explicit hand-offs** to whichever follow-up authorises the analytical work (**RISK001-A-exec**):

1. `research/RISK001-A/loader.py` — builds the exit universe from `aegis_recommendation_db.csv` + `aegis_registry.csv`
2. `research/RISK001-A/measure.py` — computes the 13 per-position fields (§6.2)
3. `research/RISK001-A/policies.py` — implements the 6 policies as deterministic bar-by-bar functions
4. `research/RISK001-A/simulate.py` — the replay engine (§9)
5. `research/RISK001-A/stats.py` — the significance tests (§10)
6. `research/RISK001-A/report.py` — emits the final `RISK001-A_EXIT_ANALYTICS_FINAL.md` with tables + charts filled in

All 6 modules live under `research/`, not under `india/` or `nexaquant/`. **They cannot be imported by production code.** They read data; they produce artifacts; they do not participate in the daily pipeline. This isolation is deliberate — research code must never accidentally become production code.

Estimated effort for RISK001-A-exec: **~4 hours** of analytical Python, assuming the parquet data is complete and no data-quality surprises show up. If data-quality issues emerge (§3.3), effort could extend to a full day.

---

## 13.  Non-goals — what this study will explicitly NOT conclude

The final report will not:

- Recommend a specific stop threshold outside the 6 policies simulated
- Recommend implementation without meeting all 5 adoption criteria in §10.2
- Change entry logic, scoring, or portfolio construction in any way
- Speculate about future performance — every claim is anchored to the 4.6-year historical window
- Compare against any external strategy, benchmark, or third-party study
- Address transaction taxes (STT), which vary per client — flagged for the operator's own overlay

---

## 14.  Decision matrix — what happens after the final report lands

| Report outcome | Next action | Authorised by |
|:--|:--|:-:|
| **RECOMMEND-IMPLEMENT** — one or more policies pass §10.2 | Proceed to RISK001-B (architecture) using the winning policy's shape as the concrete stop-rule for Level 1 | Operator |
| **STAND-DOWN** — no policy passes | Close RISK001 track. Sequence advances to OPS002. Revisit only when > 100 new recommendations have been added to the dataset or a market regime change is confirmed. | Operator |
| **INCONCLUSIVE** — statistical tests not decisive either way | Extend dataset by 6 months of forward validation, then re-run RISK001-A. Do NOT implement in the interim. | Operator |

---

## 15.  Integrity + sign-off

The final report must include:

- Simulator commit SHA (from `research/RISK001-A/` module tree)
- Dataset SHA (`sha256` of the loaded universe as a canonical parquet)
- Random seed for bootstrap resampling
- MON001 fingerprint at the time of the run (must be `e4c070673568c52d…` — the current sealed value)
- Sealed-file diff check: 0 files touched
- Cumulative_strategy_search: 38 (unchanged)
- Advisory disclaimer identical to production Telegram footer

Any RISK001-C implementation authorised on the basis of this study must trace back to the exact commit SHA of the analytical modules that produced the report. If the modules change after the report is emitted, the report is invalidated and the study must be re-run.

---

## 16.  Change log

| Date | Change | Author |
|:--|:--|:--|
| 2026-07-17 | Initial spec + baseline evidence report | AEGIS engineering |
