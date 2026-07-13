# LAB010 — LAB009 Evidence Review

**Date:** 2026-07-13 · **Purpose:** Mechanical restatement of the LAB009 evidence LAB010 is
validating. No reinterpretation.

## Source commits
- Preregistration: `b077767`
- Original results: `6f78104`
- Evidence audit: `1210c77`
- Maturity-boundary seal: `3333282`
- Maturity-boundary results: `e8d13ae`
- Period-boundary seal: `7fad319`
- **Period-boundary results (FINAL, trustworthy): `413a735`**

## Sealed methodology (as of `413a735`)

- Candidates: N0=63 (control), H21, H42, H84
- Phase offsets per horizon: `[0, floor(H/4), floor(H/2), floor(3H/4)]`
  - N0: {0, 15, 31, 47}
  - **H84: {0, 21, 42, 63}**
- Cash: `[0.0, 0.06]`
- Cost grid: `[15, 30, 50]`, canonical=15, stress=50
- Turnover: Formulation B EXTENDED (single term)
- Common window (period-corrected): 2021-10-01 → 2026-03-27
- Discovery: 2021-10-01 → 2023-10-13
- Confirmation: 2024-01-15 → 2026-01-27
- Trading days/year: 252
- 6 sealed gates (unchanged since `b077767`, byte-identical in seal `7fad319`)

## H84 result under `413a735` (period-boundary corrected, canonical 15bps)

| Metric | cash=0% | cash=6% |
|---|---:|---:|
| Median full CAGR | 0.1119869569 | 0.1279934872 |
| Median full Sharpe | 1.2043883177 | 1.3631030279 |
| Median conf Sharpe | 0.8121675745 | 0.9524602370 |
| Worst full MaxDD | -0.1625561320 | -0.1590619509 |
| phase_top2_sharpe | 0.5000000000 | 0.5000000000 |
| cost_drag | 0.0065174188 | 0.0066107329 |

## H84 gate margins under `413a735` (cash=0%, canonical 15bps)

| Gate | Margin |
|---|---:|
| G1 conf Sharpe ≥ N0 | +0.2411668716 |
| G2 CAGR gap | +0.0095978761 |
| G3 Sharpe gap | **+0.0211674556** ⚠ |
| G4 worst MaxDD gap | +0.0356612297 |
| G5 phase_top2 gap | **+0.0000000000 (boundary)** ⚠ |
| G6 cost_drag margin | +0.0108917061 |

## H84 phase-level full Sharpes (cash=0%, 15bps)

| Phase | 0 | 21 | 42 | 63 |
|:-:|---:|---:|---:|---:|
| Sharpe | 1.074833 | 1.333943 | 0.997154 | 1.450509 |

## H84 phase cycle counts (period-corrected common window)

| Phase | 0 | 21 | 42 | 63 |
|:-:|:-:|:-:|:-:|:-:|
| Cycles | 12 | 13 | 13 | 12 |

## PBO diagnostic (unchanged)

- cash=0%: **0.8714285714285714**
- cash=6%: **0.8428571428571429**
- N=16 configs, S=8 folds
- Phase-dependence caveat: 16 configs are NOT 16 independent hypotheses
- Diagnostic only — NOT a promotion gate in LAB009

## Trial count

`cumulative_strategy_search: 38` at central manifest (verified `413a735` state).

## Production

- `india/recommendation_registry.py` — `HOLD = 63` (line 31)
- `india/recommendation_generator.py` — `rebal = 63` (line 44 CONFIG)
- Unchanged since long before LAB009 began.

## Final LAB009 verdict (from `413a735`)

- H21: PROMOTE-INELIGIBLE
- H42: PROMOTE-INELIGIBLE
- **H84: PROMOTE-ELIGIBLE**

## LAB009 cautions that LAB010 must address

1. H84 has 12-13 cycles per phase — small sample per phase
2. PBO 0.87 — high; OOS fragility signal across 16 phase configs
3. Gate 3 margin +0.021 — tight
4. Gate 5 exactly at 0.500 boundary — H84 ranks top-2 in only 2 of 4 phase indices
5. Promote-eligibility is a Lab-level verdict, not a production greenlight

LAB010 is designed to answer: **is H84's LAB009 promote-eligibility survives chronological and cost stress, or does it depend on a narrow slice of the evidence?**

## Note on `phase_top2_sharpe` under 2-candidate universe

LAB009's Gate 5 uses `phase_top2_sharpe` — the fraction of phase indices where a candidate
ranks in the top 2 among all 4 candidates (N0, H21, H42, H84). This is meaningful in a
4-candidate universe but DEGENERATE in LAB010's 2-candidate universe (N0 + H84 only), where
top-2-out-of-2 is trivially true whenever both Sharpes are finite (H84's phase_top2 = 1.0).

Consequence for LAB010: the LAB009-form Gate 5 expression (`cand.phase_top2_sharpe >= 0.50`)
is retained in V6 as a LIVENESS SENTINEL only (asserts phase Sharpes are finite). The
non-degenerate 2-candidate analog — `phase_win_rate := fraction of phase indices where H84's
phase-Sharpe >= N0's phase-Sharpe` — is used in V3 with byte-identical threshold 0.50. This
adaptation was disclosed in the pre-seal adversarial audit and is the only semantic
difference between LAB009's gate set and LAB010's V6 replay.
