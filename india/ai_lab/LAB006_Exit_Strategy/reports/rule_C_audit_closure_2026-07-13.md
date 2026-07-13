# Rule C (trailing stop) — Audit-closure Report 2026-07-13

_Generated 2026-07-13T12:11:22_

> **This is the fixed-scaffold rerun.** Supersedes the 2026-07-13 provisional report.
> Bugs fixed: (1) per-exit false-exit denominator; (2) PIT-safe P3 active-check; (3) full-matrix PBO across all 12 configs; (4) DSR n_trials from trial_manifest.
> P2 results included FOR COMPLETENESS but excluded from promotion analysis due to structural capital-concentration.

## Baseline
CAGR **+18.40%** · Sharpe **1.40** · MaxDD **-18.2%** · Ulcer 6.0 · CVaR(5%) -1.81%

## Full-matrix PBO
**PBO = 0.229** across the 12 (stop × policy) configs, S=8 folds. DSR n_trials = 28 (from trial_manifest.md).
Interpretation: PBO < 0.10 = robust config selection; > 0.50 = overfit.

## Main sweep — cost=15bps
| Stop | Policy | Notes | CAGR | Sharpe | Sortino | MaxDD | CVaR(5%) | Ulcer | Recovery | Exits | False-exit | Opp cost | DSR |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 5% | P1 |  | +5.7% | +0.89 | +1.13 | -10.8% | -1.0% | +5.77 | — | 254 | 50.8% | +3.64 | +0.46 |
| 5% | P2 | ⚠ excluded (P2 concentration) | +22.8% | +1.17 | +1.65 | -30.6% | -2.6% | +10.48 | — | 254 | 50.8% | +3.64 | +0.69 |
| 5% | P3 |  | +9.3% | +1.22 | +1.69 | -12.7% | -1.1% | +6.47 | — | 254 | 50.8% | +3.64 | +0.73 |
| 8% | P1 |  | +10.9% | +1.22 | +1.73 | -15.4% | -1.3% | +8.18 | — | 163 | 43.6% | +4.17 | +0.73 |
| 8% | P2 | ⚠ excluded (P2 concentration) | +17.3% | +1.18 | +1.66 | -25.8% | -2.0% | +7.52 | — | 163 | 43.6% | +4.17 | +0.70 |
| 8% | P3 |  | +13.1% | +1.38 | +1.99 | -15.6% | -1.3% | +6.83 | — | 163 | 43.6% | +4.17 | +0.83 |
| 10% | P1 |  | +12.5% | +1.26 | +1.81 | -17.1% | -1.4% | +8.31 | 196 | 117 | 42.7% | +3.51 | +0.75 |
| 10% | P2 | ⚠ excluded (P2 concentration) | +18.3% | +1.32 | +1.91 | -21.5% | -1.9% | +5.77 | 307 | 117 | 42.7% | +3.51 | +0.79 |
| 10% | P3 |  | +14.1% | +1.37 | +2.00 | -16.1% | -1.4% | +7.10 | — | 117 | 42.7% | +3.51 | +0.82 |
| 12% | P1 |  | +15.6% | +1.45 | +2.12 | -18.1% | -1.4% | +7.41 | 157 | 82 | 40.2% | +2.74 | +0.86 |
| 12% | P2 | ⚠ excluded (P2 concentration) | +20.6% | +1.52 | +2.23 | -18.4% | -1.8% | +5.28 | 62 | 82 | 40.2% | +2.74 | +0.90 |
| 12% | P3 |  | +16.5% | +1.51 | +2.21 | -17.2% | -1.5% | +6.80 | 149 | 82 | 40.2% | +2.74 | +0.89 |

## Cost sensitivity — top 3 non-P2 configs
(Same strategy under different friction — **NOT a PBO input**)
| Config | Cost (bps) | CAGR | Sharpe | MaxDD | Ulcer | Exits | False-exit |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| stop12_P3 | 30 | +16.3% | +1.49 | -17.5% | +6.92 | 82 | 40.2% |
| stop12_P3 | 50 | +16.0% | +1.46 | -18.0% | +7.09 | 82 | 40.2% |
| stop12_P1 | 30 | +15.4% | +1.43 | -18.4% | +7.52 | 82 | 40.2% |
| stop12_P1 | 50 | +15.2% | +1.41 | -18.7% | +7.66 | 82 | 40.2% |
| stop8_P3 | 30 | +12.6% | +1.34 | -16.0% | +7.11 | 163 | 43.6% |
| stop8_P3 | 50 | +12.0% | +1.27 | -16.5% | +7.49 | 163 | 43.6% |

## Exit-quality diagnostics (per stop level, across all triggered exits)
| Stop | # exits | Avg exit ret | Avg hold-to-mature | Avg missed recovery | False-exit % |
|:-:|:-:|:-:|:-:|:-:|:-:|
| 5% | 254 | -0.0% | +3.3% | +7.8% | 51% |
| 8% | 163 | -2.9% | -0.1% | +6.4% | 44% |
| 10% | 117 | -4.5% | -1.6% | +6.3% | 43% |
| 12% | 82 | -5.4% | -3.3% | +5.3% | 40% |
