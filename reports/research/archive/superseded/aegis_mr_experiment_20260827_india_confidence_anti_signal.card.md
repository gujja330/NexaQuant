# aegis_mr_experiment_20260827_india_confidence_anti_signal

**Experiment ID:** `aegis_mr_experiment_20260827_india_confidence_anti_signal`  
**Status:** `SUPERSEDED_BY`  
**Route:** `superseded`  
**Superseded by:** `aegis_mr_experiment_20260827_x1_india_r1_r2_ranking`  
**Market:** INDIA  
**Card generated:** 2026-08-27T09:15:46+00:00

## Metadata

- **Hypothesis:** In India, higher confidence_pct at prediction time predicts LOWER 5D forward win rate. Bucket audit shows WR spread of 23.88pp with monotonicity MIXED_DOWN.
- **Data source:** aegis_mr_ticket_20260827_india_confidence_anti_signal
- **Result (historical):** —
- **Sample size (forward):** N = 1 shadow days (2026-08-27 onwards)
- **Metric:** shadow_5D_WR
- **Reason for current status:** SUPERSEDED_BY · superseded by aegis_mr_experiment_20260827_x1_india_r1_r2_ranking
- **Revisit condition:** N reaches 100 forward observations
- **Acceptance:** Shadow 5D WR >= production 5D WR + 5pp AND shadow avg > production avg + 0.3% on n>=100 forward India predictions.
- **Rejection:** Shadow 5D WR < production - 2pp OR shadow catastrophic-loss rate > production + 0.3pp.

## Recent attempts

- `2026-08-27` n_rows=19

## Governance

- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)
- Zero auto-promotion
- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry