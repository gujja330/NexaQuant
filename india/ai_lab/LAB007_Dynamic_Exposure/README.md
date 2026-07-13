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
