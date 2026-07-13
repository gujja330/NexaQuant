# LAB006 · Rule B (vol-spike k=2.5) — Backtest Report
_Generated 2026-07-13T11:43:42_

## Verdict
**Read this table like a portfolio audit, not a horse race.** Return alone does not decide.
Look for material improvement on MaxDD, CVaR, Ulcer, recovery time. Confirm PBO<0.10, DSR>0.90.
The operator makes the promotion call.

## Metric comparison

| Metric | Baseline | Rule B (vol-spike k=2.5) · P1 | Rule B (vol-spike k=2.5) · P2 | Rule B (vol-spike k=2.5) · P3 |
|---|---|---|---|---|
| CAGR | +18.4% | +16.4% | +16.6% | +17.3% |
| Total return | +123.0% | +105.6% | +107.2% | +113.4% |
| Sharpe | +1.40 | +1.38 | +1.29 | +1.41 |
| Sortino | +1.96 | +1.95 | +1.81 | +1.98 |
| Max DD | -18.2% | -18.2% | -18.2% | -18.2% |
| CVaR (5%) | -1.8% | -1.6% | -1.8% | -1.7% |
| Ulcer Index | 598.9% | 590.8% | 593.8% | 575.9% |
| Recovery days | 342 | 342 | 342 | 342 |
| Turnover (frac cycles exited) | 0.0% | 52.6% | 52.6% | 52.6% |
| False-exit rate | — | 70.0% | 70.0% | 70.0% |
| Opportunity cost (avg %) | — | +5.40 | +5.40 | +5.40 |

## Robustness (DSR / PBO)
| Variant | DSR | PBO | Note |
|---|---|---|---|
| P1 | 0.973 | 0.514 | ❌ fails gate |
| P2 | 0.959 | 0.971 | ❌ fails gate |
| P3 | 0.977 | 0.457 | ❌ fails gate |

## Interpretation
* P1 (cash-until-rebalance) — did the exit save capital vs holding?
* P2 (rotate-to-next) — was capital better deployed elsewhere?
* P3 (cooldown-then-reenter) — false-exit resilience.

### Promotion decision
Fill in after operator review:
- [ ] Promote to Telegram-as-signal
- [ ] Reject — evidence insufficient
- [ ] Retest with tweaked parameter
