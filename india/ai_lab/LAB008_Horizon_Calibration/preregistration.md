# LAB008 — Horizon Calibration · Sealed Preregistration

**Sealed 2026-07-13.** This file is written and locked BEFORE any LAB008 candidate is executed.
Any deviation invalidates the preregistration and requires a NEW experiment ID.

## Research question

Does the production 63-trading-day recommendation horizon remain the best evidence-supported
horizon, or does a shorter/longer fixed horizon improve risk-adjusted performance and robustness?

## Null / control

**N0** = production horizon of **63 trading days**. This IS the current production behaviour
(`recommendation_registry.py:31 HOLD=63`, `recommendation_generator.py:44 rebal=63`). Production
code is NOT modified — LAB008 generates a fresh in-memory registry at horizon=63 using the same
PIT-safe `champion_picks()` function that production uses.

## Sealed candidates

| Candidate | horizon_days | is_control | Description |
|:-:|:-:|:-:|:-:|
| **N0** | 63 | true  | Production horizon (control) |
| **H21** | 21 | false | Monthly rebalance |
| **H42** | 42 | false | Bi-monthly rebalance |
| **H84** | 84 | false | Quarterly+ rebalance |

**Exactly 3 new strategy configurations** (N0 is the control, not a new search trial).

Cumulative strategy-search count:
- Before LAB008 seal: **32**
- After LAB008 seal:  **35**

## Exposure model — PRODUCTION DYNAMIC EXPOSURE

Every candidate applies the SAME PIT-reconstructed production `exp_series` (from
`confidence_engine.current_regime()`) at each cycle's asof date. This isolates horizon as the
only varying dimension while keeping the frozen production regime logic active. Horizon-varying
candidates differ ONLY in:
- When cycles begin (`asof`) and end (`mature_date`)
- How often the portfolio rebalances (and thus how often it pays cost)
- What the trailing exp value happens to be at each cycle's asof

**Rationale**: this matches the counterfactual "if production changed HOLD to N days, keeping
everything else the same". Testing horizon in isolation from the frozen regime overlay would be
an unrealistic backtest of a system that does not exist.

## Cost model

**100% stock turnover at each rebalance.** At every cycle boundary after the first, the
simulator applies `cost_bps × current_val` as a rebalance cost. This is the worst-case
assumption (assumes no overlap between consecutive cycle picks) and is what makes Gate 6
(cost drag) discriminating — high-frequency horizons pay more.

The simulator ALSO applies the LAB007 |Δexp|-style exposure-change cost when the production
exp differs between consecutive cycle asofs. In practice this is dwarfed by the stock-turnover
cost.

## PIT requirements (all met by design)

1. **Selection PIT-safe**: `champion_picks(closes, rets, asof)` uses `rets.loc[:asof].tail(LOOKBACK)`
   — trailing only. `LOOKBACK=120` in `arjuna_v2.py` is independent of horizon.
2. **Regime signal PIT-safe**: same `exp_series` construction as LAB007 (rolling quantile with
   `min_periods=30`, ffill on global overlay).
3. **Selection uses NO forward information**: only closes-up-to-asof.
4. **Forward closes at `asof + horizon`** are used ONLY for post-selection maturity scoring
   (`exit_price`, `actual_ret`) — never fed back into selection.
5. **No horizon-induced look-ahead**: LOOKBACK is fixed 120 days regardless of horizon; the
   selection window is the same trailing 120 days at every asof.

## Chronological Discovery / Confirmation split

Same as LAB007. Not "training" — no fitted model.

- **Discovery**: 2021-07-01 → 2023-10-13 (inclusive)
- **Confirmation**: 2024-01-15 → 2026-01-27 (inclusive)

Cycle counts DIFFER per candidate (different asofs). Reported explicitly in the LAB008 findings
alongside a statistical-power warning where confirmation-Weak-cycle count is small.

## Trading-days / annualization

`simulation.trading_days_per_year: 252` (config). All CAGR/Sharpe/etc. annualized against this
constant. Comparing raw per-cycle returns as if horizons had equal duration is FORBIDDEN — the
framework's `metric_suite` annualizes automatically via `trading_days_per_year`.

## Sealed promotion gates (all six must PASS under both cash-return assumptions)

**Gate 1** — Full-period CAGR not materially worse than N0
`(cand.full.cagr - n0.full.cagr) >= -0.02`

**Gate 2** — Full-period Sharpe not materially worse than N0
`(cand.full.sharpe - n0.full.sharpe) >= -0.10`

**Gate 3** — Confirmation CAGR not materially worse than N0
`(cand.conf.cagr - n0.conf.cagr) >= -0.03`

**Gate 4** — Confirmation max drawdown not materially worse than N0 (MaxDD is negative)
`(cand.conf.max_dd - n0.conf.max_dd) >= -0.03`

**Gate 5** — Weak-regime ulcer not materially worse than N0
`(cand.regime.Weak.ulcer - n0.regime.Weak.ulcer) <= 2.0`

**Gate 6** — Cost drag not materially worse than N0
`((cand.full.cagr - cand_stress.full.cagr) - (n0.full.cagr - n0_stress.full.cagr)) <= 0.01`

Gates are evaluated via the AST-safe expression evaluator (`lab_expression.compile_gate_expression`).
The retracted tautological Gate 6 (`cand.full.cagr - cand.full.cagr >= -3.0`) is NOT used.

## PBO policy

LAB008 has N=4 candidates (N0 + H21 + H42 + H84). `min_configs_for_interpretation` in the
YAML is 6, so LAB008's PBO is computed but flagged with the framework's CAUTION note:
"N=4 < min-for-interpretation 6 — treat with skepticism". **PBO is NOT a LAB008 promotion gate.**
Per-fold Sharpe rank stability is the primary small-N robustness evidence.

## DSR

`dsr.n_trials_source: manifest` → reads `cumulative_strategy_search: 35` after preregistration
seal. DSR is reported for each candidate but is NOT a hardcoded gate in LAB008.

## Reporting requirements

For every (candidate × cash × cost) row, report: CAGR, Sharpe, Sortino, MaxDD, CVaR(5%), Ulcer,
Recovery days, avg exp, DSR. Add per-period slices (Discovery, Confirmation, Full) and per-regime
attribution (Strong / Neutral / Weak) with cycle counts. Cost sensitivity table per candidate at
15/30/50 bps.

## Files

- `preregistration.md` — this file
- `lab008.yaml` — sealed config
- `horizon_policies.py` — plugin: per-horizon registry builder + policy builder + simulator
- `run_lab008.py` — thin runner
- `reports/lab008_<date>.md` + `.csv` — outputs

## What LAB008 will NOT do

- Not touch `india/recommendation_registry.py` (HOLD=63 stays)
- Not touch `india/recommendation_generator.py` (rebal=63 stays)
- Not touch Core (`arjuna_v2`, `confidence_engine`, HRP, sector cap)
- Not touch Telegram
- Not tune parameters after seeing results
- Not add candidates after seeing results
- Not compute or claim promotion based on PBO alone

## Reproducibility

- Sealed: 2026-07-13
- Cumulative trial count locked at 35 (32 previous + 3 new LAB008 candidates)
- Preregistration and results are TWO SEPARATE git commits
