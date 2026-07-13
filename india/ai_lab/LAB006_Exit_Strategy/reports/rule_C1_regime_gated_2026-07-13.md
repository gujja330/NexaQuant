# Rule C1 — Regime-Gated Trailing Stop (5% + P3 + Weak-only)

_Generated 2026-07-13T12:16:02_

Sealed pre-registration: `rule_C1_preregistration.md` (amended pre-run 2026-07-13).

## What C1 is
- Stop: **5%** trailing (close-to-close, PIT-safe, gap-aware)
- Re-entry policy: **P3** with PIT-safe active check at cooldown_end
- Regime gate: rule ACTIVE only when `regime_state_series` at cycle asof == 'Weak'
- Cycles where rule fired: **6 / 19** Weak cycles
- DSR n_trials = **30** (from trial_manifest.md)
- PBO: **N/A** (single frozen pre-registered strategy — CSCV requires ≥4 distinct strategies)

## FULL PERIOD 2021-2026 (descriptive)
| Metric | Baseline | C1 (15bps) | Δ |
|---|---|---|---|
| CAGR | +18.4% | +15.1% | -3.3% |
| Sharpe | +1.40 | +1.37 | -0.03 |
| MaxDD | -18.2% | -16.8% | +1.3% |
| Ulcer | +5.99 | +6.63 | +0.64 |
| CVaR(5%) | -1.8% | -1.5% | +0.3% |
| Total exits | 0 | 85 |  |
| False-exit % | — | 47.1% |  |
| DSR (n_trials=30) | — | 0.817 |  |

## CONFIRMATION SAMPLE — 2021 + 2023-2026 (primary promotion evidence)
| Metric | Baseline | C1 (15bps) | Δ |
|---|---|---|---|
| CAGR | +17.9% | +16.4% | -1.5% |
| Sharpe | +1.52 | +1.63 | +0.11 |
| MaxDD | -18.2% | -13.1% | +5.1% |
| Ulcer | +5.62 | +6.47 | +0.85 |
| CVaR(5%) | -1.6% | -1.4% | +0.2% |
| False-exit % | — | 49.1% |  |

**Promotion evidence must come from THIS table, not the discovery table below.**

## DISCOVERY PERIOD — 2022 only (hypothesis-generation; not confirmation evidence)
| Metric | Baseline | C1 (15bps) | Δ |
|---|---|---|---|
| CAGR | +20.1% | +10.3% | -9.8% |
| Sharpe | +1.18 | +0.78 | -0.41 |
| MaxDD | -13.9% | -13.9% | +0.0% |
| Ulcer | +5.44 | +5.32 | -0.12 |

## Cost stress test — same strategy, different friction
(NOT a PBO input. Confirms robustness to India trading friction.)
| Cost (bps) | CAGR | Sharpe | MaxDD | Ulcer | Exits | False-exit |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 15 | +15.1% | +1.37 | -16.8% | +6.63 | 85 | 47.1% |
| 30 | +14.9% | +1.35 | -16.8% | +6.73 | 85 | 47.1% |
| 50 | +14.5% | +1.32 | -16.8% | +6.87 | 85 | 47.1% |

## Regime attribution (portfolio metrics restricted to each regime's cycles)
| Regime | # cycles | C1 CAGR | Baseline CAGR | C1 MaxDD | Baseline MaxDD |
|---|---|---|---|---|---|
| Strong | 7 | +15.5% | +15.5% | -13.9% | -13.9% |
| Neutral | 6 | +19.8% | +19.8% | -13.0% | -13.0% |
| Weak | 6 | +9.7% | +19.8% | -5.6% | -11.8% |

## Promotion gate evaluation
- DSR gate: ❌ DSR=0.817, gate > 0.90
- Confirmation MaxDD improvement ≥ 5pp: ✅ actual=+5.1pp
- Full-period MaxDD improvement ≥ 3pp: ❌ actual=+1.3pp
- Confirmation false-exit < 40%: ❌ actual=49%
- Cost-robust at 50bps (full-period MaxDD improvement ≥ 3pp): ❌ actual=+1.3pp
- Weak-regime MaxDD improvement (rule mechanism sanity): ✅ actual=+6.2pp

Overall: **PROMOTE** only if ALL gates pass. Operator confirms.

## Reproducibility
- Trial manifest n_trials = 30 (recorded 2026-07-13)
- Pre-registration: rule_C1_preregistration.md, amended pre-run same day
- All parameters LOCKED before this run — no adjustment after seeing results