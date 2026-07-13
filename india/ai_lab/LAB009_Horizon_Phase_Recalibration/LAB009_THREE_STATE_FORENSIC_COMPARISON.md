# LAB009 — Three-State Forensic Comparison

**Executed:** 2026-07-13 · **Seal commit:** `7fad319` · **Cumulative strategy_search:** 38

Compares three LAB009 evidence states derived from a single sealed hypothesis set (N0=63,
H21, H42, H84) and identical simulator/gates:

- **A** = Original LAB009 (asof-only common window)          — commit `6f78104`
- **B** = Maturity-boundary corrected (common_end = min last mature)     — commit `e8d13ae`
- **C** = Period-boundary corrected (disc/conf also mature-bounded)     — this run

Trial count remains 38 across all three states — same hypotheses, methodology corrections
only.

## Three-state candidate verdict table

| Cand | Cash | A_orig | B_mat_corrected | C_period_corrected |
|:-:|:-:|:-:|:-:|:-:|
| H21 | 0% | REJECT | REJECT | REJECT |
| H21 | 6% | REJECT | REJECT | REJECT |
| **H42** | 0% | **PROMOTE** | REJECT | REJECT |
| **H42** | 6% | **PROMOTE** | REJECT | REJECT |
| **H84** | 0% | REJECT | **PROMOTE** | **PROMOTE** |
| **H84** | 6% | REJECT | **PROMOTE** | **PROMOTE** |

## Three-state gate table (cash=0%)

| Cand | State | G1 | G2 | G3 | G4 | G5 | G6 | Failed |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| H21 | A | PASS | FAIL | FAIL | PASS | FAIL | PASS | g2/g3/g5 |
| H21 | B | FAIL | FAIL | FAIL | PASS | FAIL | PASS | g1/g2/g3/g5 |
| H21 | C | FAIL | FAIL | FAIL | PASS | FAIL | PASS | g1/g2/g3/g5 |
| H42 | A | PASS | PASS | PASS | PASS | PASS | PASS | — |
| H42 | B | PASS | PASS | **FAIL** | PASS | PASS | PASS | g3 |
| H42 | C | PASS | PASS | **FAIL** | PASS | PASS | PASS | g3 |
| H84 | A | PASS | PASS | **FAIL** | PASS | PASS | PASS | g3 |
| H84 | B | PASS | PASS | **PASS** | PASS | PASS | PASS | — |
| H84 | C | PASS | PASS | **PASS** | PASS | PASS | PASS | — |

Cash=6% shows the identical PASS/FAIL pattern.

## Period-corrected raw metrics (full precision, canonical 15bps)

**cash=0%**

| Cid | median conf Sharpe | median full CAGR | median full Sharpe | worst full MaxDD | phase_top2 | cost_drag |
|:-:|---:|---:|---:|---:|---:|---:|
| N0  | 0.5710007029 | 0.1123890808 | 1.2332208621 | -0.1682173617 | 1.000000 | 0.0074091249 |
| H21 | 0.5489182387 | 0.0759795588 | 0.9142863912 | -0.1583446413 | 0.000000 | 0.0153009310 |
| H42 | 0.7580550608 | 0.1039424003 | 1.1591974572 | -0.1856242259 | 0.500000 | 0.0096237886 |
| H84 | 0.8121675745 | 0.1119869569 | 1.2043883177 | -0.1625561320 | 0.500000 | 0.0065174188 |

**cash=6%**

| Cid | median conf Sharpe | median full CAGR | median full Sharpe | worst full MaxDD | phase_top2 | cost_drag |
|:-:|---:|---:|---:|---:|---:|---:|
| N0  | 0.7491421408 | 0.1274923170 | 1.3855218184 | -0.1656651617 | 1.000000 | 0.0075097147 |
| H21 | 0.7072238574 | 0.0914219623 | 1.0845804320 | -0.1459001295 | 0.000000 | 0.0160671725 |
| H42 | 0.9352184512 | 0.1197094448 | 1.3203516360 | -0.1816638284 | 0.500000 | 0.0097610888 |
| H84 | 0.9524602370 | 0.1279934872 | 1.3631030279 | -0.1590619509 | 0.500000 | 0.0066107329 |

## H84 gate margins @ full precision (cash=0%)

| Gate | Margin | Verdict |
|---|---:|:-:|
| G1 conf Sharpe delta | +0.2411668716 | ✅ PASS |
| G2 CAGR gap | +0.0095978761 | ✅ PASS |
| G3 Sharpe gap | +0.0211674556 | ✅ PASS |
| G4 worst MaxDD gap | +0.0356612297 | ✅ PASS |
| G5 phase_top2 gap | +0.0000000000 (boundary) | ✅ PASS |
| G6 cost_drag margin | +0.0108917061 | ✅ PASS |

## Per-phase confirmation Sharpe delta (B → C, cash=0%, canonical 15bps)

Phases where cycle exclusion changed conf Sharpe:

| Cand | Phase | B conf Sharpe | C conf Sharpe | Δ |
|:-:|:-:|---:|---:|---:|
| N0  | 15 | 0.4155 | 0.4711 | +0.0557 |
| **N0**  | **31** | **0.2150** | **0.5579** | **+0.3429** |
| H21 | 0  | 0.3393 | 0.4277 | +0.0884 |
| H21 | 5  | 0.6476 | 0.8858 | +0.2382 |
| H21 | 10 | 0.5168 | 0.6617 | +0.1450 |
| H21 | 15 | 0.4180 | 0.4361 | +0.0181 |
| H42 | 0  | 0.4869 | 0.6838 | +0.1969 |
| H42 | 10 | 0.9497 | 1.1615 | +0.2118 |
| H42 | 21 | 0.6416 | 0.8323 | +0.1907 |
| H42 | 31 | 0.2535 | 0.4014 | +0.1478 |
| H84 | 21 | 0.9213 | 0.8704 | **-0.0510** |
| **H84** | **42** | **0.4746** | **1.1861** | **+0.7115** |

Full-period Sharpes across all configs: **UNCHANGED** (delta = 0.0000). Only conf/disc period
slice metrics were affected — as expected, because period correction only modifies which
cycles enter conf/disc slices, not the full-period equity curve (which is bounded by the
maturity-corrected common_end already).

## H63_P31_2025-12-09 attribution

- `asof` = 2025-12-09; `mature_date` = 2026-03-11 (43 days past conf_end 2026-01-27)
- Present in **B_mat** N0 phase 31 confirmation membership: **YES**
- Present in **C_per** N0 phase 31 confirmation membership: **NO** (correctly excluded)
- N0 phase 31 conf Sharpe: **0.2150 → 0.5579** (delta **+0.3429**)
- N0 median conf Sharpe: **0.4998 → 0.5710** (delta **+0.0712**)

Excluding this one cycle from confirmation was the primary driver of N0's confirmation
Sharpe improvement.

## Gate 1 movement attribution

Change in Gate 1 (candidate median conf Sharpe ≥ N0 median conf Sharpe) from B to C:

| Cand | B N0 conf Sh | C N0 conf Sh | ΔN0 | B cand conf Sh | C cand conf Sh | Δcand | B (c−N0) | C (c−N0) |
|:-:|---:|---:|---:|---:|---:|---:|---:|---:|
| H21 | 0.4998 | 0.5710 | +0.071 | 0.5679 | 0.5489 | -0.019 | +0.068 | -0.022 |
| H42 | 0.4998 | 0.5710 | +0.071 | 0.5642 | 0.7581 | +0.194 | +0.064 | +0.187 |
| H84 | 0.4998 | 0.5710 | +0.071 | 0.6143 | 0.8122 | +0.198 | +0.115 | +0.241 |

**Attribution: BOTH N0 and candidates moved.** Under the period correction, excluding
post-conf_end-mature cycles improved conf Sharpes across the board (those tail cycles
included 2026-Q1 market weakness). H84 benefited more than N0; H21 lost ground while N0
improved (H21 phase mix included good tail cycles that were removed).

Even though N0 improved on Gate 1 (making it harder), H84's larger improvement kept its
margin wide (+0.241 delta at cash=0%). H21 fails Gate 1 in state C (worse than B where it
passed marginally).

## Residual trust audit results

All 15 checks PASS:
1. ✅ No discovery included cycle matures past discovery_end
2. ✅ No confirmation included cycle matures past confirmation_end
3. ✅ No period metric starts before period_start
4. ✅ Full-period equity remains bounded by corrected common_end (2026-03-27)
5. ✅ All 6 gate expressions byte-identical to seal `7fad319`
6. ✅ Gate evaluator consumes raw floats (verified in prior audit)
7. ✅ Median aggregation semantics unchanged
8. ✅ Worst aggregation direction-aware
9. ✅ phase_top2_sharpe semantics unchanged
10. ✅ DSR reads trial count 38 from central manifest
11. ✅ PBO remains diagnostic-only
12. ✅ PIT safety intact (champion_picks + rolling exp_series unchanged)
13. ✅ No post-result code/config edits (git diff 7fad319..HEAD on sealed files = empty)
14. ✅ No output filename edits after seal (verified — filenames were set IN seal)
15. ✅ No new methodology/evidence defect discovered

**Classification: A — trustworthy; no remaining material methodology/evidence defect found.**

## Final LAB009 verdict per candidate (mechanical, from all 6 gates)

- **H21: PROMOTE-INELIGIBLE** (fails G1, G2, G3, G5 under both cash assumptions)
- **H42: PROMOTE-INELIGIBLE** (fails G3 under both cash assumptions; margin -0.024 / -0.015)
- **H84: PROMOTE-ELIGIBLE** (passes ALL 6 gates under both cash assumptions)

## PBO diagnostic (unchanged)

- cash=0%: 0.8714  · cash=6%: 0.8429
- N=16 configs, S=8 folds · phase-dependence caveat unchanged
- **PBO is NOT a promotion gate.** Diagnostic only. High value indicates OOS fragility
  of IS-best selection across the 16 phase configurations.

## Production stays HOLD=63

**H84's PROMOTE-ELIGIBLE status is a LAB verdict, not a production decision.** Operator
approval separately required for any Core change. Recommendation: treat H84 as a hypothesis
requiring further validation (limited cycle count 12-14 per phase, high PBO 0.87, tight
Gate 3 margin +0.021) before any production consideration.

## Files
- Original LAB009 evidence: `reports/lab009_2026-07-13.md` + `.csv` (preserved unchanged)
- Maturity-corrected evidence: `reports/lab009_maturity_corrected_2026-07-13.md` + `.csv` (preserved unchanged)
- Period-corrected evidence: `reports/lab009_period_corrected_2026-07-13.md` + `.csv` (this run)
