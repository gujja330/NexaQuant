# USA MID-cap tilt · cap-weighted selection experiment

**Experiment ID:** `aegis_mr_experiment_20260827_x3_usa_mid_cap_tilt`  
**Status:** `ARCHIVED_FOR_LATER`  
**Route:** `retired`  
**Market:** USA  
**Card generated:** 2026-08-27T09:15:46+00:00

## Metadata

- **Hypothesis:** 30D corpus shows USA MID cap n=622 · 5D WR=46.60% · avg=+0.10% (only USA positive-avg cohort) beats LARGE n=459 · 5D WR=35.96% · avg=-0.84% by 10.64pp WR. Tilting selection toward MID and away from LARGE in shadow should confirm this prospectively.
- **Data source:** ['derived_from_mr_studies_Q3_cap_bucket']
- **Result (historical):** USA MID-cap tilt · cap-weighted selection experiment
- **Sample size (forward):** N = 1 shadow days (2026-08-27 onwards)
- **Metric:** shadow_mid_5D_WR - shadow_large_5D_WR
- **Reason for current status:** ARCHIVED_FOR_LATER · no successor
- **Revisit condition:** N reaches 100 forward observations
- **Acceptance:** shadow MID 5D WR - LARGE 5D WR >= 8pp on n>=100 forward USA predictions AND MID avg > LARGE avg by >= 0.5%.
- **Rejection:** MID - LARGE gap < 3pp forward OR MID catastrophic-loss rate > LARGE + 0.5pp.

## Governance

- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)
- Zero auto-promotion
- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry