# LAB007 — Sealed Pre-registration

**Sealed 2026-07-13.** This file is written and locked BEFORE any candidate is executed.
Any deviation invalidates the pre-registration and must be documented as LAB007-B (new)
with a new trial count. No post-run parameter tuning permitted.

## 1. Hypothesis

The CURRENT production dynamic exposure policy may be directionally useful but poorly
calibrated. A simpler or differently tapered exposure policy may improve MaxDD / CVaR /
Ulcer with bounded CAGR sacrifice.

**We are NOT testing "does regime timing add value" (that would use 100%-invested as null).
We ARE testing "is the specific current mapping well-tuned".**

## 2. Exact production exposure — the null (N0)

Traced from `india/confidence_engine.py:32-51` and `india/global_risk.py:global_exposure()`.
Every input is PIT-safe (audit: `README.md § LAB007 findings 2026-07-13`).

```
exp(t) = 1.0
    × (0.60 if IndiaVIX(t)      > rolling_120d.quantile(0.80).at(t)   else 1.0)   # G1
    × (0.60 if Nifty_close(t)   < Nifty_close.rolling(200).mean(t)    else 1.0)   # G2
    × (0.80 if SPX_close(t)     < SPX_close.rolling(200).mean(t)      else 1.0)   # G3
    × (0.80 if USVIX(t)         > USVIX.rolling(120d).quantile(0.80)  else 1.0)   # G4
    × (0.85 if DXY(t)/DXY(t-63) - 1 > +0.03                            else 1.0)   # G5
```

Labels are display-only buckets on the numeric result:
`Strong ≥ 0.90 · Neutral 0.65-0.89 · Weak < 0.65`

Applied at `recommendation_generator.py:223` as `invest = capital * exp` once per cycle.
No intra-cycle exposure changes.

Historical distribution (1,373 trading days, 2020-12-28 → 2026-07-13):
mean 0.762 · median 0.800 · min 0.196 · max 1.000 · 42% of days at 1.000.

Historical exp at each of 19 cycle asofs:
```
2021-07-01 : 1.000    2024-01-15 : 0.600
2021-10-01 : 0.800    2024-04-18 : 0.800
2022-01-03 : 1.000    2024-07-19 : 0.800
2022-04-05 : 0.850    2024-10-18 : 1.000
2022-07-06 : 0.408    2025-01-20 : 0.306
2022-10-07 : 0.544    2025-04-24 : 0.384
2023-01-06 : 0.800    2025-07-23 : 1.000
2023-04-12 : 1.000    2025-10-24 : 1.000
2023-07-13 : 1.000    2026-01-27 : 0.600
2023-10-13 : 0.680
```

## 3. Candidate matrix — 4 configs LOCKED

Each candidate modifies ONLY the specified gate(s). All other gates remain production-identical.

### A — Milder India gates
```
G1: replace 0.60 with 0.75  (India VIX)
G2: replace 0.60 with 0.75  (Nifty 200-DMA)
G3, G4, G5: UNCHANGED
```
Hypothesis being tested: current 0.60 India cuts too aggressively in transitional periods,
sacrificing recovery upside without proportional DD protection.

### B — Stronger India gates
```
G1: replace 0.60 with 0.45  (India VIX)
G2: replace 0.60 with 0.45  (Nifty 200-DMA)
G3, G4, G5: UNCHANGED
```
Hypothesis being tested: current 0.60 India is too lax; deeper cuts on India domestic
signals could preserve capital in sustained drawdowns.

### C — Smooth India-VIX taper
```
G1: replace {0.6 if VIX > q80 else 1.0} with
    max(0.60, min(1.00, 1.00 - 0.40 * (VIX_pctile - 0.60) / 0.30))
    where VIX_pctile = VIX percentile against trailing 120 days
    Yields: pctile ≤ 60% → 1.0; pctile = 90% → 0.60; linear taper between
G2: UNCHANGED (still discrete 0.60)
G3, G4, G5: UNCHANGED
```
Hypothesis being tested: discrete 80th-pctile gate is unstable at boundary; smooth taper is
more robust to signal noise.

### D — Fixed 0.85 constant
```
exp(t) = 0.85 ALWAYS
No regime input, no gates
```
Hypothesis being tested: regime timing adds no value beyond a static prudent baseline; the
information cost of the 5-gate calculation isn't worth it.

## 4. Simulation methodology

- Registry cycles (source=='historical', scored==1) — the 19 chronological cycles
- Each cycle's stock weights: HRP-normalized from registry (sum to 1.0 within the equity portion)
- Cycle P&L: `portfolio_return(t) = exp_asof × stock_weighted_return(t) + (1 - exp_asof) × cash_return(t)`
- Cash return: **DUAL primary result** (see § 5)
- Cost model: transactions incurred when exp changes cycle-over-cycle, applied to the
  DIFFERENCE `|exp(cycle N+1) - exp(cycle N)|` in bps
- No intra-cycle exposure changes for any candidate (matches production)

## 5. Cash return — dual primary reporting

Per operator: cash return assumption cannot be selected post-hoc.

- **Primary result**: `cash_return = 0%` (conservative; understates true baseline CAGR)
- **Sensitivity reference**: `cash_return = 6% annualized` (~0.023%/day; realistic Indian short-term rate)
- Both reported side-by-side for every candidate + N0
- No selection of "the better" assumption; both are the reported result

Actual RBI/repo-linked cash-return data is a separate future data-quality improvement, NOT
a LAB007 blocker.

## 6. Chronological discovery/confirmation split

Not "training". Not "held-out". Discovery = period that inspired the hypothesis; Confirmation
= all other data.

| Period | Dates | # Cycles | Strong | Neutral | Weak |
|---|---|---|---|---|---|
| **Discovery** | 2021-07-01 → 2023-10-13 | 10 | 4 | 4 | 2 |
| **Confirmation** | 2024-01-15 → 2026-01-27 | 9 | 3 | 2 | **4** |

**Power limitation acknowledged**: 4 Weak cycles in confirmation is a small sample. Any
mechanism claim about Weak-regime behavior in the confirmation set carries meaningful
statistical uncertainty. If a candidate's mechanism-attribution primarily depends on 1-2 of
those 4 cycles, that must be flagged in the report — not treated as robust confirmation.

Primary promotion evidence comes from CONFIRMATION metrics. Discovery is transparency only.

## 7. Trial-count arithmetic (audited)

```
LAB006 subtotal:
  Rule B (5 k × 3 policies)                : 15
  Rule C (4 stops × 3 policies)            : 12
  Rule C audit-closure rerun (same configs): 0
  Rule C1 (1 pre-registered strategy)      : 1
LAB006 total                               : 28

LAB007 new candidates:
  A, B, C, D (N0 is control not new)       : 4

Cumulative Lab-wide n_trials               : 32
```

The earlier LAB006 reports cited 30. That was a `read_trial_manifest_count()` fallback
default that fired when the reader's regex didn't match the amended manifest labels. True
LAB006 count is 28. Fallback bug fixed in scaffold (raises LookupError now).

`india/ai_lab/trial_manifest.md` is the central Lab-wide ledger. `n_trials = 32` is what
DSR uses for LAB007.

## 8. Promotion gates — LOCKED

A candidate promotes to Core/Telegram consideration ONLY if ALL of gates 1-6 pass in the
confirmation sample under BOTH cash-return assumptions:

1. **Confirmation Ulcer improvement ≥ 1.0 point** vs N0
2. **Confirmation MaxDD improvement ≥ 3pp vs N0 OR CVaR(5%) improvement ≥ 0.5pp**
3. **Full-period CAGR sacrifice ≤ 2pp** vs N0
4. **DSR > 0.90** with `n_trials = 32` (from central manifest)
5. **Cost-robust at 50 bps**: gates 1-3 still hold with cost=50 bps
6. **Regime-attribution sane**: primary risk improvement is economically attributable to
   Weak-regime behavior (Weak-cycle Ulcer improvement > Strong-cycle Ulcer improvement)

**PBO handling** (corrected from earlier proposal):
- N=5 (N0 + 4 candidates) is at the low end of CSCV feasibility.
- We will run `pbo_across_configs()` — but if the metric is judged uninterpretable at N=5, the
  report will explicitly say `PBO = N/A · N=5 too small for defensible interpretation` and
  present fold-level Sharpe rank tables instead.
- **PBO is NOT a soft promotion gate.** No candidate can be promoted merely because PBO is
  N/A. Gates 1-6 must ALL pass and operator approval remains mandatory.

## 9. Negative-result handling

A rejection is a valid outcome. If N0 remains superior or candidates only trade CAGR for
cosmetic drawdown improvement, LAB007 candidates are rejected and Core stays frozen.

No LAB007-B / -C variants after seeing results without a new pre-registration and updated
trial count. No advisory tier. No bypass. No "promising enough" promotion.

## 10. What LAB007 will NOT do

- Not touch Core (`arjuna_v2`, `confidence_engine`, `recommendation_generator`)
- Not touch Telegram (`telegram_notify`, `exit_reasons`)
- Not introduce fitted models / learned parameters (there are none in the candidates)
- Not select thresholds from full-period outcome optimization
- Not add candidates post-run

## 11. Reproducibility

- Sealed: 2026-07-13
- Central manifest: `india/ai_lab/trial_manifest.md` (n_trials = 32)
- Code (to be written AFTER operator approval):
  - `india/ai_lab/LAB007_Dynamic_Exposure/exposure_lab.py` — reusable simulator additions
  - `india/ai_lab/LAB007_Dynamic_Exposure/run_lab007.py` — main driver
- Report path: `india/ai_lab/LAB007_Dynamic_Exposure/reports/lab007_<date>.md`
- Diagnostics: `reports/lab007_diagnostics_<date>.csv`
