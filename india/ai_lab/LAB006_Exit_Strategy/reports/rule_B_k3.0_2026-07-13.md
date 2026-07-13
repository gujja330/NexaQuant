# LAB006 · Rule B (vol-spike k=3.0) — Backtest Report
_Generated 2026-07-13T11:43:49_

## Verdict
**Read this table like a portfolio audit, not a horse race.** Return alone does not decide.
Look for material improvement on MaxDD, CVaR, Ulcer, recovery time. Confirm PBO<0.10, DSR>0.90.
The operator makes the promotion call.

## Metric comparison

| Metric | Baseline | Rule B (vol-spike k=3.0) · P1 | Rule B (vol-spike k=3.0) · P2 | Rule B (vol-spike k=3.0) · P3 |
|---|---|---|---|---|
| CAGR | +18.4% | +17.2% | +17.5% | +17.3% |
| Total return | +123.0% | +112.2% | +115.0% | +113.0% |
| Sharpe | +1.40 | +1.39 | +1.37 | +1.39 |
| Sortino | +1.96 | +1.97 | +1.93 | +1.96 |
| Max DD | -18.2% | -18.2% | -18.2% | -18.2% |
| CVaR (5%) | -1.8% | -1.7% | -1.8% | -1.7% |
| Ulcer Index | 598.9% | 604.3% | 617.9% | 593.4% |
| Recovery days | 342 | 342 | 342 | 342 |
| Turnover (frac cycles exited) | 0.0% | 31.6% | 31.6% | 31.6% |
| False-exit rate | — | 100.0% | 100.0% | 100.0% |
| Opportunity cost (avg %) | — | +5.65 | +5.65 | +5.65 |

## Robustness (DSR / PBO)
| Variant | DSR | PBO | Note |
|---|---|---|---|
| P1 | 0.974 | 0.229 | ❌ fails gate |
| P2 | 0.971 | 0.286 | ❌ fails gate |
| P3 | 0.974 | 0.743 | ❌ fails gate |

## Interpretation
* P1 (cash-until-rebalance) — did the exit save capital vs holding?
* P2 (rotate-to-next) — was capital better deployed elsewhere?
* P3 (cooldown-then-reenter) — false-exit resilience.

### Promotion decision
Fill in after operator review:
- [ ] Promote to Telegram-as-signal
- [ ] Reject — evidence insufficient
- [ ] Retest with tweaked parameter
