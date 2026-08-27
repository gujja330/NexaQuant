# aegis_mr_experiment_20260827_india_top3_rank_inversion

**Experiment ID:** `aegis_mr_experiment_20260827_india_top3_rank_inversion`  
**Status:** `SUPERSEDED_BY`  
**Route:** `superseded`  
**Superseded by:** `aegis_mr_experiment_20260827_x1_india_r1_r2_ranking`  
**Market:** INDIA  
**Card generated:** 2026-08-27T09:15:46+00:00

## Metadata

- **Hypothesis:** India R1 places QUALITY(57%) + OK(40%) high-confidence stocks in top-3 slots · these have 14.5% 5D WR. Meanwhile R2 rank_4_7 (n=56, 47% WR, +0.53% avg) is the only positive cohort. The ranker's top-3 selection is anti-correlated with outcome.
- **Data source:** aegis_mr_ticket_20260827_india_top3_rank_inversion
- **Result (historical):** —
- **Sample size (forward):** N = 1 shadow days (2026-08-27 onwards)
- **Metric:** shadow_top3_5D_WR
- **Reason for current status:** SUPERSEDED_BY · superseded by aegis_mr_experiment_20260827_x1_india_r1_r2_ranking
- **Revisit condition:** N reaches 100 forward observations
- **Acceptance:** Shadow top-3 5D WR >= production top-3 5D WR + 10pp AND does NOT reduce rank_4_7 quality by more than 2pp on n>=50 top-3 candidates.
- **Rejection:** Daily rec-count drop > 30% for 5 consecutive days OR shadow top-3 5D WR < production top-3 - 3pp.

## Recent attempts

- `2026-08-27` n_rows=19

## Governance

- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)
- Zero auto-promotion
- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry