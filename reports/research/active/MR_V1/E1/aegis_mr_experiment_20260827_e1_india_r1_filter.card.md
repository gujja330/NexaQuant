# E1 · India R1 negative filter (weakest cohorts)

**Experiment ID:** `aegis_mr_experiment_20260827_e1_india_r1_filter`  
**Status:** `ACTIVE_SHADOW`  
**Route:** `active`  
**Market:** INDIA  
**Card generated:** 2026-08-27T09:15:46+00:00

## Metadata

- **Hypothesis:** R1 top-3 with ma20_dist outside +1..+5 (n=82, 14.5% WR) AND R1 confidence 70-85 anti-signal (n=103, 13.16% WR) are the two weakest R1 cohorts. Filtering them should raise R1 5D WR toward R2 baseline 32.16%.
- **Data source:** ['mr_studies_india.json:Q8_rank_slot.top3', 'mr_score_usefulness_india.json:audits.confidence_pct']
- **Result (historical):** E1 · India R1 negative filter (weakest cohorts)
- **Sample size (forward):** N = 2 shadow days (2026-08-27 onwards)
- **Metric:** shadow_R1_5D_WR (after filter)
- **Reason for current status:** ACTIVE_SHADOW · no successor
- **Revisit condition:** N reaches 100 forward observations
- **Acceptance:** Filtered R1 5D WR >= production R1 + 5pp on n>=100
- **Rejection:** Filtered R1 5D WR < production R1 - 3pp

## Recent attempts

- `2026-08-27` n_rows=19

## Governance

- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)
- Zero auto-promotion
- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry