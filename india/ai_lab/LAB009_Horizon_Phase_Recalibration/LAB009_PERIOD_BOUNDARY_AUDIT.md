# LAB009 — Period Boundary Defect Audit

**Audit date:** 2026-07-13 (post-H84 forensic audit)
**Prior LAB009 commits:**
- `b077767` — LAB009 preregistration
- `6f78104` — LAB009 evidence/results
- `1210c77` — LAB009 evidence audit
- `3333282` — Maturity-boundary correction seal
- `e8d13ae` — Maturity-boundary correction results

**Cumulative strategy_search:** **38** (unchanged — this correction is NOT a new hypothesis)

---

## 1. Exact defect

`india/ai_lab/LAB009_Horizon_Phase_Recalibration/run_lab009.py` lines 174-179 classify a cycle's
membership in discovery/confirmation using **ASOF ONLY**:

```python
disc_asofs = {pd.Timestamp(m["asof"]).normalize() for m in meta
              if pd.Timestamp(m["asof"]).normalize() <= disc_end}
conf_asofs = {pd.Timestamp(m["asof"]).normalize() for m in meta
              if pd.Timestamp(m["asof"]).normalize() >= conf_start}
disc = period_metrics(eq, meta, disc_asofs, trading_days=trading_days)
conf = period_metrics(eq, meta, conf_asofs, trading_days=trading_days)
```

Then `period_metrics` in `lab_metrics.py:97-108` builds windows `(asof, mature_date)` per cycle
and slices `equity.loc[asof:mature]` from the full equity curve — including bars past the
declared `disc_end` / `conf_end` if the cycle's `mature_date` extends there.

**Same class of maturity-boundary defect that was corrected at common_end (commit `3333282`),
now inside the discovery/confirmation split.**

## 2. Boundary audit matrix

| Metric family | Cycle classification | Realized-return start | Realized-return end | Bounded by declared period end? | Promotion-driving? |
|---|---|---|---|:-:|:-:|
| **full** | ALL simulated cycles | asof (or asof+1 for non-first) | mature_date | ✅ bounded by common_end=2026-03-27 (corrected) | YES (Gates 2, 3) |
| **discovery** | `asof <= disc_end (2023-10-13)` | asof or asof+1 | mature_date | ❌ **DEFECT**: mature_date can exceed disc_end | (Diagnostic — not in any gate) |
| **confirmation** | `asof >= conf_start (2024-01-15)` — ONE-SIDED | asof or asof+1 | mature_date | ❌ **DEFECT**: mature_date can exceed conf_end (2026-01-27); AND no upper bound on asof either | **YES (Gate 1)** |
| **regime** | regime label match (no period constraint) | asof or asof+1 | mature_date | ✅ bounded by common_end (via full simulation) | Diagnostic only |
| **DSR** | Daily returns of full equity curve | common_start segment | common_end | ✅ bounded by common_end | (Reported; not a hardcoded gate) |
| **PBO** | Cross-config daily returns | common_start | common_end | ✅ bounded by common_end | Diagnostic only |

**Two rows flagged DEFECT.** Confirmation is Gate 1 promotion-driving.

## 3. Discovery-boundary offender count

Cycles classified as discovery (`asof ≤ 2023-10-13`) but whose `mature_date > 2023-10-13`:

Per audit computation (from committed diagnostics + cycle registries):
- **16/16 configs affected.** Every config has at least one discovery-classified cycle
  whose maturity crosses `disc_end`.
- Discovery-boundary defect impact is Diagnostic only (discovery metrics do not drive any
  promotion gate).

## 4. Confirmation-boundary offender count

Cycles classified as confirmation (`asof ≥ 2024-01-15`) but whose `mature_date > 2026-01-27`:

- **12/16 configs affected.**
- Total confirmation-classified cycles with maturity past `conf_end`: **12**
- Days past `conf_end` range: **+6 to +59**
- **This directly affects Gate 1 (median confirmation Sharpe).**

Key example (already established in H84 forensic audit):
- N0 phase 31 cycle `H63_P31_2025-12-09` (asof 2025-12-09, mature 2026-03-11): classified as
  confirmation; matures 43 days past `conf_end` (2026-01-27); its -4.08% weighted return
  dropped N0's confirmation Sharpe as well as full-period Sharpe. This cycle is EXACTLY the
  one that caused H84's Gate 3 verdict flip in the maturity-corrected LAB009 run.

Complete list of confirmation-boundary offenders (12 cycles):
```
H21 p= 0: H21_P00_2026-01-27  asof=2026-01-27  mature=2026-02-24  +28d
H21 p= 5: H21_P05_2026-01-01  asof=2026-01-01  mature=2026-02-02  +6d
H21 p=10: H21_P10_2026-01-08  asof=2026-01-08  mature=2026-02-09  +13d
H21 p=15: H21_P15_2026-01-16  asof=2026-01-16  mature=2026-02-16  +20d
H42 p= 0: H42_P00_2026-01-27  asof=2026-01-27  mature=2026-03-27  +59d
H42 p=10: H42_P10_2025-12-09  asof=2025-12-09  mature=2026-02-09  +13d
H42 p=21: H42_P21_2025-12-24  asof=2025-12-24  mature=2026-02-24  +28d
H42 p=31: H42_P31_2026-01-08  asof=2026-01-08  mature=2026-03-11  +43d
N0  p=15: H63_P15_2025-11-17  asof=2025-11-17  mature=2026-02-16  +20d
N0  p=31: H63_P31_2025-12-09  asof=2025-12-09  mature=2026-03-11  +43d  ← flipped H84
H84 p=21: H84_P21_2025-10-24  asof=2025-10-24  mature=2026-02-24  +28d
H84 p=42: H84_P42_2025-11-25  asof=2025-11-25  mature=2026-03-27  +59d
```

## 5. Promotion-driving metrics affected

- **Gate 1** — `cand.median.conf.sharpe >= n0.median.conf.sharpe` — **directly affected**.
- Gates 2, 3, 4, 5, 6 use only full-period metrics (already bounded by corrected common_end).
- Regime metrics — diagnostic; not in any preregistered gate.
- Discovery metrics — diagnostic; not in any preregistered gate.

Despite only Gate 1 being directly promotion-driving under the boundary defect, the
underlying issue is symmetric: both N0 and candidate confirmation Sharpes may contain
post-`conf_end` returns. The bias is not necessarily one-directional, but the H84 forensic
audit proved that the boundary-past cycle can materially affect verdicts when it is a
losing outlier (as in N0 phase 31's added cycle).

## 6. Why asof-only classification is insufficient

A cycle's realized-return path spans `[asof, mature_date]`. Classifying by asof alone lets
a cycle contribute returns from OUTSIDE the declared period end. The declared period end is
sealed methodology — evaluating with returns past it violates the sealed promise.

The correction requires BOTH boundaries:

```
Discovery cycle IFF:  disc_start <= asof  AND  mature_date <= disc_end
Confirmation cycle IFF: conf_start <= asof  AND  mature_date <= conf_end
```

Where sealed dates (unchanged):
- `disc_end = 2023-10-13`
- `conf_start = 2024-01-15`
- `conf_end = 2026-01-27` (from original preregistration Confirmation period)

`disc_start` is inferred as the common_start (2021-10-01, corrected). No cycle can have
`asof < common_start` under the maturity-correction filter.

## 7. Relationship to previous common_end defect

The maturity correction (commit `3333282`) fixed the boundary defect at the OUTERMOST window
(common_end derived from mature). This period-boundary correction extends the same principle
to INNER windows (discovery, confirmation).

Both corrections share the same principle:

> A cycle contributes to a declared evaluation period only if its realized-return path is
> fully contained within `[period_start, period_end]`.

The confirmation-end defect was NOT caught by the maturity-boundary correction because that
correction only addressed the common window, not the sealed discovery/confirmation calendar
boundaries.

## 8. Why this correction is NOT a new strategy trial

- Same 3 non-control hypotheses (H21, H42, H84)
- Same 4 phase offsets per horizon
- Same 6 gate expressions byte-identical
- Same gate thresholds
- Same turnover formula (Formulation B EXTENDED, verified 0.90 on worked example)
- Same cost grid, same cash grid
- Same simulator (`simulate_horizon_phase`)
- Same DSR trial-source
- Same PBO configuration

Only the CYCLE-CLASSIFICATION filter for `period_metrics(disc/conf)` is corrected. This is
a computed-membership correction on the same hypotheses; no new strategy trials.

**Cumulative `strategy_search` remains 38.**

## 9. Production stays 63

- `india/recommendation_registry.py` — HOLD=63 preserved
- `india/recommendation_generator.py` — rebal=63 preserved
- No production/Core/Telegram files modified by this correction

## 10. What is NEW in the corrected code

Minimal helper `select_period_cycles(meta, period_start, period_end)` in `run_lab009.py`:
returns the set of asofs whose cycles are fully contained in `[period_start, period_end]`.

Then `disc = period_metrics(eq, meta, select_period_cycles(meta, common_start, disc_end), ...)`
and `conf = period_metrics(eq, meta, select_period_cycles(meta, conf_start, conf_end), ...)`.

Assertions inside `period_metrics` (via a corrected wrapper OR the runner) verify no equity
observation exceeds the declared period_end.

## 11. Corrected output filenames (sealed BEFORE execution)

- Report: `reports/lab009_period_corrected_{date}.md`
- Diagnostics: `reports/lab009_period_corrected_diagnostics_{date}.csv`

Original LAB009 outputs and the maturity-corrected outputs are PRESERVED.

## 12. Locked in seal commit BEFORE execution

- Audit document (this file)
- Preregistration addendum: `preregistration_period_boundary_addendum.md`
- Code correction in `run_lab009.py` + optional lab_metrics helper if needed
- Deterministic tests (15 items)
- Output filename templates in `lab009.yaml` (period_corrected_ prefix)

## 13. No outcome assumed

The corrected execution may reverse H21, H42, or H84 verdicts in any direction. The audit
does not predict or assume an outcome — it only defines the correction rigorously.
