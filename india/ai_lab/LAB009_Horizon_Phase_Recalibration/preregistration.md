# LAB009 — Horizon Recalibration with Realistic Turnover and Phase Sensitivity

**Sealed 2026-07-13.** Locked BEFORE any candidate is executed. Any deviation invalidates
the preregistration.

## Origin

LAB008 evidence audit (commit `a2fa686`) returned **Decision B**: LAB008 valid only under its
sealed 100%-turnover + calendar-strided assumptions. Two methodology corrections identified:
(1) cost model assumed 100% stock turnover per rebalance when actual observed mean is
32-54%, biasing the comparison unevenly across candidates; (2) `closes.index[::horizon_days]`
strided asofs from a single starting phase produced non-comparable coverage across candidates
(N0∩H84 asof overlap = 26%, H84 missed first 2 months, H21 got 4 extra late months). Both
corrected here.

## Research question (identical to LAB008)

Does production horizon = 63 remain the best evidence-supported horizon after (a) replacing
100% turnover with observed portfolio turnover, (b) controlling for rebalance calendar phase,
(c) forcing identical evaluation coverage across candidates?

## Sealed candidates

| Candidate | horizon_days | is_control |
|:-:|:-:|:-:|
| **N0**  | 63 | ✅ true (production; unchanged) |
| **H21** | 21 | false |
| **H42** | 42 | false |
| **H84** | 84 | false |

Same 3 non-control hypotheses as LAB008 but with materially changed methodology → counted as
**3 new strategy-search trials**.

Cumulative strategy-search count:
- Before LAB009 seal: **35** (LAB006 28 + LAB007 4 + LAB008 3)
- After  LAB009 seal: **38** (+3 for H21/H42/H84 under new methodology)

## Realistic turnover cost model (LOCKED)

**Formulation choice: B EXTENDED (effective portfolio weights including cash bucket).**

For every cycle transition t-1 → t:

```
all_syms = union(symbols_prev, symbols_cur)
eff_w_prev(s) = exp_{t-1} × normalized_stock_weight_{t-1}(s)     for s in all_syms
eff_w_cur(s)  = exp_t     × normalized_stock_weight_t(s)         for s in all_syms
stock_side  = Σ_{s in all_syms} |eff_w_cur(s) - eff_w_prev(s)|
cash_side   = |exp_t - exp_{t-1}|                                (= |Δ(1 - exp)|)
turnover_t  = 0.5 × (stock_side + cash_side)
cost_t      = current_val × turnover_t × cost_bps × 1e-4
```

**Single cost term.** No separate `|Δexp|` additive term — exposure change is captured inside
`eff_w` movement plus the explicit cash-side symmetric term. Verified by worked example (see
LAB008 audit `LAB008_EVIDENCE_AUDIT.md`): matches one-sided capital-movement accounting exactly.

Rationale (documented before execution): Formulation A as spec'd overstates when stocks are
< 100% turned over on top of exposure change (double-charges the exposure-shifted capital
which then "churns"). Formulation B without cash bucket understates because half of any pure
exposure shift lives on the cash side and gets discounted by the 0.5 factor. B EXTENDED with
explicit cash-bucket contribution recovers the correct one-sided cost.

Stock weights `w_t(s)` are normalized to sum to 1 within the recommendation basket (matching
LAB008's `weights / weights.sum()` treatment). Missing symbols in the union have weight 0.

Cost is applied at each cycle asof AFTER the first (first cycle assumed zero prior position,
no round-trip cost required — matching LAB008 convention for parity of that specific choice).

## Phase-sensitivity design (LOCKED)

Each horizon is tested at **4 preregistered phase offsets**: `[0, ⌊H/4⌋, ⌊H/2⌋, ⌊3H/4⌋]`.

Asof generation: `closes.index[offset :: horizon_days]` for each phase offset. Cycles are then
subject to LAB009's PIT-safe champion_picks and the common-window filter (below).

| Horizon | Phase offsets (calendar-days) |
|:-:|:-:|
| N0=63 | 0, 15, 31, 47 |
| H21   | 0, 5, 10, 15 |
| H42   | 0, 10, 21, 31 |
| H84   | 0, 21, 42, 63 |

Total configurations: 4 horizons × 4 phases = **16 horizon-phase configs.**

No phase offsets are chosen after seeing results. No offsets added or removed post-run.

## Common evaluation window (LOCKED)

Before candidate performance is inspected:

- **common_start** = maximum, across all 16 horizon-phase configs, of each config's earliest
  scored asof (its first mature cycle boundary)
- **common_end** = minimum, across all 16 horizon-phase configs, of each config's latest
  scored asof (its last mature cycle boundary that has a fully realized forward return)

All PROMOTION-DRIVING metrics are computed ONLY on cycles whose asof is within
`[common_start, common_end]`. Full-available diagnostics are reported for transparency but
DO NOT feed the gate evaluations.

The common window is derived STRICTLY from date availability (scorable-cycle counts), NOT
from performance. This is PIT-safe by construction.

## Discovery vs Confirmation

Same chronological split as LAB007/LAB008:
- **Discovery**:   2021-07-01 → 2023-10-13
- **Confirmation**: 2024-01-15 → 2026-01-27

Applied AFTER the common-window filter. Cycle counts per (horizon × phase × period) reported
explicitly, with statistical-power warnings where confirmation-Weak-cycle count is low.

## Horizon-level aggregation (LOCKED)

Metrics are computed at HORIZON × PHASE (16 configs). Then per HORIZON aggregated:

- **median** across the 4 phases (CAGR, Sharpe, Sortino, MaxDD, CVaR5, Ulcer, DSR, avg_exp)
- **worst-phase** across the 4 phases with metric-specific direction:
  - worst CAGR / Sharpe / Sortino / DSR = MIN across phases
  - worst MaxDD / CVaR5 = MIN (most-negative)
  - worst Ulcer / Recovery = MAX
  - worst avg_exp not defined (skip)
- **phase_top2_sharpe** = fraction of the 4 phases where this horizon ranks in top-2 by
  Sharpe versus the OTHER horizons' same-phase results
- **cost_drag** = full-window CAGR at canonical cost minus CAGR at stress cost (in decimals)

Phase returns are NOT pooled into a synthetic single stream. Horizon is the experimental unit;
phase is a robustness dimension.

## Cash + cost grid

- `cash_returns_annual: [0.0, 0.06]` — dual primary, gates must pass under BOTH
- `cost_grid_bps: [15, 30, 50]`
- `canonical_cost_bps: 15` — used for headline metrics and PBO
- `promotion_stress_cost_bps: 50` — used for cost_drag calc (Gate 6) and diagnostics

30 bps is diagnostic only.

## Sealed promotion gates

All six must PASS under BOTH cash assumptions (0.0 AND 0.06) at canonical 15 bps.

**Gate 1** — Candidate median confirmation Sharpe ≥ N0 median confirmation Sharpe:
`cand.median.conf.sharpe >= n0.median.conf.sharpe`

**Gate 2** — Candidate median full-window CAGR ≥ N0 median − 1.0pp:
`cand.median.full.cagr >= n0.median.full.cagr - 0.01`

**Gate 3** — Candidate median full-window Sharpe ≥ N0 median − 0.05:
`cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`

**Gate 4** — Candidate worst-phase MaxDD not worse than N0 worst-phase by more than 3pp
(MaxDD is negative; "not worse" means less-negative):
`cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03`

**Gate 5** — Candidate phase top-2 Sharpe fraction ≥ 0.50:
`cand.phase_top2_sharpe >= 0.50`

**Gate 6** — Candidate cost drag not more than 1pp worse than N0 cost drag:
`(cand.cost_drag - n0.cost_drag) <= 0.01`

Gates evaluated via `lab_expression.compile_gate_expression` (AST-safe). Namespace root names:
`cand`, `n0`, `cand_stress`, `n0_stress` (although LAB009 uses `cost_drag` scalar rather than
cross-cost expressions for Gate 6; `cand_stress`/`n0_stress` remain in the whitelist but are
unused by these gates).

## PIT safety (audit performed before execution)

- Picks use `champion_picks(closes, rets, asof)` → `rets.loc[:asof].tail(LOOKBACK)` — trailing only
- Exposure `exp_series` uses trailing rolling quantiles + `ffill` (identical to LAB007 N0)
- Turnover uses only cycle t-1 and cycle t weights (both already sealed at their respective asofs)
- Phase offsets are calendar-arithmetic constants — do not inspect future returns
- Common window derived from scorable-date availability across all 16 configs — NOT from performance
- Future closes accessed ONLY for `exit_price` / `actual_ret` post-selection scoring

## DSR / multiple testing

- `n_trials_source: manifest` → **38** cumulative Lab-wide after LAB009 seal
- DSR reported for every horizon × phase config
- Horizon-level median DSR + worst-phase DSR also reported
- DSR is NOT a hardcoded gate in LAB009 (LAB008 had it as Gate 4; here Sharpe-based gates
  serve that role at aggregate level)

## PBO

There are 16 horizon-phase configs. **They are NOT 16 independent strategy hypotheses**:
- Phases within the same horizon share the same policy definition (same horizon)
- Phase-level Sharpes are correlated via shared underlying data
- Treating N=16 in CSCV as independent strategies OVERSTATES the effective search

**PBO is DIAGNOSTIC ONLY in LAB009.** No preregistered promotion decision uses PBO. The
framework will compute PBO across the 16 configs and report the value with the
`min_configs_for_interpretation` caution note. Report explicitly: "phase configurations
share horizon policy → PBO under-adjusts for dependence".

Effective strategy-hypothesis count for multi-testing burden is 3 (H21/H42/H84 as
horizon-level policies), reflected in `cumulative_strategy_search = 38`.

## What LAB009 will NOT do

- Not modify Core, production, or Telegram
- Not modify `india/recommendation_registry.py` (HOLD=63 stays)
- Not modify `india/recommendation_generator.py` (rebal=63 stays)
- Not modify LAB008 preregistration, diagnostics, or reports
- Not use the invalid "all candidates sample only N0's 19 asofs" design (which would break
  what "21-day rebalance" means)
- Not tune parameters or thresholds after seeing results
- Not add/remove phase offsets after seeing results
- Not change the common evaluation window after seeing results
- Not promote to production even if all gates pass — operator approval required

## Files

- `preregistration.md` — this file
- `lab009.yaml` — sealed config
- `horizon_phase_policies.py` — LAB009 plugin (registry × phase builder + simulator + aggregator)
- `run_lab009.py` — thin runner
- `reports/lab009_<date>.md` + `.csv` — outputs

## Framework extension

The generic `lab_runner._wrap_ns` is extended to recursively wrap arbitrary nested dicts as
attribute chains, so gate expressions can reference `cand.median.conf.sharpe`,
`cand.worst.full.max_dd`, and scalar leaves like `cand.phase_top2_sharpe` uniformly. This is
a small generic improvement, not LAB009-specific logic.

## Reproducibility

- Sealed: 2026-07-13
- Cumulative trial count locked at 38 (35 previous + 3 new LAB009)
- Preregistration and results are TWO SEPARATE git commits
