# Adaptive Recommendation Engine · v1.4 → v2.0 · Migration Guide

_Generated 2026-08-31T05:18:34.269829+00:00Z · code_sha `3bc1be77a04b`_

## Summary

- **Best model**: `v1.4_baseline_raw_confidence`
- **Baseline**:   `v1.4_baseline_raw_confidence` (v1.4 raw confidence pass-through)
- **Trades**: 1060 total · 742 train · 318 test

## Full metric panel (test set)

| Metric              | Baseline (v1.4) | v2.0 (best) | Delta |
|---------------------|-----------------|-------------|-------|
| brier | 0.3613 | 0.3613 | +0.0000 |
| log_loss | 6.0174 | 6.0174 | +0.0000 |
| ece | 0.3280 | 0.3280 | +0.0000 |
| auc | 0.4811 | 0.4811 | +0.0000 |
| confidence_bias | 0.3280 | 0.3280 | +0.0000 |
| sharpness | 0.0055 | 0.0055 | +0.0000 |
| precision_at_1 | 0.0000 | 0.0000 | +0.0000 |
| precision_at_3 | 0.6667 | 0.6667 | +0.0000 |
| precision_at_5 | 0.8000 | 0.8000 | +0.0000 |
| precision_at_10 | 0.5000 | 0.5000 | +0.0000 |
| precision_at_20 | 0.3500 | 0.3500 | +0.0000 |
| avg_win | 6.8212 | 6.8212 | +0.0000 |
| avg_loss | -6.4379 | -6.4379 | +0.0000 |
| expectancy | 1.3591 | 1.3591 | +0.0000 |
| profit_factor | 1.5125 | 1.5125 | +0.0000 |

## Tier discrimination (Adaptive v2.0 · exit criterion)

Phase 2 exit criterion (PHASE2_MASTER_ROADMAP.md §6):
`Strong-Buy WR > Buy WR > Hold WR > Sell WR` — monotone decreasing.

- Verdict: **FAIL · discrimination weak**
- Monotone decreasing: `False`
- Top-vs-bottom spread: `-0.1544`

| Tier | n | Win rate | Predicted mean | Expectancy |
|------|---|---------:|---------------:|-----------:|
| **Strong-Buy** | 15 | 0.4667 | 1.0 | -0.3036 |
| **Buy** | 47 | 0.4255 | 1.0 | -3.4093 |
| **Hold** | 95 | 0.6316 | 0.9732 | 2.1957 |
| **Sell** | 161 | 0.6211 | 0.85 | 2.4124 |

## Feature importance (top 10)

| Rank | Feature | Importance |
|-----:|---------|-----------:|
| 1 | `confidence` | 1.0000 |

## Governance

> Advisory only. v2.0 model surfaces a top-K identification signal; global AUC remains close to chance. Do not treat raw prediction as calibrated probability outside the ranked top-K context.

## Recommended action

- Adopt `v2.0` prediction as the **top-K identifier** for the
  Adaptive Recommendation Engine's Strong-Buy / Buy assignment.
- Do NOT expose the raw v2.0 output as a probability outside the
  ranked-top-K context — global AUC remains close to chance.
- Continue calibration via DEV029 on the v2.0 signal to close
  ECE gap where the ranked-top-K interpretation would be surfaced
  as confidence to the operator.

## Files

- `reports/adaptive_rec_v2_signal.json` — headline + metrics
- `reports/adaptive_rec_v2_scoreboard.json` — all model results
- `reports/adaptive_rec_v2_feature_importance.json` — per-feature importance
- `reports/adaptive_rec_v2_reliability.json` — baseline + v2 curves
- `reports/adaptive_rec_v2_signal.parquet` — per-trade predictions
- `reports/adaptive_rec_v2_migration.md` — this file