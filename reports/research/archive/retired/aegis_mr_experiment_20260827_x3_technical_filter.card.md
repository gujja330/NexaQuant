# Technical filter · RSI + MA20 evidence-backed edges

**Experiment ID:** `aegis_mr_experiment_20260827_x3_technical_filter`  
**Status:** `ARCHIVED_FOR_LATER`  
**Route:** `retired`  
**Market:** INDIA  
**Card generated:** 2026-08-27T09:15:46+00:00

## Metadata

- **Hypothesis:** India OVERSOLD_lt30 RSI has 43.75% 5D WR (+18pp vs baseline). India above_+1_+5 ma20_dist has 37.17% WR (+11pp). India WEAK 30-45 RSI has 18.25% WR (-7pp) and below_-5_-1 ma20_dist has 17.97% WR (-8pp). Positive-filter tag on the good buckets and negative-filter tag on the bad ones should predict forward outcomes prospectively.
- **Data source:** ['derived_from_mr_studies_technicals']
- **Result (historical):** Technical filter · RSI + MA20 evidence-backed edges
- **Sample size (forward):** N = 2 shadow days (2026-08-27 onwards)
- **Metric:** positive_filter_5D_WR - negative_filter_5D_WR
- **Reason for current status:** ARCHIVED_FOR_LATER · no successor
- **Revisit condition:** N reaches 100 forward observations
- **Acceptance:** positive_filter_5D_WR - negative_filter_5D_WR >= 15pp on n>=100 total tagged observations.
- **Rejection:** positive_filter_5D_WR - negative_filter_5D_WR < 3pp · signals that historical buckets don't survive out-of-sample.

## Recent attempts

- `2026-08-27` n_rows=19

## Governance

- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)
- Zero auto-promotion
- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry