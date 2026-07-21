# AEGIS Executive Dashboard

**Last updated:** 2026-07-21 · Sprint 6 · Learning Engine · SHIPPED
**Overwritten every sprint** — always the current state of AEGIS.

---

## Pipeline Status

```
✅ Feature Store              Sprint 2.5   · 81 features · fingerprint b65ceb49a83a
✅ Feature Intelligence       Sprint 2.6   · governance + drift + selection
✅ Model Factory              Sprint 2.7   · 11 models + ensemble
✅ Recommendation Engine v3   Sprint 3     · conflict + calibration + regime + explainer
✅ Risk Engine                Sprint 4     · Kelly + caps + VaR/CVaR
✅ Portfolio Engine           Sprint 5     · N-name + rebalance diff + cash policy
✅ Learning Engine            Sprint 6     · outcome ledger + attributions + calibration
⚪ Execution Simulator        Sprint 7     · pending
⚪ Walk-Forward Validation    Sprint 8     · pending  (first REAL results)
⚪ AI Validation Auditor      Sprint 9     · pending
⚪ Research Factory           Sprint 10    · pending
```

---

## Today's Runtime Results (2026-07-21)

| Metric | India | USA |
|---|---:|---:|
| Recommendations | 15 | 15 |
| STRONG_BUY + BUY | 0 | 0 |
| HOLD | 15 | 15 |
| SELL + STRONG_SELL | 0 | 0 |
| Disagreement → HOLD | 10 | 6 |
| **Active Positions** | **0** | **0** |
| Cash % | 100.0% | 100.0% |
| Gross Exposure | 0.00% | 0.00% |
| Portfolio Volatility (ann) | 0.00% | 0.00% |
| VaR 95% 1d | 0.00% | 0.00% |
| CVaR 95% 1d | 0.00% | 0.00% |
| HHI | 0.000 | 0.000 |
| Effective N | 0.0 | 0.0 |
| Turnover | 0.00% | 0.00% |
| Portfolio Verdict | PASS | PASS |

## Current Bottleneck (WHY all-HOLD)

The classifier is being **appropriately conservative** — not broken:
- ✓ Equal-weight ensemble across 11 models
- ✓ Neutral regime dampens both BUY and SELL confidence by 0.95
- ✓ Model disagreement (6-10 tickers) auto-collapses to HOLD via safety valve
- ✓ Calibrated confidence sits just below the 0.50 BUY threshold on most tickers

Sprint 6 Learning Engine now exists — the confidence calibration feedback loop is closed. Once historical outcomes populate (via Sprint 8 walk-forward or via 60 days of live-forward recs), calibration will loosen for models that empirically win.

---

## Learning Corpus State

| Field | India | USA |
|---|---:|---:|
| Rec history rows | 0 | 0 |
| New closed today | 0 | 0 |
| Corpus total | 0 | 0 |
| Win rate | n/a | n/a |
| Calibration method | identity | identity |

**Empty by design.** Sprint 6 built the framework; Sprint 8 walk-forward will populate it.

---

## Cumulative Test Health

```
Sprint 1 (backend validation)                12/12 ✅
Sprint 2 (canonical + market intel + AI)     12/12 ✅
Sprint 2.5 (feature store + AI)              12/12 ✅
Sprint 2.6 (feature intel + registry + gate) 18/18 ✅
Sprint 2.7 (model factory + 11 models)       14/14 ✅
Sprint 3 (recommendation intelligence v3)    22/22 ✅
Sprint 4 (risk engine)                       23/23 ✅
Sprint 5 (portfolio engine)                  20/20 ✅
Sprint 6 (learning engine)                   19/19 ✅
─────────────────────────────────────────────────────
TOTAL                                       152/152 ✅
```

## Backend Validation

- India: WARNING (3 pre-existing legacy datasets stale — not Sprint 6)
- USA: PASS · 60/60 · confidence 0.913

---

## Model Registry

Every engine registered as EXPERIMENTAL — promotion via `backend/promotion/promotion_gate.py`:
- `aegis.recommendation.v3` (India + USA)
- `aegis.risk.v1` (India + USA)
- `aegis.portfolio.v1` (India + USA)
- `aegis.learning.v1` (India + USA)

---

## Next Sprint Readiness

```
Sprint 6 → Sprint 7  ✓ (learning corpus ready for execution simulator's fills ledger)
Sprint 7 → Sprint 8  Pending
Sprint 8 → Sprint 9  Pending
Sprint 9 → Sprint 10 Pending
```

---

## Latest Commit

Sprint 6 · Learning Engine · commit pending push · docs/AEGIS_SPRINT6_REPORT.md
