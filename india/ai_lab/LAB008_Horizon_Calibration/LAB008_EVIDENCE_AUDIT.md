# LAB008 — Evidence Audit (post-execution forensic)

**Audit date:** 2026-07-13 · **Auditor:** operator-directed forensic pass
**Sealed evidence commit:** `5a7fdb0` (NOT modified by this audit)
**Preregistration commit:** `ccb73c7` (NOT modified by this audit)
**Cumulative strategy_search:** **35** (unchanged)

This document is an audit artifact. It does not alter LAB008's sealed preregistration or
diagnostics. Its purpose is to determine whether LAB008's headline conclusion
("production HOLD=63 remains champion") is scientifically supported strongly enough to close
LAB008, or whether the evidence has a methodology limitation requiring a new experiment ID.

## Audit 1 — N0 vs production registry parity

Comparing the in-memory LAB008 N0 registry (built at horizon=63) against the historical subset
of `data/aegis_registry.csv` filtered by `source=='historical' AND scored==1 AND horizon_d==63`.

| Item | Production | LAB008 N0 |
|---|---|---|
| Unique cycles | 19 | 19 |
| Rows | 285 | 285 |
| First asof | 2021-07-01 | 2021-07-01 |
| Last asof | 2026-01-27 | 2026-01-27 |
| Common asofs | 19 (100%) | 19 (100%) |
| LAB008-only asofs | 0 | — |
| Production-only asofs | 0 | — |
| Symbol-set mismatches (per cycle) | 0 / 19 | — |
| Max \|weight diff\| across all common (asof, symbol) | **5.00e-05** (rounding: production weight is stored to 4 decimals; LAB008 to 6) |
| Max \|actual_ret diff\| across common | **5.00e-03** (rounding: production `actual_ret` stored to 2 decimals; LAB008 to 4) |

**Verdict: N0 parity is CLEAN.** Zero symbol-set mismatches. Diffs are strictly explainable by
storage precision (float rounding at read/write). LAB008 N0 faithfully reproduces the production
63-day historical registry.

## Audit 2 — Rebalance calendar / phase confound

Every candidate strides `closes.index[::horizon_days]` starting from `closes.index[0]`. This
alignment causes the candidates to share DIFFERENT calendar dates.

### First 15 asofs by candidate

```
N0  (63d): 2021-07-01, 2021-10-01, 2022-01-03, 2022-04-05, 2022-07-06, 2022-10-07,
           2023-01-06, 2023-04-12, 2023-07-13, 2023-10-13, 2024-01-15, 2024-04-18,
           2024-07-19, 2024-10-18, 2025-01-20
H21 (21d): 2021-07-01, 2021-08-02, 2021-09-01, 2021-10-01, 2021-11-02, 2021-12-03,
           2022-01-03, 2022-02-02, 2022-03-04, 2022-04-05, 2022-05-09, 2022-06-07,
           2022-07-06, 2022-08-04, 2022-09-07
H42 (42d): 2021-07-01, 2021-09-01, 2021-11-02, 2022-01-03, 2022-03-04, 2022-05-09,
           2022-07-06, 2022-09-07, 2022-11-09, 2023-01-06, 2023-03-09, 2023-05-15,
           2023-07-13, 2023-09-12, 2023-11-13
H84 (84d): 2021-09-01, 2022-01-03, 2022-05-09, 2022-09-07, 2023-01-06, 2023-05-15,
           2023-09-12, 2024-01-15, 2024-05-18, 2024-09-18, 2025-01-20, 2025-05-26,
           2025-09-23, 2026-01-27
```

### Pairwise asof overlap

| Comparison | N0 total | Other total | Common | N0-only | Other-only | Overlap % of N0 | Overlap % of other |
|---|---|---|---|---|---|---|---|
| **N0 vs H21** | 19 | 59 | 19 | 0 | 40 | 100% | 32% |
| **N0 vs H42** | 19 | 29 | 10 | 9 | 19 | 53% | 34% |
| **N0 vs H84** | 19 | 14 | 5 | 14 | 9 | 26% | 36% |

### Cycle date-range coverage

| Candidate | First asof | Last asof | First idx | Last idx |
|---|---|---|---|---|
| N0  | 2021-07-01 | 2026-01-27 | 126 | 1260 |
| H21 | 2021-07-01 | **2026-06-02** (4 months later) | 126 | 1344 |
| H42 | 2021-07-01 | **2026-03-27** (2 months later) | 126 | 1302 |
| H84 | **2021-09-01** (2 months later start) | 2026-01-27 | 168 | 1260 |

### Verdict on Audit 2

LAB008 tests **HORIZON DURATION + REBALANCE TIMING / CALENDAR PHASE simultaneously**. It does
NOT isolate horizon duration alone. Concretely:

1. **H84 misses the first 2 months** (2021-07 to 2021-09) that all other candidates capture —
   this drops early recovery data from H84's window.
2. **H21 gets 4 extra months of late data** (Feb-Jun 2026) not in N0.
3. **H42 gets 2 extra months of late data** (Feb-Mar 2026) not in N0.
4. **N0 vs H42 only 53% asof overlap** — the 9 non-overlapping N0 asofs are sampled from
   completely different price paths than H42's cycles at neighboring dates.
5. **N0 vs H84 only 26% asof overlap** — H84's cycles are almost entirely on a different
   calendar than N0's.

Performance differences BETWEEN candidates thus reflect a mix of horizon duration + calendar
phase + coverage endpoint effects. This is answer **B** to the operator's question.

## Audit 3 — Turnover cost model

LAB008 assumed 100% stock turnover at every rebalance + `(1 + Δexp)` factor. Compared to
actual portfolio turnover computed as `0.5 * sum(|w_t - w_{t-1}|)` over the union of symbols:

| Candidate | Transitions | Mean | Median | p25 | p75 | Min | Max | Fraction ≥ 0.90 | LAB008 assumed | Overstatement per transition |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **N0**  | 18 | 0.500 | 0.477 | 0.434 | 0.571 | 0.316 | 0.740 | **0%** | 1.00 | **-0.500** (50pp) |
| **H21** | 58 | 0.325 | 0.312 | 0.255 | 0.392 | 0.076 | 0.614 | **0%** | 1.00 | **-0.675** (67.5pp) |
| **H42** | 28 | 0.429 | 0.430 | 0.346 | 0.499 | 0.238 | 0.652 | **0%** | 1.00 | **-0.571** (57.1pp) |
| **H84** | 13 | 0.536 | 0.547 | 0.462 | 0.606 | 0.343 | 0.694 | **0%** | 1.00 | **-0.464** (46.4pp) |

**Cumulative cost overstatement at 15 bps (over the full window, ignoring compounding):**

| Candidate | LAB008 assumed (100% × n × 15bps) | Actual (mean_turnover × n × 15bps) | **Overstatement** |
|:-:|:-:|:-:|:-:|
| N0  | 2.70% | 1.35% | **1.35pp** |
| **H21** | 8.70% | 2.83% | **5.87pp** |
| H42 | 4.20% | 1.80% | 2.40pp |
| H84 | 1.95% | 1.05% | 0.90pp |

**The overstatement is UNEVEN across candidates.** H21 overstated by 5.87pp; N0 by only 1.35pp.
The differential of ~4.5pp is exactly the order of magnitude of LAB008's headline "H21 loses
4.4pp CAGR to N0". **A meaningful portion of H21's failure is a model artifact, not evidence.**

### Cost double-counting assessment

The LAB008 cost formula: `cost = current_val × (1.0 + Δexp) × cost_bps`.

Interpretation:
- `1.0` = assumed 100% stock turnover on current portfolio value
- `Δexp` = exposure change (cash-to-stock or stock-to-cash movement)

Is there double-counting? **Not in the strict sense** (the two terms represent conceptually
different capital movements: stock rebalancing vs exposure adjustment). BUT:

1. The `1.0` factor assumes 100% stock turnover ON THE ENTIRE current_val, when actually only
   `exposure_fraction × current_val` is in stocks and only some fraction of that churns.
   Overstates by roughly `(1 - exposure) + exposure × (1 - actual_turnover)` per transition.
2. The `Δexp` term is applied to `current_val` (unadjusted), whereas exposure movement really
   affects only the changed fraction.
3. Sign asymmetry: exposure moving 0.8→0.9 requires ~0.1 additional stock purchases; exposure
   moving 0.9→0.8 requires ~0.1 stock sales. Both incur cost. `|Δexp|` correctly captures the
   one-sided cost, but adding it to a `1.0` baseline still overstates because the baseline
   itself is inflated.

**Net finding**: no double-counting of the same movement, but the baseline 100% assumption is
empirically wrong (actual 32%-54%) and drives systematic over-costing. Corrected cost model
would apply `cost_bps × actual_turnover_fraction × current_val`, plus a separate one-sided
exposure adjustment term.

## Audit 4 — Claim strength

| Claim (verbatim from LAB008 report / commit message) | Classification | Reason |
|---|---|---|
| "Production HOLD=63 remains champion" | **Supported only under preregistered assumptions** | True under LAB008's cost model + calendar. Not proven under a corrected turnover model. |
| "dominates every tested alternative" | **Overstated** | N0 dominates on Sharpe rank AT ALL FOLDS, which is robust. But the raw CAGR gap includes ~4.5pp of cost-model overstatement bias against H21. |
| "validates the choice of 63d" | **Overstated** | Only 3 alternatives tested. Calendar-confounded (Audit 2). Cost model biases against short horizons (Audit 3). "Validation" is too strong; "not-rejected" is the accurate term. |
| "H21 catastrophically fails Gate 6" | **Overstated** | The 5.24pp cost drag for H21 is a MODEL artifact. Under actual turnover 32.5%, H21's cost drag would be roughly (2.83pp - 1.35pp) = 1.48pp — still worse than N0 but no longer "catastrophic". Gate 6 threshold is 1pp; H21 might still fail but by a small margin, not a chasm. |
| "59 rebalances × ~15bps compounds into a 5pp CAGR haircut" | **Unsupported as stated** | The 5pp haircut assumes 100% turnover per rebalance. Actual mean is 32.5%, so the true cost drag from H21's frequency is closer to 1.5-2pp. The catchy "5pp" number is a model artifact. |

## Audit 5 — Decision

**B — LAB008 remains valid only as an assumption-specific experiment (100% turnover + calendar-confounded rebalance dates). A new LAB009-style validation experiment is required before making a production horizon conclusion.**

Rationale:
- Audit 1 (parity): **CLEAN**. N0 faithfully reproduces production. Not a blocker.
- Audit 2 (calendar confound): candidates test horizon duration + calendar phase together.
  N0 vs H42 only 53% overlap; N0 vs H84 only 26% overlap. This is a genuine limitation but does
  not invalidate the sealed evidence — LAB008's preregistration didn't claim calendar isolation.
- Audit 3 (cost model): 100% turnover assumption overstates costs by ~50% for N0, 67.5% for H21.
  Since the cost overstatement is UNEVEN across candidates, it biases the comparison.
- Audit 4: several claims in the LAB008 report/commit go beyond what the evidence supports.

The evidence is internally consistent with its own preregistration but the ASSUMPTIONS
(especially cost model) are strong. A "production horizon conclusion" needs a follow-up experiment
that:
1. Applies a realistic (turnover-weighted) cost model
2. Aligns candidate asofs on a common calendar (or explicitly tests calendar-phase sensitivity)
3. Reports LAB008 headline gap decomposition into: horizon-effect vs calendar-effect vs cost-model-effect

## Recommended follow-up experiment (only if operator opts for decision B path)

**LAB009 — Horizon Recalibration under Realistic Cost Model**

- Same 4 candidates (N0=63, H21, H42, H84) — NOT a new hypothesis, so no strategy-search trial increment
  Actually reconsider: LAB009 changes the cost model, which is a methodology change on the same
  hypotheses — this may or may not increment n_trials depending on operator interpretation. Flag
  for operator decision.
- Cost model: `cost_bps × actual_turnover_t × current_val + cost_bps × |Δexp_t| × current_val`
  where `actual_turnover_t = 0.5 × sum(|w_t - w_{t-1}|)`.
- Calendar-controlled variant: OR restrict to the N0 asof calendar (all candidates sample cycles
  starting at N0's 19 asofs and holding for their respective horizons).
- Same 6 gates, same regime buckets, same PBO policy.

## Restatement of what LAB008 IS and IS NOT

- **IS**: A sealed test of "under the assumption of 100% turnover per rebalance and the
  index-strided calendar starting at closes.index[0], does any of {H21, H42, H84} beat N0=63
  on the 6 preregistered gates under either cash-return assumption?" **Answer: NO.**
- **IS NOT**: A calibrated statement about production horizon choice under realistic trading
  friction, or an isolation of horizon duration from calendar phase.

## Audit artifact status

- Cumulative `strategy_search`: **35** (unchanged)
- Production/Core/Telegram changes: **NONE**
- LAB007 evidence: **unchanged**
- LAB008 sealed preregistration + diagnostics + results report: **unchanged**
- This document is the sole product of the audit.
