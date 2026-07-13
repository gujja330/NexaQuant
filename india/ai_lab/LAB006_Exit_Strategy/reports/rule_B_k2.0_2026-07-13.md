# LAB006 · Rule B (vol-spike k=2.0) — Backtest Report
_Generated 2026-07-13T11:43:36_

## Verdict
**Read this table like a portfolio audit, not a horse race.** Return alone does not decide.
Look for material improvement on MaxDD, CVaR, Ulcer, recovery time. Confirm PBO<0.10, DSR>0.90.
The operator makes the promotion call.

## Metric comparison

| Metric | Baseline | Rule B (vol-spike k=2.0) · P1 | Rule B (vol-spike k=2.0) · P2 | Rule B (vol-spike k=2.0) · P3 |
|---|---|---|---|---|
| CAGR | +18.4% | +14.7% | +16.8% | +15.7% |
| Total return | +123.0% | +92.1% | +109.0% | +99.9% |
| Sharpe | +1.40 | +1.32 | +1.28 | +1.33 |
| Sortino | +1.96 | +1.86 | +1.79 | +1.87 |
| Max DD | -18.2% | -18.2% | -18.2% | -18.2% |
| CVaR (5%) | -1.8% | -1.5% | -1.8% | -1.6% |
| Ulcer Index | 598.9% | 585.6% | 579.3% | 561.0% |
| Recovery days | 342 | 342 | 342 | 342 |
| Turnover (frac cycles exited) | 0.0% | 63.2% | 63.2% | 63.2% |
| False-exit rate | — | 83.3% | 83.3% | 83.3% |
| Opportunity cost (avg %) | — | +6.29 | +6.29 | +6.29 |

## Robustness (DSR / PBO)
| Variant | DSR | PBO | Note |
|---|---|---|---|
| P1 | 0.964 | 0.629 | ❌ fails gate |
| P2 | 0.957 | 0.857 | ❌ fails gate |
| P3 | 0.965 | 0.571 | ❌ fails gate |

## Interpretation
* P1 (cash-until-rebalance) — did the exit save capital vs holding?
* P2 (rotate-to-next) — was capital better deployed elsewhere?
* P3 (cooldown-then-reenter) — false-exit resilience.

### Promotion decision
Fill in after operator review:
- [ ] Promote to Telegram-as-signal
- [ ] Reject — evidence insufficient
- [ ] Retest with tweaked parameter
