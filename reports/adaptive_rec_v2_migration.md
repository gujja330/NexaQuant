# Adaptive Recommendation Engine · v1.4 → v2.0 · Migration Guide

_Generated 2026-07-20T05:38:10.751888+00:00Z · code_sha `45999b46b7a9`_

## Summary

- **Best model**: `hgb_v2.0`
- **Baseline**:   `v1.4_baseline_raw_confidence` (v1.4 raw confidence pass-through)
- **Trades**: 1060 total · 742 train · 318 test

## Full metric panel (test set)

| Metric              | Baseline (v1.4) | v2.0 (best) | Delta |
|---------------------|-----------------|-------------|-------|
| brier | 0.3613 | 0.3626 | +0.0013 |
| log_loss | 6.0174 | 1.1544 | -4.8630 |
| ece | 0.3280 | 0.3041 | -0.0239 |
| auc | 0.4743 | 0.4757 | +0.0013 |
| confidence_bias | 0.3280 | -0.0302 | -0.3582 |
| sharpness | 0.0055 | 0.1059 | +0.1004 |
| precision_at_1 | 0.0000 | 0.0000 | +0.0000 |
| precision_at_3 | 0.3333 | 0.3333 | +0.0000 |
| precision_at_5 | 0.4000 | 0.6000 | +0.2000 |
| precision_at_10 | 0.6000 | 0.8000 | +0.2000 |
| precision_at_20 | 0.6000 | 0.6000 | +0.0000 |
| avg_win | 6.7343 | 6.7343 | +0.0000 |
| avg_loss | -6.4379 | -6.4379 | +0.0000 |
| expectancy | 1.3080 | 1.3080 | +0.0000 |
| profit_factor | 1.4932 | 1.4932 | +0.0000 |

## Tier discrimination (Adaptive v2.0 · exit criterion)

Phase 2 exit criterion (PHASE2_MASTER_ROADMAP.md §6):
`Strong-Buy WR > Buy WR > Hold WR > Sell WR` — monotone decreasing.

- Verdict: **MARGINAL · monotone but thin spread**
- Monotone decreasing: `True`
- Top-vs-bottom spread: `0.0161`

| Tier | n | Win rate | Predicted mean | Expectancy |
|------|---|---------:|---------------:|-----------:|
| **Strong-Buy** | 15 | 0.6 | 0.9906 | 4.6769 |
| **Buy** | 47 | 0.5957 | 0.9482 | 0.3005 |
| **Hold** | 95 | 0.5895 | 0.7796 | 0.8552 |
| **Sell** | 161 | 0.5839 | 0.2727 | 1.5554 |

## Feature importance (top 10)

| Rank | Feature | Importance |
|-----:|---------|-----------:|
| 1 | `dim_volatility` | 0.2223 |
| 2 | `score_at_entry` | 0.2218 |
| 3 | `dim_drawdown` | 0.1908 |
| 4 | `dim_momentum` | 0.1768 |
| 5 | `dim_position_52w` | 0.1317 |
| 6 | `industry_Private Banks` | 0.0137 |
| 7 | `sector_Consumption` | 0.0132 |
| 8 | `sector_Auto` | 0.0048 |
| 9 | `sector_Metal` | 0.0034 |
| 10 | `sector_Energy` | 0.0032 |

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