# LAB010 — H84 Robustness Validation · Sealed Preregistration

**Sealed 2026-07-13.** Locked BEFORE any LAB010 execution. Any deviation invalidates the
preregistration.

## Origin

LAB009 final trustworthy state (commit `413a735`) declared H84 PROMOTE-ELIGIBLE at the Lab
level. Five cautions remain (see `LAB010_EVIDENCE_REVIEW.md`): small per-phase cycle counts,
high PBO diagnostic (0.87), tight Gate 3 margin (+0.021), Gate 5 exactly at 0.500 boundary,
and single-episode risk.

LAB010 is a **robustness validation of the already-selected H84 candidate**, not a search.
No new candidates. No horizon search. No threshold search. Same H84 hypothesis, same phase
offsets, same simulator, same six sealed gate expressions (reused verbatim as LAB009 Gate 1,
3, 5 references below).

## Trial count

**`cumulative_strategy_search` remains 38.** LAB010 tests only the already-counted H84
hypothesis under the already-counted H84 phase offsets. LAB010 does not introduce a new
strategy-search trial. Rationale: LAB standards (`LAB_STANDARDS.md`) define a strategy-search
trial as a distinct hypothesis × parameter × policy combination tested for portfolio outcomes.
LAB010's candidate is identical to LAB009's H84 candidate (same 84-day horizon, same 4 phase
offsets, same gates). LAB010 adds robustness DIMENSIONS (chronological blocks, LOBO),
not new hypotheses. Framework rule §7 explicitly excludes "same-config rerun" (which LAB010
is, with additional slicing).

## Control and validation candidate

- **N0** = HOLD=63 (production; unchanged)
- **H84** = HOLD=84 (LAB009 promote-eligible; the subject of LAB010 validation)

No other candidates. H21, H42, and any neighboring horizon are explicitly EXCLUDED.

## Phase offsets (unchanged from LAB009)

- N0: {0, 15, 31, 47}
- H84: {0, 21, 42, 63}

## Chronological validation blocks (LOCKED, deterministic)

Three preregistered chronological blocks derived from calendar dates before H84 block-level
performance was inspected. Boundaries chosen to divide the common window (2021-10-01 →
2026-03-27) into three approximately-equal blocks of contiguous months:

| Block | Start | End | Approx duration |
|:-:|:-:|:-:|:-:|
| **B1** | 2021-10-01 | 2023-06-30 | 21 months |
| **B2** | 2023-07-01 | 2024-12-31 | 18 months |
| **B3** | 2025-01-01 | 2026-03-27 | 15 months |

Boundaries are deterministic and were chosen based on natural mid-year calendar splits,
NOT on H84 performance in any block. No performance data was inspected before sealing these
boundaries.

**Cycle-inclusion rule per block** (mature-bounded, matches sealed LAB009 discipline):
- Cycle belongs to block iff `block_start <= asof AND mature_date <= block_end`
- Cycles that straddle block boundaries are dropped from block-level analysis (not counted
  in any block). This is a natural consequence of the mature-bounded rule, not a defect.

**Data availability confirmed BEFORE seal:**

| Cand | Phase | B1 cycles | B2 cycles | B3 cycles | Total (all 3) |
|:-:|:-:|:-:|:-:|:-:|:-:|
| N0  | 0  | 6 | 5 | 4 | 15 |
| N0  | 15 | 6 | 5 | 4 | 15 |
| N0  | 31 | 6 | 5 | 4 | 15 |
| N0  | 47 | 6 | 5 | 3 | 14 |
| H84 | 0  | 4 | 3 | 3 | 10 |
| H84 | 21 | 5 | 3 | 3 | 11 |
| H84 | 42 | 4 | 4 | 3 | 11 |
| H84 | 63 | 4 | 4 | 2 | 10 |

Straddling drop rate: 15-25% of full-window cycles are lost to block boundaries. Preserved as
noted.

## Leave-one-block-out (LOBO) semantics

Three LOBO folds:
- **LOBO_dropB1**: use B2 ∪ B3 only (drop B1)
- **LOBO_dropB2**: use B1 ∪ B3 only (drop B2)
- **LOBO_dropB3**: use B1 ∪ B2 only (drop B3)

For each LOBO fold, the simulator is applied to the union of the retained blocks. Metrics are
computed on the resulting equity curve identically to LAB009 (median across phases + worst).

Cycles that straddle a retained block's boundary with the dropped block are dropped from that
LOBO fold (same mature-bounded rule).

## Cash + cost grid (unchanged from LAB009)

- `cash_returns_annual: [0.0, 0.06]`
- `cost_grid_bps: [15, 30, 50]`
- canonical=15, stress=50

## Turnover formula

Unchanged: Formulation B EXTENDED, single cost term. Worked example must still produce 0.90.

## Sealed validation gates

All gates evaluated via AST-safe evaluator on raw floats. Thresholds are REUSED from LAB009
(no new arbitrary numbers introduced) where possible. Every gate is tied to a specific LAB009
caution:

### V1 — LOBO Gate 3 (Sharpe delta) — addresses "Gate 3 margin fragility"
For each of 3 LOBO folds under canonical cost + both cash assumptions:
```
cand.median.full.sharpe >= n0.median.full.sharpe - 0.05
```
**All 6 (3 folds × 2 cash) must PASS.** Threshold identical to LAB009 Gate 3.

### V2 — LOBO Gate 1 (confirmation Sharpe) — addresses confirmation-period stability
For each of 3 LOBO folds under canonical cost + both cash assumptions:
```
cand.median.conf.sharpe >= n0.median.conf.sharpe
```
**All 6 must PASS.** Threshold identical to LAB009 Gate 1. Note: LOBO changes which
confirmation cycles are available.

### V3 — LOBO phase-win-rate (2-candidate analog of LAB009 Gate 5) — addresses "Gate 5 boundary"
Under LAB010's 2-candidate universe (N0 + H84 only), LAB009's `phase_top2_sharpe` metric is
DEGENERATE (both candidates are trivially in top-2 out of 2), so it cannot serve as a
robustness check. The non-degenerate 2-candidate analog is `phase_win_rate`:

```
phase_win_rate := |{ phase index i : H84.phase_i.full.sharpe >= N0.phase_i.full.sharpe }| / 4
```

For each of 3 LOBO folds under both cash assumptions:
```
cand.phase_win_rate >= 0.50
```
**All 6 must PASS.** Threshold 0.50 reused from LAB009 Gate 5 (i.e., cand must beat N0 by
phase-Sharpe in at least 2 of 4 phase indices). Byte-identical numeric threshold — the metric
is redefined only to escape the 2-candidate degeneracy. This is disclosed in the pre-seal
adversarial audit (Class B defect caught, fixed pre-seal).

### V4 — Cost stability (stress cost gates 1-3) — addresses "cost dependence"
At cost=50 bps (stress) under both cash assumptions:
```
G1: cand.median.conf.sharpe >= n0.median.conf.sharpe
G2: cand.median.full.cagr >= n0.median.full.cagr - 0.01
G3: cand.median.full.sharpe >= n0.median.full.sharpe - 0.05
```
**All 6 (3 gates × 2 cash) must PASS at stress cost.** Same thresholds as LAB009 Gate 1/2/3.

### V5 — Block-level majority
H84 must beat N0 in at least 2 of 3 blocks by median full Sharpe (raw comparison, no threshold):
```
for each block b in {B1, B2, B3}:
    win_b := (H84.block_b.median.full.sharpe >= N0.block_b.median.full.sharpe)
V5 PASS iff sum(win_b) >= 2 across both cash assumptions
```
Rationale: majority of blocks is a natural robustness threshold; addresses "single-episode
concentration". Applied per cash assumption.

### V6 — Full-period reproduction of LAB009 result
Under both cash assumptions at canonical cost, when LAB010 harness computes H84 vs N0 on the
full common window (no LOBO, no block split), all 6 LAB009 gates must still PASS. This
verifies the LAB010 harness reproduces LAB009's H84 verdict as a sanity check.

V6 gate_5 uses LAB009's `phase_top2_sharpe` byte-identical, but under 2-candidate universe
this metric is trivially 1.0 (both candidates always in top-2), so V6 gate_5 functions as a
LIVENESS SENTINEL (asserts H84 phase-Sharpes are finite) rather than a robustness check. The
non-degenerate robustness analog is V3 (phase_win_rate). Disclosed here per pre-seal audit.

### Not a gate — PBO reported diagnostically only
LAB010 does NOT set a PBO threshold. High PBO (0.87 in LAB009) already noted. Reported for
transparency.

## LAB010 final outcome

- **VALIDATED**: ALL V1–V6 gates PASS (36 gate evaluations total under both cash assumptions)
- **NOT_VALIDATED**: Any V1–V6 gate FAILS
- **INCONCLUSIVE**: If LOBO or block simulation returns unusable numeric results (e.g., NaN
  Sharpe from empty regime slice); explicit fallback path.

No discretionary override. VALIDATED requires ALL mandatory gates PASS. LAB010's outcome does
NOT modify production. Even VALIDATED requires separate operator approval before any Core
change.

## PIT safety

- Selection uses `champion_picks(closes, rets, asof)` — trailing only, unchanged
- Exposure via `exp_series` reconstruction — same as LAB009 N0
- Turnover from cycle t-1 and t weights only
- Block boundaries are calendar constants, no forward info
- LOBO fold definitions are deterministic
- Cycle inclusion: `block_start <= asof AND mature_date <= block_end` — same period-boundary rule as LAB009's addendum

## PBO handling

- PBO is computed for the full-period H84+N0 configuration (matches LAB009)
- PBO reported diagnostically under LAB010 outcome
- NOT a promotion gate

## Reporting

Output filenames sealed:
- `reports/lab010_h84_robustness_{date}.md`
- `reports/lab010_h84_robustness_diagnostics_{date}.csv`

## What LAB010 will NOT do

- Not modify production
- Not modify Core
- Not modify Telegram
- Not modify LAB009 sealed evidence
- Not introduce new candidates, horizons, phase offsets, cash assumptions, cost levels, or gate expressions
- Not tune thresholds after seeing results
- Not add/remove chronological blocks after seeing results
- Not add/remove LOBO folds after seeing results
- Not promote H84 to production (even under VALIDATED)

## Overlapping-cycle / pseudo-replication acknowledgement

- H84 phase offsets share underlying market data via overlapping stock holdings
- LOBO folds share block boundaries and cycle registries
- These are NOT independent samples in the strict statistical sense
- LAB010 metrics are NOT confidence intervals under the null; they are robustness observations
- LAB010 cannot cure this dependence; it can only stress-test whether H84 depends on a
  single block or phase

## Adversarial pre-audit acknowledgement

LAB010 uses SAME data as LAB009. It is not an out-of-sample validation. Its purpose is
narrow: does LAB009's H84 result survive chronological and cost stress on the same data?
A VALIDATED outcome is NECESSARY but NOT SUFFICIENT for production consideration. Truly
independent validation requires new data (forward paper trading, out-of-sample period, or
different universe) — outside LAB010's scope.

## Pre-seal adversarial audit findings (2026-07-13)

Under a formal adversarial pre-seal audit, three concerns were surfaced:

1. **phase_top2_sharpe degeneracy under 2-candidate universe (Class B, FIXED PRE-SEAL).**
   LAB009's Gate 5 metric compares one candidate's phase Sharpes against a 4-candidate
   universe. With LAB010's 2-candidate universe (N0, H84), phase_top2 is trivially 1.0
   whenever Sharpes are finite. V3 (LOBO Gate 5) was redefined to use `phase_win_rate`, the
   non-degenerate 2-candidate analog with byte-identical threshold 0.50. V6 gate_5 was
   retained byte-identical to LAB009 gate_5 but reframed as a liveness sentinel, not a
   robustness gate, with explicit disclosure.

2. **H84 loses more cycles than N0 under block/LOBO slicing (Class A limitation, disclosed).**
   H84's 84-day horizon straddles block boundaries more often than N0's 63-day horizon. Under
   the mature-bounded rule, ~15-25% of H84's full-window cycles are dropped from block-level
   analysis, versus ~11-17% for N0. This makes LAB010 harder for H84, not easier — a
   robustness stress in itself. Disclosed as a limitation.

3. **Statistical power is genuinely limited (Class A limitation, disclosed).**
   Under LOBO, each fold retains only 7-11 H84 cycles per phase. Block-level analysis has
   3-5 H84 cycles per phase per block. These are NOT confidence intervals under the null;
   they are robustness observations. LAB010 cannot cure the small-sample nature of the
   underlying LAB009 evidence; it can only stress-test whether H84 depends on any single
   block or phase. LAB010 does NOT claim statistical significance.

Classification after audit + fix: **A — trustworthy for the narrow "does H84 survive
chronological and cost stress on LAB009 data" question. Not sufficient by itself for
production promotion.**

## Sealed 2026-07-13

Author: operator + assistant
Change ID: LAB010-H84-ROBUSTNESS-VALIDATION-V1

Cumulative `strategy_search`: **38 unchanged** at LAB010 seal.
