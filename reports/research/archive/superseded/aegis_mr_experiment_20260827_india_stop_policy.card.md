# aegis_mr_experiment_20260827_india_stop_policy

**Experiment ID:** `aegis_mr_experiment_20260827_india_stop_policy`  
**Status:** `SUPERSEDED_BY`  
**Route:** `superseded`  
**Superseded by:** `aegis_mr_experiment_20260827_x2_stop_loss_time_5d`  
**Market:** INDIA  
**Card generated:** 2026-08-27T09:15:46+00:00

## Metadata

- **Hypothesis:** Under 30-day historical replay, TIME_STOP_5D exit produces avg expectancy of -0.613% vs CURRENT -0.886%. TIME_STOP_5D also eliminates all catastrophic >10% losses (0.00% vs 0.20%).
- **Data source:** aegis_mr_ticket_20260827_india_stop_policy
- **Result (historical):** —
- **Sample size (forward):** N = 1 shadow days (2026-08-27 onwards)
- **Metric:** expectancy_gap_vs_current
- **Reason for current status:** SUPERSEDED_BY · superseded by aegis_mr_experiment_20260827_x2_stop_loss_time_5d
- **Revisit condition:** N reaches 100 forward observations
- **Acceptance:** Median advisory return over next 5D >= median current-policy return + 0.3% AND catastrophic-loss rate <= current on n>=100 advisory events.
- **Rejection:** MFE-captured drops by more than 0.5% vs current · signals that time-exit is forfeiting winners.

## Recent attempts

- `2026-08-27` n_rows=19

## Governance

- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)
- Zero auto-promotion
- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry