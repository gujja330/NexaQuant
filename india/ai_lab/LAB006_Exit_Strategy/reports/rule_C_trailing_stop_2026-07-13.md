# Rule C (trailing stop) — Backtest Report 2026-07-13

> **⚠ PROVISIONAL — DO NOT CITE AS EVIDENCE. Superseded by audit 2026-07-13.**
>
> This report was produced BEFORE the audit that identified 5 scaffold bugs (false-exit metric
> uses wrong denominator; P3 re-entry check leaks future info; PBO computed with degenerate N=2
> matrix; DSR n_trials underreports; P2 has structural concentration bug). The Rule C evidence
> below is not trustworthy until the scaffold is fixed and the run repeats.
>
> **What survives from this report**:
> - The equity-curve construction (chronological 19-cycle, no overlaps/gaps, ₹100k → ₹223k)
> - The exit-diagnostics table (per-exit false-exit rate: 51/44/43/40% at 5/8/10/12%)
> - The direction of DD improvement (5% P3 halves MaxDD in provisional numbers)
>
> **What is retracted**:
> - PBO figures — computed with degenerate N=2 CSCV setup
> - Main-sweep `False-exit` column — uses cycle-level denominator (nearly meaningless)
> - Any P3 comparison — future-info leak in re-entry check inflates results
> - Any P2 comparison — capital-concentration bug makes results structurally unrealistic
>
> Full replacement report will be published after `exit_lab.py` scaffold fixes land.


_Generated 2026-07-13T11:51:45_

## Baseline
CAGR **+18.40%** · Sharpe **1.40** · MaxDD **-18.2%** · Ulcer 6.0 · CVaR(5%) -1.81%

## Main sweep — cost=15bps
| Stop | Policy | CAGR | Sharpe | Sortino | MaxDD | CVaR(5%) | Ulcer | Recovery | Turnover | False-exit | Opp cost | DSR | PBO |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 5% | P1 | +5.7% | +0.89 | +1.13 | -10.8% | -1.0% | 577.4% | — | 100.0% | 100.0% | +3.64 | +0.61 | +0.00 |
| 5% | P2 | +22.8% | +1.17 | +1.65 | -30.6% | -2.6% | 1048.2% | — | 100.0% | 100.0% | +3.64 | +0.81 | +0.11 |
| 5% | P3 | +13.9% | +1.83 | +2.53 | -9.7% | -1.1% | 327.5% | 315 | 100.0% | 100.0% | +3.64 | +0.99 | +0.26 |
| 8% | P1 | +10.9% | +1.22 | +1.73 | -15.4% | -1.3% | 818.3% | — | 100.0% | 94.7% | +4.17 | +0.84 | +0.00 |
| 8% | P2 | +17.3% | +1.18 | +1.66 | -25.8% | -2.0% | 752.1% | — | 100.0% | 94.7% | +4.17 | +0.81 | +0.23 |
| 8% | P3 | +15.1% | +1.52 | +2.25 | -15.0% | -1.3% | 555.7% | — | 100.0% | 94.7% | +4.17 | +0.95 | +0.94 |
| 10% | P1 | +12.5% | +1.26 | +1.81 | -17.1% | -1.4% | 831.1% | 196 | 89.5% | 82.4% | +3.51 | +0.86 | +0.00 |
| 10% | P2 | +18.3% | +1.32 | +1.91 | -21.5% | -1.9% | 577.0% | 307 | 89.5% | 82.4% | +3.51 | +0.88 | +0.54 |
| 10% | P3 | +16.2% | +1.50 | +2.22 | -16.0% | -1.4% | 580.1% | — | 89.5% | 82.4% | +3.51 | +0.94 | +0.31 |
| 12% | P1 | +15.6% | +1.45 | +2.12 | -18.1% | -1.4% | 740.8% | 157 | 78.9% | 73.3% | +2.74 | +0.93 | +0.20 |
| 12% | P2 | +20.6% | +1.52 | +2.23 | -18.4% | -1.8% | 528.2% | 62 | 78.9% | 73.3% | +2.74 | +0.95 | +0.49 |
| 12% | P3 | +18.3% | +1.60 | +2.37 | -17.3% | -1.5% | 594.8% | 343 | 78.9% | 73.3% | +2.74 | +0.96 | +0.77 |

## Cost sensitivity — top 3 configs
| Stop | Policy | Cost (bps) | CAGR | Sharpe | MaxDD | Ulcer | Turnover |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 5% | P3 | 30 | +13.0% | +1.72 | -10.1% | 348.9% | 100.0% |
| 5% | P3 | 50 | +11.9% | +1.58 | -10.5% | 380.3% | 100.0% |
| 12% | P3 | 30 | +18.0% | +1.58 | -17.4% | 608.6% | 78.9% |
| 12% | P3 | 50 | +17.5% | +1.54 | -17.6% | 627.6% | 78.9% |
| 8% | P3 | 30 | +14.5% | +1.47 | -15.3% | 583.5% | 100.0% |
| 8% | P3 | 50 | +13.7% | +1.39 | -15.8% | 621.5% | 100.0% |

## Exit-quality diagnostics (per stop level, across all triggered exits)
| Stop | # exits | Avg exit ret | Avg hold-to-mature | Avg 'missed' recovery | False-exit % |
|:-:|:-:|:-:|:-:|:-:|:-:|
| 5% | 254 | -0.0% | +3.3% | +7.8% | 51% |
| 8% | 163 | -2.9% | -0.1% | +6.4% | 44% |
| 10% | 117 | -4.5% | -1.6% | +6.3% | 43% |
| 12% | 82 | -5.4% | -3.3% | +5.3% | 40% |

**Interpretation:** If `hold-to-mature` > `exit ret` on average, the stop is systematically cutting positions before recovery. If `False-exit %` is high, the stop is noise-triggered.

## Verdict framework
A rule promotes to Telegram-as-signal ONLY if:
- PBO < 0.10 for the chosen (stop, policy)
- Material MaxDD or CVaR improvement (not just Sharpe/CAGR)
- Cost-sensitive: winner remains competitive at 30bps and 50bps
- False-exit rate < ~30% (not systematically cutting recoveries)
- Operator approves

## Research-rule compliance for this run
- ✅ Close-to-close execution (no gap fill at stop price, no OHLC ordering leakage)
- ✅ P2 rotation candidate from same-cycle picks (PIT known at cycle asof)
- ✅ Cost sensitivity swept
- ✅ Fixed stop grid [0.05, 0.08, 0.1, 0.12]; no post-hoc threshold mining
- ✅ Exit-quality diagnostics captured
- ✅ DSR n_trials = 12 (main sweep) — corrects for multi-hypothesis inflation