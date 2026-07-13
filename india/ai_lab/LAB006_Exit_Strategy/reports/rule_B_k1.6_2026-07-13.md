# LAB006 · Rule B (vol-spike k=1.6) — Backtest Report
_Generated 2026-07-13T11:43:04_

## Verdict
**Read this table like a portfolio audit, not a horse race.** Return alone does not decide.
Look for material improvement on MaxDD, CVaR, Ulcer, recovery time. Confirm PBO<0.10, DSR>0.90.
The operator makes the promotion call.

## Metric comparison

| Metric | Baseline | Rule B (vol-spike k=1.6) · P1 | Rule B (vol-spike k=1.6) · P2 | Rule B (vol-spike k=1.6) · P3 |
|---|---|---|---|---|
| CAGR | +18.4% | +11.1% | +17.1% | +13.4% |
| Total return | +123.0% | +65.0% | +112.0% | +81.4% |
| Sharpe | +1.40 | +1.11 | +1.24 | +1.23 |
| Sortino | +1.96 | +1.56 | +1.80 | +1.78 |
| Max DD | -18.2% | -18.7% | -18.2% | -18.2% |
| CVaR (5%) | -1.8% | -1.4% | -1.9% | -1.5% |
| Ulcer Index | 598.9% | 659.0% | 639.6% | 585.3% |
| Recovery days | 342 | 164 | 351 | 350 |
| Turnover (frac cycles exited) | 0.0% | 94.7% | 94.7% | 94.7% |
| False-exit rate | — | 94.4% | 94.4% | 94.4% |
| Opportunity cost (avg %) | — | +4.39 | +4.39 | +4.39 |

## Robustness (DSR / PBO)
| Variant | DSR | PBO | Note |
|---|---|---|---|
| P1 | 0.911 | 0.257 | ❌ fails gate |
| P2 | 0.950 | 0.200 | ❌ fails gate |
| P3 | 0.947 | 0.400 | ❌ fails gate |

## Interpretation
* P1 (cash-until-rebalance) — did the exit save capital vs holding?
* P2 (rotate-to-next) — was capital better deployed elsewhere?
* P3 (cooldown-then-reenter) — false-exit resilience.

### Promotion decision
Fill in after operator review:
- [ ] Promote to Telegram-as-signal
- [ ] Reject — evidence insufficient
- [ ] Retest with tweaked parameter
