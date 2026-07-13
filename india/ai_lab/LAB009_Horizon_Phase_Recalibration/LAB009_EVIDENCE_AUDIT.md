# LAB009 — Evidence Audit (post-execution forensic)

**Audit date:** 2026-07-13 · **Auditor:** operator-directed forensic pass
**Sealed evidence commit:** `6f78104` (NOT modified by this audit)
**Preregistration commit:** `b077767` (NOT modified by this audit)
**Cumulative strategy_search:** **38** (unchanged)

This document is an audit artifact. It does not alter LAB009's sealed preregistration,
diagnostics, or reports. Its purpose is to determine whether LAB009's headline conclusion
("H42 is PROMOTE-ELIGIBLE") is fully supported by the sealed methodology and committed
evidence, or whether one or more methodology/reporting defects weaken that claim.

---

## Section 1 — Preregistration vs Implementation matrix

| Preregistered requirement | Implementation location | Verdict | Impact if wrong |
|---|---|:-:|---|
| 4 deterministic phase offsets per horizon | `horizon_phase_policies.phase_offsets_for` | ✅ PASS | N/A |
| Phase offsets: N0 {0,15,31,47}; H21 {0,5,10,15}; H42 {0,10,21,31}; H84 {0,21,42,63} | Verified by execution log | ✅ PASS | N/A |
| Realistic turnover formula (Formulation B EXTENDED with cash bucket) | `simulate_horizon_phase` lines 116-128 | ✅ PASS (5/5 unit cases verified) | N/A |
| Normalized stock weights before turnover calc | `weights / weights.sum()` | ✅ PASS | N/A |
| Effective exposure-scaled weights `eff_w = exp × w_stock` | `eff_w_dict = {s: exp_at_asof * w ...}` | ✅ PASS | N/A |
| Explicit cash bucket in turnover | `cash_side = |exp_t - exp_{t-1}|` | ✅ PASS | N/A |
| No additive `|Δexp|` double-charge outside cash bucket | Only one cost term applied | ✅ PASS | N/A |
| Common window `common_start = max(first_scorable)` | `compute_common_window` | ✅ PASS | N/A |
| Common window `common_end = min(last_scorable)` | Same | ✅ PASS | N/A |
| Common-window filter applied to asof only, NOT to mature-date | Simulator filters `reg_df["asof"]` only | ⚠️ AMBIGUOUS | See Section 3 |
| Discovery / Confirmation split (2021-07 / 2024-01) | `disc_asofs`, `conf_asofs` in runner | ✅ PASS | N/A |
| Median aggregation across 4 phases | `_aggregate_phases` (statistics.median) | ✅ PASS | N/A |
| Worst-phase metric direction (per-metric sign) | `_worst_by_direction` maps correctly | ✅ PASS | N/A |
| Cost drag = canonical CAGR − stress CAGR (median-phase) | `hr["cost_drag"] = canon_cagr - stress_cagr` | ✅ PASS | N/A |
| 6 gate expressions match preregistration | `lab009.yaml` gates block | ✅ PASS | N/A |
| Both cash assumptions must pass | `overall = all(verdicts[c]["all_pass"] for c in cash_grid)` | ✅ PASS | N/A |
| n_trials=38 from manifest | `read_trial_manifest_count(config.trial_manifest_path)` returns 38 | ✅ PASS | N/A |
| DSR reported for every horizon×phase | `deflated_sharpe(eq.pct_change().dropna(), n_trials=n_trials)` | ✅ PASS | N/A |
| PBO diagnostic ONLY, not a promotion gate | Only 6 preregistered gates evaluated | ✅ PASS | N/A |
| PIT safety: no forward info in selection | `champion_picks` uses `rets.loc[:asof].tail(LOOKBACK)` | ✅ PASS | N/A |
| First-cycle in window `turnover_t=0` matches "first cycle assumed zero prior position" | Simulator filters BEFORE prev-init | ⚠️ AMBIGUOUS | See Section 2 |
| PBO wording "UNDER-adjusts for dependence" | Report + preregistration language | ⚠️ REPORTING DEFECT | See Section 8 |

**Summary:** 17/20 items PASS unambiguously. 3 items require deeper audit → Sections 2, 3, 8.

---

## Section 2 — Turnover accounting forensic check

### Formula unit tests (all PASS with tolerance 1e-9)

| Case | Prev stock w · exp | Cur stock w · exp | Expected turnover | Computed | PASS |
|:-:|---|---|:-:|:-:|:-:|
| A | {A:0.5,B:0.5} · 0.8 | {C:0.5,D:0.5} · 0.9 | 0.90 | 0.90 | ✅ |
| B | {A:0.5,B:0.5} · 0.8 | {A:0.5,B:0.5} · 0.8 | 0.00 | 0.00 | ✅ |
| C | {A:0.5,B:0.5} · 0.8 | {A:0.5,B:0.5} · 0.9 | 0.10 | 0.10 | ✅ |
| D | {A:1.0} · 1.0 | {B:1.0} · 1.0 | 1.00 | 1.00 | ✅ |
| E | {A:1.0} · 0.8 | {A:0.5,B:0.5} · 0.8 | 0.40 | 0.40 | ✅ |

Turnover formula matches Formulation B EXTENDED spec exactly.

### First-cycle-in-window audit

**Finding:** The simulator filters `reg_df` to the common window BEFORE initializing
`prev_eff_w = None`. This means for phases with cycles OUTSIDE the common window that would
have transitioned INTO the first in-window cycle, the transition-cost is **NOT charged**.

Interpretation ambiguity: preregistration says "first cycle assumed zero prior position — no
round-trip cost". This can mean:
- **(A)** First cycle in FULL history (first log_rec ever). Post-common-window filtering,
  the "first in-window cycle" is NOT the first in history → its transition SHOULD be charged.
- **(B)** First cycle in EVALUATION WINDOW. Then charging zero is consistent with
  implementation.

**Implementation chose interpretation (B).**

Quantified impact (per config, pre-window cycles from Audit report table):

| Cand | H | Phase | Pre-window cycles | Omitted turnover cost estimate |
|:-:|:-:|:-:|:-:|:-:|
| H21 | 21 | 0 | 3 | ~9 bps (mean 0.325 × 15bps × 1 transition) |
| H21 | 21 | 5 | 3 | ~9 bps |
| H21 | 21 | 10 | 3 | ~9 bps |
| H21 | 21 | 15 | 4 | ~9 bps |
| H42 | 42 | 0 | 2 | ~6 bps |
| H42 | 42 | 10 | 2 | ~6 bps |
| H42 | 42 | 21 | 1 | ~6 bps |
| H42 | 42 | 31 | 1 | ~6 bps |
| N0  | 63 | 0 | 1 | ~7 bps |
| N0  | 63 | 15 | 1 | ~7 bps |
| N0  | 63 | 31 | 1 | ~7 bps |
| N0  | 63 | 47 | 1 | ~7 bps |
| H84 | 84 | 0 | 1 | ~8 bps |
| H84 | 84 | 21 | 0 | 0 |
| H84 | 84 | 42 | 1 | ~8 bps |
| H84 | 84 | 63 | 1 | ~8 bps |

**Uniform ~1 free transition across all configs** (H21 has more pre-window cycles, but each
only saves ONE transition — the FIRST in-window transition — regardless). Impact is
essentially uniform across horizons and does NOT materially bias comparisons.

**Verdict**: implementation is INTERNALLY CONSISTENT with interpretation (B) but the
preregistration language does not unambiguously state (A) vs (B). Reporting/prereg wording
should be tightened; the quantitative impact is negligible (~7-9 bps uniform bias).

---

## Section 3 — Common evaluation window: coverage inequality

**Verified**: `common_start = 2021-10-01`, `common_end = 2025-11-25`.

**CRITICAL FINDING**: Common-window filter is on **asof only**, NOT on `mature_date`. Cycles
whose asof ≤ common_end are INCLUDED, and their realized returns extend up to `asof + horizon`
past `common_end`.

Days past common_end by config (last cycle's mature - common_end):

| Cand | Phase 0 | Phase 1 | Phase 2 | Phase 3 |
|:-:|:-:|:-:|:-:|:-:|
| H21 | +29d | +7d | +14d | +21d |
| H42 | +63d | +14d | +29d | +44d |
| N0  | +63d | +83d | +14d | +37d |
| H84 | **+63d** | **+91d** | **+122d** | +29d |

Trading-day coverage of the resulting equity curves:

| Cand | Trading days by phase | Min | Max | Spread |
|:-:|:-:|:-:|:-:|:-:|
| H21 | 1051 / 1030 / 1030 / 1030 | 1030 | 1051 | 21d |
| H42 | 1051 / 1009 / 1051 / 1051 | 1009 | 1051 | 42d |
| N0  | 1072 / 1072 / 1009 / 1009 | 1009 | **1072** | 63d |
| H84 | 1009 / 1093 / **1093** / 1009 | 1009 | **1093** | 84d |

**H84 phases 21 and 42 get 1093 trading days; some N0/H42 phases get 1009. Coverage
differential = 84 trading days (~4 months, one full H84 cycle).**

Preregistration promised: "**identical evaluation coverage**". Implementation delivered:
identical rebalance-asof windows but non-identical realized-return coverage. Longer horizons
get MORE terminal return extending past the common window.

**Impact on H42 promotion:**
- H42's phase 0 extends 63 days past common_end → captures Nov 25 – Jan 27 returns
- N0's phase 31 stops 14 days past common_end → captures only Nov 25 – Dec 9 returns
- These extra 2 months of H42 coverage vs N0 include Dec 2025 – Jan 2026 market activity
- Sign of bias unclear — depends on what happened Dec 2025 – Jan 2026 for held picks
- Magnitude estimate: 84 trading days = ~8% of the 1009-day window. On a full-window CAGR
  of ~11%, at most ~0.9pp of the CAGR figure comes from the non-common terminal segment.

**This is an implementation defect against the sealed "identical evaluation coverage" claim.**
The defect is symmetric in direction (both N0 and H42 get extended terminal windows for some
phases), so it does not systematically favor one candidate over the other. But it violates
the promised methodology and could tip tight gate margins.

---

## Section 4 — Phase top-2 Sharpe interpretation (Gate 5)

The preregistration language "fraction of phases ranked top-2 by Sharpe" was ambiguous about
what "top-2 of what". Implementation chose **phase-INDEX pairing** (each candidate's phase i
vs other candidates' phase i, top-2 out of 4).

Three interpretations tested (diagnostic only — sealed gate uses A):

| Cand | A: phase-index pair (LAB009) | B: vs other horizons' median | C: global rank across 16 |
|:-:|:-:|:-:|:-:|
| N0  | 0.750 | 0.750 | 0.750 |
| H21 | 0.000 | 0.000 | 0.000 |
| **H42** | **0.750** | **0.750** | **0.750** |
| H84 | 0.500 | 0.500 | 0.500 |

**H42's Gate 5 PASS is ROBUST** — 0.75 top-2 fraction under all three interpretations, at both
cash assumptions. Not fragile.

Note: N0 at cash=6% under interpretation A gives 0.50 (vs 0.75 under B and C). N0 borderline
under one interpretation but this does not affect candidate promotion.

---

## Section 5 — Gate recomputation from CSV (independent of report)

Recomputed all six gates directly from `lab009_diagnostics_2026-07-13.csv` median/worst rows.

### H42 exact margins (cash=0%, canonical 15bps)

| Gate | LHS | RHS | Margin | Verdict |
|---|---:|---:|---:|:-:|
| G1 median conf Sharpe ≥ N0 | +0.7581 | +0.5710 | **+0.1871** | ✅ PASS |
| G2 median full CAGR delta pp ≥ -1.0 | -0.111pp | -1.000pp | **+0.889pp** | ✅ PASS |
| **G3 median full Sharpe delta ≥ -0.05** | -0.023 | -0.050 | **+0.027** ⚠ | ✅ PASS (tight) |
| G4 worst-phase full MaxDD delta pp ≥ -3.0 | -1.741pp | -3.000pp | +1.259pp | ✅ PASS |
| G5 median phase_top2 ≥ 0.50 | 0.7500 | 0.5000 | +0.2500 | ✅ PASS |
| G6 cost drag delta pp ≤ +1.0 | +0.219pp | +1.000pp | -0.781pp | ✅ PASS |

### H42 exact margins (cash=6%)

| Gate | Margin |
|---|---:|
| G1 | +0.1861 |
| G2 | +0.9988 |
| **G3** | **+0.0337** ⚠ |
| G4 | +1.4001 |
| G5 | +0.2500 |
| G6 | -0.7773 |

**Gate 3 (Sharpe delta) is the tightest — H42 passes by only 0.027 at cash=0%, 0.034 at
cash=6%.** The coverage inequality identified in Section 3 (up to 84 trading days differential)
could plausibly shift H42's Sharpe by more than 0.03 if the extended terminal window
contributed materially to Sharpe.

### H84 exactly-on-boundary failure

H84 fails Gate 3 by **exactly -0.0500 at cash=0%** and -0.0503 at cash=6%. H84 is one hair
from passing. This tight boundary means the coverage inequality could also flip H84's verdict.

### H21 comfortable failures

H21 fails G2 by 0.91pp and G3 by 0.11 — comfortable margins, not sensitive to coverage.

---

## Section 6 — Metric / equity concatenation audit

### Cycle overlap/gap by config

**All 16 configs**: cycle boundaries are exact (`mature_date_t == asof_{t+1}`). No overlaps,
no gaps. `cycle_equity[cycle_equity.index > equity.index[-1]]` correctly drops the shared
boundary bar without discarding data.

### Cost deduction accounting

- Cost applied at each in-window cycle boundary AFTER the first (see Section 2 first-cycle
  discussion).
- Applied via `current_val -= transaction_cost` **before** the new cycle's stock+cash curve
  is scaled by `current_val`. Correct — cost paid at rebalance, before position accrual.
- No double deduction.

### `current_val` transitions

Traced through the simulator: `current_val = cycle_end_val` at end of each cycle, becomes the
base for the next cycle's cost + scaling. Consistent.

**Verdict**: metric and equity concatenation is internally consistent. No bookkeeping bugs.

---

## Section 7 — DSR audit

- `n_trials` read from `india/ai_lab/trial_manifest.md`. Verified: `cumulative_strategy_search:
  38` at line 19. ✅
- DSR computed per horizon×phase from that config's daily return series.
- **Horizon-level median DSR is NOT a rigorously statistical horizon-level DSR.** It is
  simply the median of 4 phase-level DSR values. This is a heuristic summary, not a
  properly-derived aggregate significance test. Report should state this explicitly.
- No DSR-based promotion gate exists in LAB009 (Sharpe-based gates 1 and 3 serve that role
  at aggregate level).

**Verdict**: DSR sourcing PASS. Horizon-level median DSR is a valid heuristic but should be
labelled as such — not treated as a horizon-level statistical significance test.

---

## Section 8 — PBO wording audit

Preregistration and report say: "Treating N=16 as independent strategy hypotheses in CSCV
UNDER-adjusts for dependence".

**Mathematical assessment**: this wording is ambiguous and potentially misleading in direction.

- CSCV under independence assumption: expected PBO ≈ 0.5 under null
- Under high correlation between configs: IS→OOS ranks are more stable → PBO tends LOWER
  than under independence (correlated winners stay winners)
- Therefore N=16 correlated configs → PBO reported UNDER independence assumption is
  BIASED LOWER than under-perfect-correlation-assumption; the reported PBO=0.84 could
  UNDERSTATE the true multi-testing search burden if the phase-level configs are only
  weakly correlated
- OR: if configs are strongly correlated (essentially 3 hypotheses replicated 4 times each),
  the reported PBO is closer to the "true" PBO of a 3-strategy search, and no adjustment is
  needed

**"UNDER-adjusts for dependence" without specifying direction is not technically correct**.
Dependence does NOT create a simple monotonic bias on PBO — the direction depends on
whether the dependence is with the market noise vs the search space.

**Regardless of the caveat direction, PBO = 0.84 is HIGH.** The safer read: LAB009's IS-best
config is unstable across the 8-fold CSCV split, with ~84% of splits placing the IS-winner
in the bottom half OOS. This is a strong signal of fragility that PBO's caveat cannot
explain away.

**Verdict: REPORTING DEFECT** — the "UNDER-adjusts for dependence" wording overreached and
may have unintentionally softened the reader's concern about PBO=0.84. A rewrite should
say: "*PBO's interpretation under phase-dependent configs is not straightforward; PBO is
reported as diagnostic only. However, PBO = 0.84 is a HIGH value irrespective of the
dependence caveat — the IS-best is not stable OOS.*"

This does not by itself invalidate H42's gate PASS, but it does argue for caution in
interpreting LAB009 as a strong endorsement.

---

## Section 9 — Execution-count audit (Unicode-fail rerun)

First LAB009 execution attempt failed with:
```
File "run_lab009.py", line 117, in main
    print(f"    {cid} H={h:>2}d phase={p:>2}: {reg['rec_id'].nunique()} cycles "
UnicodeEncodeError: 'charmap' codec can't encode character '→'
```

**Line 117 is inside the "Building per-(horizon, phase) registries..." print loop.** This
occurs BEFORE the simulation loop (line ~200) and BEFORE gate evaluation.

- No candidate simulation was executed before the failure.
- No performance metrics were computed.
- No gates evaluated.
- No PBO / DSR calculated.

Fix: sed replaced `→` (U+2192) with `->` in run_lab009.py (cosmetic string change only, no
research logic modified). Then re-executed.

**Verdict: PASS.** The "execute exactly once" invariant is preserved. Only ONE genuine
candidate execution occurred (the second run). No result was observed and re-run.

---

## Section 10 — Production safety audit

`git diff --name-only a2fa686..6f78104` (LAB009 preregistration + results commits):

```
india/ai_lab/LAB009_Horizon_Phase_Recalibration/preregistration.md      (new)
india/ai_lab/LAB009_Horizon_Phase_Recalibration/lab009.yaml             (new)
india/ai_lab/LAB009_Horizon_Phase_Recalibration/horizon_phase_policies.py (new)
india/ai_lab/LAB009_Horizon_Phase_Recalibration/run_lab009.py           (new)
india/ai_lab/LAB009_Horizon_Phase_Recalibration/reports/lab009_2026-07-13.md   (new)
india/ai_lab/LAB009_Horizon_Phase_Recalibration/reports/lab009_diagnostics_2026-07-13.csv (new)
india/ai_lab/lab_runner.py       (framework: recursive _wrap_ns extension)
india/ai_lab/trial_manifest.md   (35 → 38)
```

Production/Core/Telegram files NOT touched by LAB009:
- ✅ `india/recommendation_registry.py` — HOLD=63 still at line 31 (verified)
- ✅ `india/recommendation_generator.py` — rebal=63 untouched
- ✅ `india/arjuna_v2.py` — untouched
- ✅ `india/confidence_engine.py` — untouched
- ✅ `india/telegram_notify.py` — untouched
- ✅ `india/exit_reasons.py` — untouched

**Verdict**: PRODUCTION UNTOUCHED. Framework extension (`_wrap_ns` recursive) is generic and
does not alter Lab outcomes for previous experiments.

---

## Section 11 — Findings summary

### A. Preregistration defects

- **Section 2 first-cycle wording**: "first cycle assumed zero prior position" is ambiguous
  about pre-vs-post common-window filtering. Should specify unambiguously in future prereg.

### B. Implementation defects

- **Section 3 coverage inequality**: common-window filter applied to `asof` only, allowing
  cycles to mature up to 122 days past `common_end`. Preregistration promised "identical
  evaluation coverage" — implementation delivers non-identical realized-return coverage
  (trading-day span 1009-1093 across configs). Direction of impact on gate verdicts is
  ambiguous (not systematically favoring one candidate).

### C. Reporting defects

- **Section 8 PBO wording**: "UNDER-adjusts for dependence" is ambiguous in direction and
  may have softened reader's concern about the actually-HIGH PBO=0.84. Report should be
  rewritten to acknowledge that PBO 0.84 signals fragility regardless of dependence caveat.
- **Section 7 horizon-level DSR labeling**: "median DSR" across phases is a heuristic
  summary, not a horizon-level statistical significance test. Should be labelled as such.

### D. Statistical cautions only

- **Section 5 tight Gate 3 margin**: H42 passes Gate 3 by only +0.027 (cash=0%) and +0.034
  (cash=6%). Small perturbations to methodology (especially coverage inequality from
  Section 3) could flip H42's verdict.
- **Section 5 H84 boundary failure**: H84 fails Gate 3 by exactly -0.0500 at cash=0% — one
  hair from passing.

### E. No issue

- Turnover formula (Section 2) — verified correct on 5 unit tests
- Cycle overlap/gap (Section 6) — clean
- DSR sourcing (Section 7) — correctly reads manifest=38
- Execution count (Section 9) — Unicode-fail rerun did NOT compute any performance
- Production safety (Section 10) — untouched
- Gate 5 (Section 4) — H42 robust under all 3 interpretations

---

## Section 12 — Final audit decision

**B — LAB009 is directionally informative, but one or more methodology ambiguities weaken the
H42 promotion claim. Production remains at HOLD=63; new validation experiment (LAB010) is
required before any consideration of a horizon change.**

Rationale:
- **Turnover formula is correct** (5/5 unit tests pass)
- **Gate arithmetic is correct** (independent CSV recomputation matches report)
- **Production untouched** (no Core/Telegram files modified)
- **H42's gate margins are asymmetric**: G1/G4/G5/G6 comfortable; **G3 (Sharpe delta) tight at +0.027**
- **Section 3 coverage inequality is a real implementation defect** against the sealed
  "identical evaluation coverage" promise. Impact: up to 84 trading days extra coverage for
  H84 vs the shortest N0 phase. Direction of impact on H42 vs N0 is unclear but the tight
  Gate 3 margin is potentially sensitive.
- **PBO 0.84 is HIGH**. The preregistration's "dependence caveat" cannot explain away that
  the IS-best config is bottom-half OOS in 84% of CSCV splits. Diagnostic-only status stands,
  but this is a genuine fragility signal.

The evidence supports H42 as a NOTABLE candidate (median metrics nearly tie N0; robust
across phase-top-2 interpretations; passes all 6 gates), but it does NOT constitute
promotion-quality evidence for a production change.

---

## Section 13 — Recommended next experiment (LAB010)

**Do NOT create LAB010 in this audit — the operator will preregister/execute separately.**

Concept for the operator's consideration:

**LAB010 — Common-Terminal-Window Horizon Retest with PBO Independence Audit**

Fixes for the two Section 3 / Section 8 findings:

1. **Common window on realized-return dates, not asof**: `common_end` becomes the earliest
   *mature_date* across all 16 configs. Cycles whose *mature_date > common_end* are dropped.
   Equity curves terminate on identical dates for every config.
2. **Explicit PBO dependence analysis**: compute effective-N via correlation eigenvalue decay
   across the 16 phase-config return streams; report both the naive PBO and a
   dependence-adjusted variant with clear direction of bias.
3. **First-cycle handling clarified in preregistration**: state explicitly whether the "first
   cycle assumed zero prior position" refers to full-history-first or window-first.
4. Trial count question flagged for operator: same 3 hypotheses (H21/H42/H84) under a
   methodology change — count as new 3 trials (→ 41) or as no-new-search (still 38)? Recommend
   +3 = 41 because the common-window methodology is a research-critical parameter.

---

## Section 14 — Audit artifact status

- Cumulative `strategy_search`: **38** (unchanged)
- Production / Core / Telegram: **NONE modified**
- LAB008 evidence: **unchanged**
- LAB009 sealed preregistration + diagnostics + results report: **unchanged**
- This document is the sole product of the audit.
