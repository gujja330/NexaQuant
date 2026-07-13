# LAB006 · Rule B (vol-spike k=1.8) — Backtest Report
_Generated 2026-07-13T11:43:29_

## Verdict
**Read this table like a portfolio audit, not a horse race.** Return alone does not decide.
Look for material improvement on MaxDD, CVaR, Ulcer, recovery time. Confirm PBO<0.10, DSR>0.90.
The operator makes the promotion call.

## Metric comparison

| Metric | Baseline | Rule B (vol-spike k=1.8) · P1 | Rule B (vol-spike k=1.8) · P2 | Rule B (vol-spike k=1.8) · P3 |
|---|---|---|---|---|
| CAGR | +18.4% | +14.2% | +16.3% | +15.7% |
| Total return | +123.0% | +87.6% | +105.2% | +100.0% |
| Sharpe | +1.40 | +1.32 | +1.24 | +1.35 |
| Sortino | +1.96 | +1.86 | +1.75 | +1.90 |
| Max DD | -18.2% | -16.6% | -17.9% | -17.7% |
| CVaR (5%) | -1.8% | -1.5% | -1.8% | -1.6% |
| Ulcer Index | 598.9% | 577.9% | 602.4% | 544.5% |
| Recovery days | 342 | 339 | 351 | 342 |
| Turnover (frac cycles exited) | 0.0% | 78.9% | 78.9% | 78.9% |
| False-exit rate | — | 93.3% | 93.3% | 93.3% |
| Opportunity cost (avg %) | — | +4.76 | +4.76 | +4.76 |

## Robustness (DSR / PBO)
| Variant | DSR | PBO | Note |
|---|---|---|---|
| P1 | 0.963 | 0.743 | ❌ fails gate |
| P2 | 0.947 | 0.629 | ❌ fails gate |
| P3 | 0.968 | 0.686 | ❌ fails gate |

## Interpretation
* P1 (cash-until-rebalance) — did the exit save capital vs holding?
* P2 (rotate-to-next) — was capital better deployed elsewhere?
* P3 (cooldown-then-reenter) — false-exit resilience.

### Promotion decision
Fill in after operator review:
- [ ] Promote to Telegram-as-signal
- [ ] Reject — evidence insufficient
- [ ] Retest with tweaked parameter
