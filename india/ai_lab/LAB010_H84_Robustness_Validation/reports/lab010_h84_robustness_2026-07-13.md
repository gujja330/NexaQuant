# LAB010 · H84 Robustness Validation — Results 2026-07-13

_Generated 2026-07-13T17:43:22_

- **Config**: `lab010.yaml` · hash `d921eeb86418f1d4`
- **Preregistration**: `preregistration.md`
- **n_trials (cumulative, unchanged)**: **38**
- **Common evaluation window (all configs)**: `2021-10-01` -> `2026-03-27`
- **Canonical cost**: 15.0bps · **stress**: 50.0bps

## Blocks (sealed)

- B1: 2021-10-01 -> 2023-06-30
- B2: 2023-07-01 -> 2024-12-31
- B3: 2025-01-01 -> 2026-03-27

## Full-window medians (cash=0%, canonical cost)

| Cand | median full Sharpe | median full CAGR | median conf Sharpe | worst full MaxDD | phase top-2 | cost_drag |
|---|---|---|---|---|---|---|
| N0 | 1.2332 | +11.2% | 0.5710 | -16.8% | 1.0000 | 0.0074 |
| H84 | 1.2044 | +11.2% | 0.8122 | -16.3% | 1.0000 | 0.0065 |

## Full-window medians (cash=6%, canonical cost)

| Cand | median full Sharpe | median full CAGR | median conf Sharpe | worst full MaxDD | phase top-2 | cost_drag |
|---|---|---|---|---|---|---|
| N0 | 1.3855 | +12.7% | 0.7491 | -16.6% | 1.0000 | 0.0075 |
| H84 | 1.3631 | +12.8% | 0.9525 | -15.9% | 1.0000 | 0.0066 |

## Block-level medians (cash=0%, canonical cost)

| Scope | N0 full Sharpe | H84 full Sharpe | H84 - N0 |
|---|---|---|---|
| block:B1 | 0.9838 | 0.7551 | -0.2287 |
| block:B2 | 2.2314 | 2.8618 | 0.6304 |
| block:B3 | 0.4895 | 0.2544 | -0.2351 |
| lobo:LOBO_dropB1 | 1.5147 | 1.6454 | 0.1307 |
| lobo:LOBO_dropB2 | 0.8085 | 0.6218 | -0.1866 |
| lobo:LOBO_dropB3 | 1.5032 | 1.4349 | -0.0682 |

## Block-level medians (cash=6%, canonical cost)

| Scope | N0 full Sharpe | H84 full Sharpe | H84 - N0 |
|---|---|---|---|
| block:B1 | 1.2738 | 0.9293 | -0.3445 |
| block:B2 | 2.3993 | 2.9539 | 0.5547 |
| block:B3 | 0.6688 | 0.5829 | -0.0859 |
| lobo:LOBO_dropB1 | 1.6137 | 1.8450 | 0.2313 |
| lobo:LOBO_dropB2 | 1.0242 | 0.8301 | -0.1941 |
| lobo:LOBO_dropB3 | 1.6733 | 1.5868 | -0.0865 |

## Gate verdicts (must PASS under BOTH cash assumptions)

### cash=0%
- ✅ `v1_lobo_dropB1_gate3`  scope=`lobo:LOBO_dropB1,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ❌ `v1_lobo_dropB2_gate3`  scope=`lobo:LOBO_dropB2,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ❌ `v1_lobo_dropB3_gate3`  scope=`lobo:LOBO_dropB3,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ❌ `v2_lobo_dropB1_gate1`  scope=`lobo:LOBO_dropB1,cost:canonical`  expr=`cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ `v2_lobo_dropB2_gate1`  scope=`lobo:LOBO_dropB2,cost:canonical`  expr=`cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ `v2_lobo_dropB3_gate1`  scope=`lobo:LOBO_dropB3,cost:canonical`  expr=`cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ `v3_lobo_dropB1_win_rate`  scope=`lobo:LOBO_dropB1,cost:canonical`  expr=`cand.phase_win_rate >= 0.50`
- ✅ `v3_lobo_dropB2_win_rate`  scope=`lobo:LOBO_dropB2,cost:canonical`  expr=`cand.phase_win_rate >= 0.50`
- ❌ `v3_lobo_dropB3_win_rate`  scope=`lobo:LOBO_dropB3,cost:canonical`  expr=`cand.phase_win_rate >= 0.50`
- ✅ `v4_stress_gate1`  scope=`full,cost:stress`  expr=`cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ `v4_stress_gate2`  scope=`full,cost:stress`  expr=`cand.median.full.cagr >= n0.median.full.cagr - 0.01`
- ✅ `v4_stress_gate3`  scope=`full,cost:stress`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ❌ `v5_block_B1`  scope=`block:B1,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe`
- ✅ `v5_block_B2`  scope=`block:B2,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe`
- ❌ `v5_block_B3`  scope=`block:B3,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe`
- ✅ `v6_full_gate1`  scope=`full,cost:canonical`  expr=`cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ `v6_full_gate2`  scope=`full,cost:canonical`  expr=`cand.median.full.cagr >= n0.median.full.cagr - 0.01`
- ✅ `v6_full_gate3`  scope=`full,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ✅ `v6_full_gate4`  scope=`full,cost:canonical`  expr=`cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03`
- ✅ `v6_full_gate5`  scope=`full,cost:canonical`  expr=`cand.phase_top2_sharpe >= 0.50`
- ✅ `v6_full_gate6`  scope=`full,cost:canonical`  expr=`(cand.cost_drag - n0.cost_drag) <= 0.01`
- Block majority: FAIL

### cash=6%
- ✅ `v1_lobo_dropB1_gate3`  scope=`lobo:LOBO_dropB1,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ❌ `v1_lobo_dropB2_gate3`  scope=`lobo:LOBO_dropB2,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ❌ `v1_lobo_dropB3_gate3`  scope=`lobo:LOBO_dropB3,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ✅ `v2_lobo_dropB1_gate1`  scope=`lobo:LOBO_dropB1,cost:canonical`  expr=`cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ `v2_lobo_dropB2_gate1`  scope=`lobo:LOBO_dropB2,cost:canonical`  expr=`cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ `v2_lobo_dropB3_gate1`  scope=`lobo:LOBO_dropB3,cost:canonical`  expr=`cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ `v3_lobo_dropB1_win_rate`  scope=`lobo:LOBO_dropB1,cost:canonical`  expr=`cand.phase_win_rate >= 0.50`
- ✅ `v3_lobo_dropB2_win_rate`  scope=`lobo:LOBO_dropB2,cost:canonical`  expr=`cand.phase_win_rate >= 0.50`
- ❌ `v3_lobo_dropB3_win_rate`  scope=`lobo:LOBO_dropB3,cost:canonical`  expr=`cand.phase_win_rate >= 0.50`
- ✅ `v4_stress_gate1`  scope=`full,cost:stress`  expr=`cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ `v4_stress_gate2`  scope=`full,cost:stress`  expr=`cand.median.full.cagr >= n0.median.full.cagr - 0.01`
- ✅ `v4_stress_gate3`  scope=`full,cost:stress`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ❌ `v5_block_B1`  scope=`block:B1,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe`
- ✅ `v5_block_B2`  scope=`block:B2,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe`
- ❌ `v5_block_B3`  scope=`block:B3,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe`
- ✅ `v6_full_gate1`  scope=`full,cost:canonical`  expr=`cand.median.conf.sharpe >= n0.median.conf.sharpe`
- ✅ `v6_full_gate2`  scope=`full,cost:canonical`  expr=`cand.median.full.cagr >= n0.median.full.cagr - 0.01`
- ✅ `v6_full_gate3`  scope=`full,cost:canonical`  expr=`cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
- ✅ `v6_full_gate4`  scope=`full,cost:canonical`  expr=`cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03`
- ✅ `v6_full_gate5`  scope=`full,cost:canonical`  expr=`cand.phase_top2_sharpe >= 0.50`
- ✅ `v6_full_gate6`  scope=`full,cost:canonical`  expr=`(cand.cost_drag - n0.cost_drag) <= 0.01`
- Block majority: FAIL

## PBO diagnostic (NOT a gate)

- cash=0%: status=computed  value=0.9000  note='N=8 configs, S=8 folds'
- cash=6%: status=computed  value=0.9429  note='N=8 configs, S=8 folds'

## LAB010 outcome

**NOT_VALIDATED**

Production HOLD=63 remains unchanged. LAB010 does not modify production even under VALIDATED. Operator approval separately required for any Core change.