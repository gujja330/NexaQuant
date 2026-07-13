# LAB007 — Dynamic Exposure / Position Sizing

**Status:** Pre-registration sealed 2026-07-13 · Awaiting operator approval to execute
**Owner:** Operator + Assistant · **Opened:** 2026-07-13

## Research question

Does any pre-registered alternative regime → exposure policy materially improve the frozen
strategy versus the CURRENT deployed dynamic exposure policy?

**Null hypothesis** = current production `current_regime()` output, PIT-reconstructed.
This is NOT a marketing test against 100% invested. The honest question is whether the
existing multiplicative-gate exposure mapping is well-tuned or would benefit from a
pre-registered alternative.

## Origin

LAB006's exit research demonstrated:
1. Trailing-stop rules cut winners in Weak-regime cycles (Weak baseline CAGR +19.8%; rule
   halved it to +9.7% while cutting MaxDD from -11.8% to -5.6%).
2. The frozen strategy's own defensive regime overlay (VIX + Nifty 200-DMA + global gates)
   is already doing much of the drawdown-management work.
3. Therefore the more useful research question may be about SIZING, not intra-cycle exits.

## Files

- `README.md` — this document
- `preregistration.md` — sealed hypothesis + candidate matrix + gates
- `exposure_lab.py` — (to be written after approval) reusable helpers for exposure-aware
  simulation, extending the LAB006 scaffold
- `run_lab007.py` — (to be written after approval) main driver
- `reports/` — output markdown + CSV per run

## Log

- **2026-07-13** — Lab opened. Trace of production exposure formula complete (see
  `preregistration.md § 2`). PIT audit clean. Historical exposure distribution documented.
- **2026-07-13** — Trial-count audit: LAB006 true count = 28 (was silently defaulting to
  30 via a reader fallback bug — fixed). Cumulative Lab-wide with 4 LAB007 candidates = 32.
- **2026-07-13** — Chronological discovery/confirmation split adopted per operator direction.
  Discovery = 10 cycles (2021-07-01 → 2023-10-13), Confirmation = 9 cycles (2024-01-15 →
  2026-01-27). Confirmation contains 4 Weak cycles — power limitation acknowledged.
- **2026-07-13** — Pre-registration sealed. STOP for operator approval before executing.
- **2026-07-13** — Operator approved (n_trials=32 audited). Preregistration commit: `93028e0`.
- **2026-07-13** — Executed once per sealed spec. **VERDICT: REJECT all 4 candidates.** None
  cleared all 6 gates under both cash-return assumptions.
  - **A** (milder India): Ulcer improvement +0.26 (< gate 1.0). DSR 0.77-0.84. Marginal.
  - **B** (stronger India): Ulcer WORSENED in confirmation. DSR 0.78-0.87.
  - **C** (smooth VIX taper): near-zero change vs N0 on all metrics. Gate 6 fails (mechanism unclear).
  - **D** (fixed 0.85): highest CAGR (+15.6% / +16.6%) and best Ulcer (5.1 / 4.9), but FAILS Gate 6
    trivially (no regime input → no regime attribution). Also fails DSR (0.83 / 0.87 < 0.90).
  - **PBO across N=5 configs**: 0.700 (cash=0%) / 0.871 (cash=6%). Both high — additional
    evidence of config-selection instability. Fold Sharpe ranks confirm: no config leads
    consistently across all 4 folds.
  - **Discovery vs confirmation reveals an era effect**: full-period CAGR 13-16% masks
    Discovery ~22-25% vs Confirmation ~4-8%. Attributable to universe / market regime, NOT
    fixable via exposure calibration.
  - Report: `reports/lab007_2026-07-13.md`. Diagnostics: `reports/lab007_diagnostics_2026-07-13.csv`.
  - **Production dynamic exposure remains frozen.** Central manifest updated.
