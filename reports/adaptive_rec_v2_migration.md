# Adaptive Recommendation Engine · v1.4 → v2.0 · Migration Guide

_Generated 2026-11-27T06:21:40.338104+00:00Z · code_sha `b5f78e3c53de`_

## Summary

- **Best model**: `hgb_v2.0`
- **Baseline**:   `v1.4_baseline_raw_confidence` (v1.4 raw confidence pass-through)
- **Trades**: 1140 total · 798 train · 342 test

## Full metric panel (test set)

| Metric              | Baseline (v1.4) | v2.0 (best) | Delta |
|---------------------|-----------------|-------------|-------|
| brier | 0.4139 | 0.3737 | -0.0402 |
| log_loss | 8.4919 | 1.2323 | -7.2596 |
| ece | 0.3997 | 0.3233 | -0.0764 |
| auc | 0.4918 | 0.4603 | -0.0315 |
| confidence_bias | 0.3997 | 0.0547 | -0.3450 |
| sharpness | 0.0052 | 0.1041 | +0.0989 |
| precision_at_1 | 0.0000 | 1.0000 | +1.0000 |
| precision_at_3 | 0.0000 | 0.6667 | +0.6667 |
| precision_at_5 | 0.0000 | 0.6000 | +0.6000 |
| precision_at_10 | 0.1000 | 0.8000 | +0.7000 |
| precision_at_20 | 0.3000 | 0.6000 | +0.3000 |
| avg_win | 6.3881 | 6.3881 | +0.0000 |
| avg_loss | -6.4409 | -6.4409 | +0.0000 |
| expectancy | 0.5738 | 0.5738 | +0.0000 |
| profit_factor | 1.1966 | 1.1966 | +0.0000 |

## Tier discrimination (Adaptive v2.0 · exit criterion)

Phase 2 exit criterion (PHASE2_MASTER_ROADMAP.md §6):
`Strong-Buy WR > Buy WR > Hold WR > Sell WR` — monotone decreasing.

- Verdict: **FAIL · discrimination weak**
- Monotone decreasing: `False`
- Top-vs-bottom spread: `0.0773`

| Tier | n | Win rate | Predicted mean | Expectancy |
|------|---|---------:|---------------:|-----------:|
| **Strong-Buy** | 17 | 0.6471 | 0.9944 | 2.2387 |
| **Buy** | 51 | 0.3922 | 0.9594 | -1.6365 |
| **Hold** | 102 | 0.5686 | 0.8243 | 0.4414 |
| **Sell** | 172 | 0.5698 | 0.3244 | 1.1431 |

## Feature importance (top 10)

| Rank | Feature | Importance |
|-----:|---------|-----------:|
| 1 | `score_at_entry` | 0.2371 |
| 2 | `dim_drawdown` | 0.2046 |
| 3 | `dim_momentum` | 0.1864 |
| 4 | `dim_volatility` | 0.1840 |
| 5 | `dim_position_52w` | 0.1351 |
| 6 | `industry_Private Banks` | 0.0113 |
| 7 | `sector_Consumption` | 0.0080 |
| 8 | `industry_Food & Beverage` | 0.0072 |
| 9 | `sector_Auto` | 0.0065 |
| 10 | `sector_Energy` | 0.0039 |

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