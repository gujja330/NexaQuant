# DEV029 · Confidence Calibration · Headline Finding

**Run:** 2026-07-17 · **Trades:** 1060 (742 train / 318 test) · **Best method:** Platt scaling

## Before / After (full corpus)

| Metric | Raw | Calibrated | Delta |
|---|---:|---:|---:|
| Brier score | 0.3295 | 0.2431 | **-0.086** |
| ECE | **0.2868** | **0.0021** | **-0.285 (~140x)** |
| MCE | 0.4571 | 0.0021 | -0.455 |
| Log loss | 2.4279 | 0.6793 | -1.749 |
| Confidence bias | +0.2868 | -0.0021 | -0.289 |

## What the raw reliability curve says

| Raw confidence bin | n | predicted | observed | gap |
|---|---:|---:|---:|---:|
| [0.80, 0.90] | 920 | 0.85 | 0.589 | **+26pp overconfident** |
| [0.90, 1.00] | 140 | 1.00 | 0.543 | **+46pp overconfident** |

## What the calibrator learned

Every raw confidence value maps to ~58% after calibration. All 1060 trades
collapse into a single [0.50, 0.60] bin, predicted 0.581, observed 0.583.

## Interpretation (evidence-driven, no manual tuning)

The raw `confidence` signal has **no discriminative power** — trades labelled
90% win at essentially the same rate as trades labelled 80%. The optimal
prediction for every trade is the base rate (~58%), which is what Platt
learned.

This is consistent with:
- DEV025 · ECE 0.29 (independently confirmed the miscalibration)
- DEV027 · 218/677 diagnoses fired as "overconfidence" (structural finding)

## Implication for downstream engines

Under ARCH001A Article V clause 5.1 (advisory-only), DEV029 does not
mutate the recommendation engine. But the finding is a strong signal that
raw `confidence` in its current form should not be trusted as a
probability — it is a rank-ordering signal at best.

Actionable follow-ups (not applied automatically):
1. **Sprint 15 (DEV030 · Champion vs Challenger)** — treat raw confidence
   as a feature, not a probability. Let a challenger strategy learn the
   real probability from features (score, sector strength, regime, ...).
2. **Sprint 16+ (feature engineering)** — investigate whether ANY current
   features carry win-probability signal. If not, the confidence label
   should be replaced with the calibrated base-rate estimate for now.
3. **UX** — display calibrated confidence to the operator instead of raw
   (Sprint 15 UX029/030 candidate).

## Governance

Retrain only when new data available; drift-based. No auto-application.
