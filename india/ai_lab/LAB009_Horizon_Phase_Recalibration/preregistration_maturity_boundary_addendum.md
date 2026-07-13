# LAB009 — Preregistration Addendum: Maturity-Boundary Correction

**Sealed 2026-07-13** (after LAB009 evidence audit `1210c77`, before corrected rerun)

This addendum is companion to the original sealed preregistration
(`preregistration.md`, committed as part of `b077767`). The original preregistration remains
INTACT as historical evidence. This addendum documents a locked correction to LAB009's
evaluation-window methodology after a discovered defect.

## Origin

The LAB009 evidence audit (commit `1210c77`) identified that LAB009's implemented
`compute_common_window()` derives `common_end` from `min(each config's latest ASOF)`, and
the simulator filters cycles on `asof <= common_end` only. Because a cycle's realized-return
path extends from `asof` through `mature_date`, and different horizons have different maturity
lengths (21/42/63/84 days), the LAB009 evidence includes cycles whose returns extend up to
122 days past the declared `common_end`. This directly contradicts the sealed preregistration's
promise of "identical evaluation coverage".

Per operator direction, this defect must be corrected before the LAB009 promotion claim is
treated as production-relevant evidence.

## What this addendum LOCKS

The following methodology change is sealed BEFORE corrected LAB009 execution:

### Corrected common evaluation window

- `common_start = max(each config's earliest scorable asof)` — UNCHANGED from original prereg
- `common_end = min(each config's LATEST mature_date)` — CORRECTED (was min of latest asof)

For LAB009 registries, these are:
- `common_start = 2021-10-01` (unchanged)
- `common_end = 2026-03-27` (was 2025-11-25 under original rule; H84 phase 42 is the binding config)

### Corrected cycle-inclusion rule

For every horizon × phase simulation, a cycle is included in the promotion-driving evaluation
if **BOTH**:
- `asof >= common_start`, AND
- `mature_date <= common_end`

Cycles with `asof <= common_end` but `mature_date > common_end` are EXCLUDED.

### Corrected equity bounds

For every returned equity series:
- `assert equity.index.min() >= common_start`
- `assert equity.index.max() <= common_end`

## What this addendum PRESERVES verbatim

The following are UNCHANGED from `preregistration.md` and remain sealed:

- Candidate set: N0=63 (control), H21, H42, H84 — no additions, no removals
- Phase offsets per horizon: `[0, floor(H/4), floor(H/2), floor(3H/4)]`
  - N0: {0, 15, 31, 47}
  - H21: {0, 5, 10, 15}
  - H42: {0, 10, 21, 31}
  - H84: {0, 21, 42, 63}
- Realistic turnover cost model: Formulation B EXTENDED (`0.5 × (Σ|Δ eff_w| + |Δexp|)`),
  single cost term, no additive `|Δexp|`. Verified unchanged by unit tests.
- Cash returns: `[0.0, 0.06]` — dual primary
- Cost grid: `[15, 30, 50]` — canonical=15, stress=50
- Six promotion gate expressions, byte-identical:
  - Gate 1: `cand.median.conf.sharpe >= n0.median.conf.sharpe`
  - Gate 2: `cand.median.full.cagr >= n0.median.full.cagr - 0.01`
  - Gate 3: `cand.median.full.sharpe >= n0.median.full.sharpe - 0.05`
  - Gate 4: `cand.worst.full.max_dd >= n0.worst.full.max_dd - 0.03`
  - Gate 5: `cand.phase_top2_sharpe >= 0.50`
  - Gate 6: `(cand.cost_drag - n0.cost_drag) <= 0.01`
- Gate thresholds: identical (-0.01, -0.05, -0.03, 0.50, 0.01)
- Discovery/Confirmation dates: 2021-07-01 → 2023-10-13 / 2024-01-15 → 2026-01-27
- Regime buckets: Strong (≥0.90), Neutral [0.65, 0.90), Weak [0, 0.65)
- DSR trial-source: `manifest` — reading `cumulative_strategy_search: 38`
- PBO diagnostic-only status
- PIT safety requirements

## Trial-count invariant

**`cumulative_strategy_search` remains 38.** No new candidates, no new hypotheses. This
correction fixes a computed evaluation-boundary defect on the SAME hypotheses; it does not
introduce new strategy trials.

## Production invariant

- `india/recommendation_registry.py` — `HOLD = 63` UNCHANGED
- `india/recommendation_generator.py` — `rebal = 63` UNCHANGED
- Core (`arjuna_v2.py`, `confidence_engine.py`) — UNCHANGED
- Telegram (`telegram_notify.py`, `exit_reasons.py`) — UNCHANGED

## What is NEW in the corrected code

Minimal changes to `india/ai_lab/LAB009_Horizon_Phase_Recalibration/horizon_phase_policies.py`:

1. `compute_common_window()` returns `common_end = min(each config's latest mature_date)`
2. `simulate_horizon_phase()` filters registry with **BOTH** `asof >= common_start` AND
   `mature_date <= common_end`
3. Post-simulation assertion: `assert max(equity.index) <= common_end` (raises loud on
   violation — no silent behavior)
4. Cycle-inclusion assertion: `assert no included cycle has mature_date > common_end`

No changes to the generic framework (`lab_config.py`, `lab_runner.py`, `lab_metrics.py`,
`lab_reporting.py`, `lab_expression.py`).

## Corrected output filenames (distinct — original evidence preserved)

- Report: `reports/lab009_maturity_corrected_2026-07-13.md`
- Diagnostics: `reports/lab009_maturity_corrected_diagnostics_2026-07-13.csv`

Original `reports/lab009_2026-07-13.md` and `.csv` are NOT overwritten.

## Deterministic tests LOCKED to run before corrected execution

1. `compute_common_window()` returns `common_end` based on `min(last mature_date)` across
   the 16 configs — verified equal to 2026-03-27 on LAB009's registries
2. No included cycle in any config has `mature_date > common_end` after filtering
3. No returned equity index exceeds `common_end`
4. Cycle with `asof <= common_end` but `mature_date > common_end` is correctly EXCLUDED
5. First included cycle has `turnover_t == 0` (retains sealed convention)
6. Turnover Formulation B EXTENDED matches worked example: exp 0.8→0.9,
   {A:0.5,B:0.5}→{C:0.5,D:0.5} produces turnover = 0.90 within numerical tolerance
7. Trial manifest reports `cumulative_strategy_search: 38`
8. All six gate expressions byte-identical to `lab009.yaml`

If ANY test fails, corrected execution is aborted and this correction is treated as
methodology-defective.

## Post-correction commit convention

- **Seal commit** (this addendum + audit + code correction + tests) — pushed BEFORE corrected
  execution. Message: `LAB009 maturity-boundary correction seal`
- **Results commit** — corrected report + corrected diagnostics + any measured-facts
  addendum update. Message: `LAB009 maturity-boundary correction results`

## Sealed 2026-07-13

Author: operator + assistant · Change ID: LAB009-MATURITY-CORRECTION-V1
