# LAB009 — Maturity Boundary Defect Audit

**Audit date:** 2026-07-13 (post-LAB009 evidence audit `1210c77`)
**Original LAB009 commits:**
- `b077767` — LAB009 preregistration
- `6f78104` — LAB009 evidence/results

**Cumulative strategy_search:** **38** (unchanged — this correction is NOT a new hypothesis)

---

## 1. Confirmed defect

### Original code path

`india/ai_lab/LAB009_Horizon_Phase_Recalibration/horizon_phase_policies.py:216-228`

```python
def compute_common_window(all_registries: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    firsts, lasts = [], []
    for (h, p), reg in all_registries.items():
        asofs = pd.to_datetime(reg["asof"])
        firsts.append(asofs.min())
        lasts.append(asofs.max())         # <-- uses asof for end boundary
    common_start = pd.Timestamp(max(firsts)).normalize()
    common_end = pd.Timestamp(min(lasts)).normalize()
```

Line 146 in `simulate_horizon_phase`:
```python
reg_df = reg_df[(reg_df["asof"] >= common_start) & (reg_df["asof"] <= common_end)]
```

Both places bound only the **asof** date. A cycle's realized-return path extends
`asof → mature_date`; different horizons have different maturity lengths (21/42/63/84 days).
Because the filter allows any cycle with `asof <= common_end` to be included, cycles at the
tail-end of the window realize returns well past `common_end`.

### Forensic table — per-config maturity overrun

Under LAB009's current (asof-based) common window `2021-10-01 → 2025-11-25`:

| Cand | H | Phase | last_asof | last_mature | days past common_end | cycles with mature > end |
|:-:|:-:|:-:|---|---|---:|:-:|
| H21 | 21 | 0  | 2025-11-25 | 2025-12-24 | +29  | 1 |
| H21 | 21 | 5  | 2025-10-31 | 2025-12-02 | +7   | 1 |
| H21 | 21 | 10 | 2025-11-10 | 2025-12-09 | +14  | 1 |
| H21 | 21 | 15 | 2025-11-17 | 2025-12-16 | +21  | 1 |
| H42 | 42 | 0  | 2025-11-25 | 2026-01-27 | +63  | 1 |
| H42 | 42 | 10 | 2025-10-08 | 2025-12-09 | +14  | 1 |
| H42 | 42 | 21 | 2025-10-24 | 2025-12-24 | +29  | 1 |
| H42 | 42 | 31 | 2025-11-10 | 2026-01-08 | +44  | 1 |
| N0  | 63 | 0  | 2025-10-24 | 2026-01-27 | +63  | 1 |
| N0  | 63 | 15 | 2025-11-17 | 2026-02-16 | +83  | 1 |
| N0  | 63 | 31 | 2025-09-08 | 2025-12-09 | +14  | 1 |
| N0  | 63 | 47 | 2025-09-30 | 2026-01-01 | +37  | 1 |
| H84 | 84 | 0  | 2025-09-23 | 2026-01-27 | +63  | 1 |
| H84 | 84 | 21 | 2025-10-24 | 2026-02-24 | +91  | 1 |
| **H84** | **84** | **42** | **2025-11-25** | **2026-03-27** | **+122** ⚠️ | 1 |
| H84 | 84 | 63 | 2025-08-22 | 2025-12-24 | +29  | 1 |

**All 16/16 configs have at least one cycle whose realized returns extend past common_end.**
Maximum overrun: **122 days** (H84 phase 42). Total tail-end equity observations beyond
common_end propagate into every promotion-driving metric.

### Trading-day coverage differential

Equity-curve trading-day spans under original filter: **1009 to 1093 days** (a spread of 84
trading days = one full H84 cycle).

## 2. Why entry-date alignment is insufficient

- CAGR/Sharpe/MaxDD/Ulcer are computed over the FULL equity time-series returned by
  `simulate_horizon_phase`.
- The equity time-series extends from the first in-window asof to the LAST cycle's
  mature_date — which lies past `common_end` for every config.
- Different candidates therefore include DIFFERENT tail periods in their metrics:
  - N0 phase 15 metrics reflect market returns through 2026-02-16
  - H84 phase 42 metrics reflect market returns through 2026-03-27
  - H21 phase 5 metrics stop at 2025-12-02
- The 4 phases of a single horizon include mutually distinct tail data.
- Comparing horizons under such non-identical realized-return coverage violates the
  preregistration's promise of "identical evaluation coverage".

## 3. Why this correction is NOT a new strategy trial

- Same 3 non-control hypotheses (H21, H42, H84)
- Same phase offsets, same cost model, same six gate expressions, same thresholds
- Same cash grid, same cost grid, same DSR trial-source
- Only the DATE-RANGE FILTER is corrected — from asof-only to include mature_date bound
- This is a computed-window correction on the same data + hypotheses

**Cumulative `strategy_search` remains 38.** No new hypothesis added.

## 4. Corrected principle

**ALL promotion-driving equity observations must lie inside one identical declared evaluation
interval `[common_start, common_end]`.**

- `common_start = max(each config's earliest scorable asof)` — UNCHANGED
- `common_end = MIN(each config's latest mature_date)` — CORRECTED (was min of last asof)

For LAB009 data:
- Corrected `common_start` = 2021-10-01 (unchanged)
- Corrected `common_end` = **2026-03-27** (was 2025-11-25 under asof-only rule; H84 phase 42's
  last mature is the binding constraint)

Cycle inclusion rule: **BOTH** `asof >= common_start` **AND** `mature_date <= common_end`.
Equity index must satisfy `equity.index.max() <= common_end`.

## 5. Correction is locked BEFORE corrected rerun

- Gates and thresholds: EXACTLY the six sealed expressions from `lab009.yaml`
- Turnover formula: Formulation B EXTENDED, verified on the same 5 unit cases
- Phase offsets: N0 {0,15,31,47}; H21 {0,5,10,15}; H42 {0,10,21,31}; H84 {0,21,42,63}
- Cash grid: [0.0, 0.06]
- Cost grid: [15, 30, 50] canonical=15, stress=50
- Preregistration original file `preregistration.md`: UNMODIFIED
- New addendum: `preregistration_maturity_boundary_addendum.md`
- Original LAB009 report and diagnostics CSV: UNMODIFIED (historical evidence)
- Corrected outputs: `reports/lab009_maturity_corrected_2026-07-13.md/.csv` (distinct filenames)

## 6. Assertions the corrected implementation must enforce

At execution time, for every horizon × phase simulation:
1. `assert no included cycle has mature_date > common_end`
2. `assert max(equity.index) <= common_end`

And the corrected `compute_common_window` must return `common_end` computed as
`min(each config's latest mature_date)`.

## 7. Effect on evaluation

Under corrected rule (`common_start=2021-10-01`, `common_end=2026-03-27`, BOTH filters):

Some configs gain cycles (their maturity fits within 2026-03-27; their asof still passes),
others lose the last cycle (whose maturity now exceeds common_end):

| Cand | H | Phase | Old cycles (asof filter) | New cycles (mature filter) |
|:-:|:-:|:-:|:-:|:-:|
| H21 | 21 | 0  | 50 | 55 (+5) |
| H21 | 21 | 5  | 49 | 55 (+6) |
| H21 | 21 | 10 | 49 | 54 (+5) |
| H21 | 21 | 15 | 49 | 54 (+5) |
| H42 | 42 | 0  | 25 | 27 (+2) |
| H42 | 42 | 10 | 24 | 27 (+3) |
| H42 | 42 | 21 | 25 | 27 (+2) |
| H42 | 42 | 31 | 25 | 26 (+1) |
| N0  | 63 | 0  | 17 | 18 (+1) |
| N0  | 63 | 15 | 17 | 18 (+1) |
| N0  | 63 | 31 | 16 | 18 (+2) |
| N0  | 63 | 47 | 16 | 17 (+1) |
| H84 | 84 | 0  | 12 | 13 (+1) |
| H84 | 84 | 21 | 13 | 13 (0) |
| H84 | 84 | 42 | 13 | 13 (0)  ← binding constraint |
| H84 | 84 | 63 | 12 | 13 (+1) |

Higher-frequency horizons gain more cycles (their maturities fit within 2026-03-27, and
their asofs extend further into the corrected window). H84 phase 42 is essentially unchanged
(it's the binding config for common_end).

**Impact direction on H42's promotion claim is a priori unknown** — additional H42 cycles
introduce new data that could shift median metrics up or down. The reported result must be
taken as-is with no post-hoc tuning.

## 8. Trial count remains 38

- No new candidates
- No parameter changes
- No new hypotheses
- Simulator methodology corrected on same hypotheses
- Trial manifest unchanged

## 9. Production stays 63

- `india/recommendation_registry.py` — HOLD=63 preserved
- `india/recommendation_generator.py` — rebal=63 preserved
- No production/Core/Telegram files modified by this correction

---

## Locked deliverables

1. This audit document (`LAB009_MATURITY_BOUNDARY_AUDIT.md`)
2. Preregistration addendum (`preregistration_maturity_boundary_addendum.md`)
3. Code correction in `horizon_phase_policies.py`
4. Deterministic tests
5. All four sealed + pushed as a single "seal commit" BEFORE corrected execution
6. Corrected outputs with distinct filenames — original evidence preserved
