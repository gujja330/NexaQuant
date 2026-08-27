# aegis_mr_experiment_20260827_india_negative_alpha

**Experiment ID:** `aegis_mr_experiment_20260827_india_negative_alpha`  
**Status:** `SUPERSEDED_BY`  
**Route:** `superseded`  
**Superseded by:** `aegis_mr_experiment_20260827_x1_india_r1_r2_ranking`  
**Market:** INDIA  
**Card generated:** 2026-08-27T09:15:46+00:00

## Metadata

- **Hypothesis:** Over 18 days, NSE universe (n=2747) 5D WR=32.25% avg=-0.388%. AEGIS-India (n=392) 5D WR=25.77% avg=-0.729%. Alpha = WR-6.48pp · avg-0.341%. AEGIS-India currently DESTROYS value relative to random pick.
- **Data source:** aegis_mr_ticket_20260827_india_negative_alpha
- **Result (historical):** —
- **Sample size (forward):** N = 1 shadow days (2026-08-27 onwards)
- **Metric:** shadow_alpha_vs_universe
- **Reason for current status:** SUPERSEDED_BY · superseded by aegis_mr_experiment_20260827_x1_india_r1_r2_ranking
- **Revisit condition:** N reaches 100 forward observations
- **Acceptance:** Compound-shadow 5D WR >= universe-WR + 3pp AND compound-shadow avg > universe avg on n>=100 forward India predictions.
- **Rejection:** Any single component regresses beyond -2pp WR when compared to production baseline · re-run components in isolation.

## Recent attempts

- `2026-08-27` n_rows=19

## Governance

- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)
- Zero auto-promotion
- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry