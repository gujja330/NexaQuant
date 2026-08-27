# India TIME_STOP_5D advisory · loss-control experiment

**Experiment ID:** `aegis_mr_experiment_20260827_x2_stop_loss_time_5d`  
**Status:** `SUPERSEDED_BY`  
**Route:** `superseded`  
**Superseded by:** `aegis_mr_experiment_20260827_e3_stop_loss_cross_market`  
**Market:** INDIA  
**Card generated:** 2026-08-27T09:15:46+00:00

## Metadata

- **Hypothesis:** Historical sweep shows TIME_STOP_5D expectancy -0.613% vs CURRENT -0.886% (gap +0.273%) AND catastrophic-loss rate 0.00% vs 0.20%. Advisory-only shadow should confirm this gap prospectively before any stop policy change.
- **Data source:** ['aegis_mr_ticket_20260827_india_stop_policy']
- **Result (historical):** India TIME_STOP_5D advisory · loss-control experiment
- **Sample size (forward):** N = 2 shadow days (2026-08-27 onwards)
- **Metric:** expectancy_gap_vs_current
- **Reason for current status:** SUPERSEDED_BY · superseded by aegis_mr_experiment_20260827_e3_stop_loss_cross_market
- **Revisit condition:** N reaches 100 forward observations
- **Acceptance:** Median advisory return over next 5D >= median current-policy return + 0.3% AND catastrophic-loss rate <= current on n>=100 advisory events.
- **Rejection:** MFE-captured drops by more than 0.5% vs current · signals that time-exit is forfeiting winners.

## Recent attempts

- `2026-08-27` n_rows=19

## Governance

- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)
- Zero auto-promotion
- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry