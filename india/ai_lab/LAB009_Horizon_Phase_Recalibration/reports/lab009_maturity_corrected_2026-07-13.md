# LAB009 · Horizon Recalibration (turnover + phase) — Results Report 2026-07-13

_Generated 2026-07-13T14:50:27_

- **Config file**: `lab009.yaml` · hash `2b0d0bb429271565`
- **Preregistration**: `preregistration.md`
- **n_trials (cumulative Lab-wide)**: **38**
- **Common evaluation window**: `2021-10-01` -> `2026-03-27`
- **Cash returns**: ['0%', '6%']
- **Cost grid (bps)**: canonical=15.0, stress=50.0
- **Cost model**: Formulation B EXTENDED (effective portfolio weights incl. cash bucket, one-sided cost basis)

## Horizon × Phase cycle counts (inside common window)

| Candidate | Horizon | Phase | Full | Discovery | Confirmation | Strong | Neutral | Weak |
|---|---|---|---|---|---|---|---|---|
| N0 | 63 | 0 | 18 | 9 | 9 | 6 | 6 | 6 |
| N0 | 63 | 15 | 18 | 8 | 9 | 7 | 3 | 8 |
| N0 | 63 | 31 | 18 | 8 | 9 | 7 | 4 | 7 |
| N0 | 63 | 47 | 17 | 8 | 8 | 7 | 4 | 6 |
| H21 | 21 | 0 | 54 | 25 | 27 | 21 | 13 | 20 |
| H21 | 21 | 5 | 53 | 24 | 26 | 21 | 11 | 21 |
| H21 | 21 | 10 | 53 | 24 | 26 | 20 | 15 | 18 |
| H21 | 21 | 15 | 53 | 24 | 26 | 20 | 13 | 20 |
| H42 | 42 | 0 | 27 | 12 | 14 | 10 | 6 | 11 |
| H42 | 42 | 10 | 26 | 12 | 13 | 9 | 7 | 10 |
| H42 | 42 | 21 | 27 | 13 | 13 | 11 | 7 | 9 |
| H42 | 42 | 31 | 27 | 12 | 13 | 11 | 8 | 8 |
| H84 | 84 | 0 | 13 | 6 | 7 | 4 | 3 | 6 |
| H84 | 84 | 21 | 14 | 7 | 7 | 6 | 2 | 6 |
| H84 | 84 | 42 | 13 | 6 | 6 | 6 | 3 | 4 |
| H84 | 84 | 63 | 13 | 6 | 6 | 5 | 5 | 3 |

## Horizon-aggregate metrics — cash=0% · cost=15.0 bps (canonical)

| Cand | median CAGR | worst CAGR | median Sharpe | worst Sharpe | worst MaxDD | median Ulcer | worst Ulcer | median DSR | worst DSR | phase top-2 | cost_drag (pp) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| N0 | +11.2% | +9.6% | 1.233 | 1.076 | -16.8% | 6.309 | 6.573 | 0.642 | 0.519 | 1.000 | 0.741pp |
| H21 | +7.6% | +7.5% | 0.914 | 0.882 | -15.8% | 6.798 | 8.574 | 0.400 | 0.371 | 0.000 | 1.530pp |
| H42 | +10.4% | +7.2% | 1.159 | 0.809 | -18.6% | 6.775 | 8.548 | 0.594 | 0.315 | 0.500 | 0.962pp |
| H84 | +11.2% | +9.4% | 1.204 | 0.997 | -16.3% | 5.973 | 6.535 | 0.608 | 0.463 | 0.500 | 0.652pp |

### Confirmation-period medians — cash=0% · canonical cost
| Cand | median CAGR | median Sharpe | median MaxDD | median Ulcer |
|---|---|---|---|---|
| N0 | +3.9% | 0.500 | -15.4% | 8.233 |
| H21 | +3.8% | 0.467 | -14.5% | 7.909 |
| H42 | +4.6% | 0.564 | -13.9% | 7.619 |
| H84 | +5.4% | 0.614 | -14.3% | 7.454 |

## Horizon-aggregate metrics — cash=6% · cost=15.0 bps (canonical)

| Cand | median CAGR | worst CAGR | median Sharpe | worst Sharpe | worst MaxDD | median Ulcer | worst Ulcer | median DSR | worst DSR | phase top-2 | cost_drag (pp) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| N0 | +12.7% | +11.0% | 1.386 | 1.216 | -16.6% | 5.812 | 6.134 | 0.745 | 0.629 | 1.000 | 0.751pp |
| H21 | +9.1% | +8.9% | 1.085 | 1.041 | -14.6% | 6.055 | 7.556 | 0.539 | 0.499 | 0.000 | 1.607pp |
| H42 | +12.0% | +8.5% | 1.320 | 0.947 | -18.2% | 5.976 | 7.878 | 0.713 | 0.422 | 0.500 | 0.976pp |
| H84 | +12.8% | +11.0% | 1.363 | 1.151 | -15.9% | 5.386 | 6.023 | 0.718 | 0.588 | 0.500 | 0.661pp |

### Confirmation-period medians — cash=6% · canonical cost
| Cand | median CAGR | median Sharpe | median MaxDD | median Ulcer |
|---|---|---|---|---|
| N0 | +5.3% | 0.659 | -14.9% | 7.604 |
| H21 | +5.0% | 0.606 | -13.7% | 7.133 |
| H42 | +6.1% | 0.730 | -12.6% | 6.652 |
| H84 | +6.8% | 0.781 | -13.2% | 6.681 |

## Gate verdicts (locked preregistration; must PASS under BOTH cash assumptions)

### H21
**Cash=0%**
- ❌ **gate_1** — Candidate median confirmation Sharpe >= N0 median confirmation Sharpe: `cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ❌ **gate_2** — Candidate median full CAGR >= N0 median CAGR - 1.0pp: `cand.median.full.cagr >= n0.median.full.cagr - 0.01`
- ❌ **gate_3** — Candidate median full Sharpe >= N0 median Sharpe - 0.05: `cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ✅ **gate_4** — Candidate worst-phase full MaxDD not worse than N0 worst-phase by more than 3pp: `cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03`
- ❌ **gate_5** — Candidate phase top-2 Sharpe fraction >= 0.50: `cand.phase_top2_sharpe >= 0.50`
- ✅ **gate_6** — Candidate cost drag not more than 1pp worse than N0 cost drag: `(cand.cost_drag - n0.cost_drag) <= 0.01`
- **ALL 6**: ❌ FAIL

**Cash=6%**
- ❌ **gate_1** — Candidate median confirmation Sharpe >= N0 median confirmation Sharpe: `cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ❌ **gate_2** — Candidate median full CAGR >= N0 median CAGR - 1.0pp: `cand.median.full.cagr >= n0.median.full.cagr - 0.01`
- ❌ **gate_3** — Candidate median full Sharpe >= N0 median Sharpe - 0.05: `cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ✅ **gate_4** — Candidate worst-phase full MaxDD not worse than N0 worst-phase by more than 3pp: `cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03`
- ❌ **gate_5** — Candidate phase top-2 Sharpe fraction >= 0.50: `cand.phase_top2_sharpe >= 0.50`
- ✅ **gate_6** — Candidate cost drag not more than 1pp worse than N0 cost drag: `(cand.cost_drag - n0.cost_drag) <= 0.01`
- **ALL 6**: ❌ FAIL

### H42
**Cash=0%**
- ✅ **gate_1** — Candidate median confirmation Sharpe >= N0 median confirmation Sharpe: `cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ **gate_2** — Candidate median full CAGR >= N0 median CAGR - 1.0pp: `cand.median.full.cagr >= n0.median.full.cagr - 0.01`
- ❌ **gate_3** — Candidate median full Sharpe >= N0 median Sharpe - 0.05: `cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ✅ **gate_4** — Candidate worst-phase full MaxDD not worse than N0 worst-phase by more than 3pp: `cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03`
- ✅ **gate_5** — Candidate phase top-2 Sharpe fraction >= 0.50: `cand.phase_top2_sharpe >= 0.50`
- ✅ **gate_6** — Candidate cost drag not more than 1pp worse than N0 cost drag: `(cand.cost_drag - n0.cost_drag) <= 0.01`
- **ALL 6**: ❌ FAIL

**Cash=6%**
- ✅ **gate_1** — Candidate median confirmation Sharpe >= N0 median confirmation Sharpe: `cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ **gate_2** — Candidate median full CAGR >= N0 median CAGR - 1.0pp: `cand.median.full.cagr >= n0.median.full.cagr - 0.01`
- ❌ **gate_3** — Candidate median full Sharpe >= N0 median Sharpe - 0.05: `cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ✅ **gate_4** — Candidate worst-phase full MaxDD not worse than N0 worst-phase by more than 3pp: `cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03`
- ✅ **gate_5** — Candidate phase top-2 Sharpe fraction >= 0.50: `cand.phase_top2_sharpe >= 0.50`
- ✅ **gate_6** — Candidate cost drag not more than 1pp worse than N0 cost drag: `(cand.cost_drag - n0.cost_drag) <= 0.01`
- **ALL 6**: ❌ FAIL

### H84
**Cash=0%**
- ✅ **gate_1** — Candidate median confirmation Sharpe >= N0 median confirmation Sharpe: `cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ **gate_2** — Candidate median full CAGR >= N0 median CAGR - 1.0pp: `cand.median.full.cagr >= n0.median.full.cagr - 0.01`
- ✅ **gate_3** — Candidate median full Sharpe >= N0 median Sharpe - 0.05: `cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ✅ **gate_4** — Candidate worst-phase full MaxDD not worse than N0 worst-phase by more than 3pp: `cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03`
- ✅ **gate_5** — Candidate phase top-2 Sharpe fraction >= 0.50: `cand.phase_top2_sharpe >= 0.50`
- ✅ **gate_6** — Candidate cost drag not more than 1pp worse than N0 cost drag: `(cand.cost_drag - n0.cost_drag) <= 0.01`
- **ALL 6**: ✅ PASS

**Cash=6%**
- ✅ **gate_1** — Candidate median confirmation Sharpe >= N0 median confirmation Sharpe: `cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ **gate_2** — Candidate median full CAGR >= N0 median CAGR - 1.0pp: `cand.median.full.cagr >= n0.median.full.cagr - 0.01`
- ✅ **gate_3** — Candidate median full Sharpe >= N0 median Sharpe - 0.05: `cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ✅ **gate_4** — Candidate worst-phase full MaxDD not worse than N0 worst-phase by more than 3pp: `cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03`
- ✅ **gate_5** — Candidate phase top-2 Sharpe fraction >= 0.50: `cand.phase_top2_sharpe >= 0.50`
- ✅ **gate_6** — Candidate cost drag not more than 1pp worse than N0 cost drag: `(cand.cost_drag - n0.cost_drag) <= 0.01`
- **ALL 6**: ✅ PASS

## PBO across 16 horizon-phase configs (DIAGNOSTIC ONLY — phase-dependence caveat)

- Cash=0%: status = **computed** value = 0.871 · N=16 configs, S=8 folds
- Cash=6%: status = **computed** value = 0.843 · N=16 configs, S=8 folds

**Interpretation:** Phase configurations within the same horizon share policy definition; their per-fold Sharpes are correlated via shared underlying data. Treating N=16 as independent strategy hypotheses in CSCV UNDER-adjusts for dependence — PBO is diagnostic here, NOT a promotion gate. The effective strategy-hypothesis count is 3 (H21/H42/H84), reflected in n_trials=38.

## Final LAB009 verdict

**PROMOTE-ELIGIBLE (subject to operator approval)**: H84

_LAB009 does not modify production even if a candidate promotes; operator approval is required for any Core change._