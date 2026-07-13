# LAB009 — Preregistration Addendum: Period Boundary Correction

**Sealed 2026-07-13** (after H84 forensic audit, before corrected execution)

Companion to `preregistration.md` (sealed `b077767`) and `preregistration_maturity_boundary_addendum.md`
(sealed `3333282`). Both prior preregistrations remain INTACT as historical evidence.

This addendum documents a locked correction to LAB009's discovery/confirmation period metric
classification after a discovered post-execution defect (H84 forensic audit, chat 2026-07-13).

## Origin

The H84 forensic audit revealed the LAB009 maturity-corrected run classifies cycles into
discovery/confirmation periods using ASOF DATE ONLY. Cycles whose `asof` fell inside the
declared period but whose `mature_date` extended past `disc_end` or `conf_end` were included,
contributing realized returns from OUTSIDE the declared window. This is the same class of
maturity-boundary defect previously fixed at common_end.

Per operator direction, this defect must be corrected before any LAB009 promotion claim can be
trusted for production consideration.

## What this addendum LOCKS

### Corrected period cycle-inclusion semantics

A cycle belongs to the discovery period metrics iff:
```
common_start <= asof   AND   mature_date <= disc_end
```

A cycle belongs to the confirmation period metrics iff:
```
conf_start <= asof     AND   mature_date <= conf_end
```

Where sealed values are:
- `common_start` = corrected common window start = 2021-10-01 (unchanged)
- `disc_end` = 2023-10-13 (unchanged from original preregistration)
- `conf_start` = 2024-01-15 (unchanged from original preregistration)
- `conf_end` = 2026-01-27 (unchanged from original preregistration)

### Post-simulation assertions (hard fails)

For each config's period-metric computation, the runner enforces:
- No discovery-included cycle has `mature_date > disc_end`
- No confirmation-included cycle has `mature_date > conf_end`
- No equity observation used for discovery period metrics falls after `disc_end`
- No equity observation used for confirmation period metrics falls after `conf_end`
- No period-metric equity observation begins before its `period_start`

### Corrected output filename templates (sealed BEFORE execution)

`lab009.yaml`:
```yaml
reporting:
  report_name_template: "lab009_period_corrected_{date}.md"
  diagnostics_name_template: "lab009_period_corrected_diagnostics_{date}.csv"
```

Original LAB009 and maturity-corrected outputs are preserved and NOT overwritten.

## What this addendum PRESERVES verbatim

- Candidate set: N0=63 (control), H21, H42, H84 — no additions, no removals
- Horizon set: 63, 21, 42, 84 — unchanged
- Phase offsets per horizon: `[0, floor(H/4), floor(H/2), floor(3H/4)]`
  - N0: {0, 15, 31, 47}
  - H21: {0, 5, 10, 15}
  - H42: {0, 10, 21, 31}
  - H84: {0, 21, 42, 63}
- Cash returns: `[0.0, 0.06]`
- Cost grid: `[15, 30, 50]`, canonical=15, stress=50
- Trading days per year: 252
- Turnover formula (Formulation B EXTENDED) — unchanged; worked example must still produce 0.90
- Six promotion gate expressions BYTE-IDENTICAL:
  - Gate 1: `cand.median.conf.sharpe >= n0.median.conf.sharpe`
  - Gate 2: `cand.median.full.cagr >= n0.median.full.cagr - 0.01`
  - Gate 3: `cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
  - Gate 4: `cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03`
  - Gate 5: `cand.phase_top2_sharpe >= 0.50`
  - Gate 6: `(cand.cost_drag - n0.cost_drag) <= 0.01`
- Gate thresholds: unchanged
- Common window rule (maturity-corrected): `common_end = min(each config latest mature_date)`
  = 2026-03-27 — UNCHANGED from `3333282`
- Regime bucket definitions: Strong (≥0.90), Neutral [0.65, 0.90), Weak [0, 0.65)
- DSR trial-source: `manifest` reading `cumulative_strategy_search: 38`
- PBO diagnostic-only status
- PIT safety requirements

## Trial-count invariant

**`cumulative_strategy_search` remains 38.** No new candidates. Correction is a
period-metric membership refinement on the same hypotheses.

## Production invariant

- `india/recommendation_registry.py` — `HOLD = 63` UNCHANGED
- `india/recommendation_generator.py` — `rebal = 63` UNCHANGED
- Core (`arjuna_v2.py`, `confidence_engine.py`) — UNCHANGED
- Telegram (`telegram_notify.py`, `exit_reasons.py`) — UNCHANGED

## What is NEW in the corrected code

Minimal changes to `india/ai_lab/LAB009_Horizon_Phase_Recalibration/run_lab009.py`:

1. New helper `select_period_cycles(meta, period_start, period_end)` returns the set of asofs
   whose cycles have `asof >= period_start AND mature_date <= period_end` — full containment.
2. Discovery period asof set built via `select_period_cycles(meta, common_start, disc_end)`.
3. Confirmation period asof set built via `select_period_cycles(meta, conf_start, conf_end)`.
4. Post-computation assertion: for each period, all included cycles have `mature_date` within
   the declared `period_end`.

No changes to:
- `simulate_horizon_phase()` behavior (full-period simulator unchanged)
- Portfolio construction, ranking, exposure, turnover, costs, cash return
- Cycle generation
- Candidate definitions
- Gate evaluator, gate expressions, thresholds
- `lab_metrics.py period_metrics()` (still generic — the caller filters cycles correctly)
- Regime bucket assignment
- DSR / PBO computation

## Deterministic tests LOCKED to run before corrected execution

All 15 tests below must PASS. If any fail, corrected execution is aborted.

1. Confirmation cycle with `asof <= conf_end` but `mature_date > conf_end` is EXCLUDED
2. Discovery cycle crossing `disc_end` is EXCLUDED
3. A fully contained discovery cycle is INCLUDED
4. A fully contained confirmation cycle is INCLUDED
5. No confirmation-metric equity observation exceeds `conf_end`
6. No discovery-metric equity observation exceeds `disc_end`
7. No period-metric equity observation begins before its `period_start`
8. H63_P31_2025-12-09 is EXCLUDED from N0 phase 31 confirmation metrics
9. All six gate expressions remain BYTE-IDENTICAL to sealed LAB009 yaml
10. Candidate / horizon / phase definitions unchanged
11. Cash and cost grids unchanged
12. Turnover worked example remains 0.90
13. `cumulative_strategy_search` remains 38
14. All 8 previous maturity-correction tests still PASS
15. All 17 LAB framework tests still PASS

## Post-seal commit convention

- **Seal commit** (this addendum + audit + code correction + tests + new output filename
  templates) — pushed BEFORE corrected execution. Message: `LAB009 period-boundary correction seal`
- **Results commit** (LATER, only after operator approval) — corrected report + corrected
  diagnostics. Message: `LAB009 period-boundary correction results`

## No outcome assumed

The corrected execution may reverse H21, H42, or H84 verdicts in any direction. This addendum
does not predict or assume an outcome — it only locks the correction rigorously before rerun.

## Sealed 2026-07-13

Author: operator + assistant · Change ID: LAB009-PERIOD-BOUNDARY-CORRECTION-V1
