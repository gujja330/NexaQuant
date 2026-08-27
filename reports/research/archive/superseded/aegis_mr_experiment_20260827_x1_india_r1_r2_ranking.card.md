# India R1/R2 Ranking · confidence + top-3 slot filter

**Experiment ID:** `aegis_mr_experiment_20260827_x1_india_r1_r2_ranking`  
**Status:** `SUPERSEDED_BY`  
**Route:** `superseded`  
**Superseded by:** `aegis_mr_experiment_20260827_e1_india_r1_filter`  
**Market:** INDIA  
**Card generated:** 2026-08-27T09:15:46+00:00

## Metadata

- **Hypothesis:** Two mechanisms compound to produce India's negative alpha vs universe: (a) R1 top-3 slot is anti-correlated with outcome when ma20_dist is outside +1..+5, and (b) confidence 70-85 band is an anti-signal. Applying both filters in shadow should raise India 5D WR toward or above universe baseline 32.25%.
- **Data source:** ['aegis_mr_ticket_20260827_india_confidence_anti_signal', 'aegis_mr_ticket_20260827_india_top3_rank_inversion', 'aegis_mr_ticket_20260827_india_negative_alpha']
- **Result (historical):** India R1/R2 Ranking · confidence + top-3 slot filter
- **Sample size (forward):** N = 2 shadow days (2026-08-27 onwards)
- **Metric:** shadow_5D_WR
- **Reason for current status:** SUPERSEDED_BY · superseded by aegis_mr_experiment_20260827_e1_india_r1_filter
- **Revisit condition:** N reaches 100 forward observations
- **Acceptance:** Shadow 5D WR >= production 5D WR + 5pp AND shadow avg > production avg + 0.3% on n>=100 forward India predictions.
- **Rejection:** Shadow 5D WR < production - 3pp OR daily rec-count drops >30% for 5 consecutive days.

## Recent attempts

- `2026-08-27` n_rows=19

## Governance

- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)
- Zero auto-promotion
- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry