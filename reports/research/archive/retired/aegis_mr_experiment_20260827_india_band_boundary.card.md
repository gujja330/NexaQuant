# aegis_mr_experiment_20260827_india_band_boundary

**Experiment ID:** `aegis_mr_experiment_20260827_india_band_boundary`  
**Status:** `ARCHIVED_LOW_PRIORITY`  
**Route:** `retired`  
**Market:** INDIA  
**Card generated:** 2026-08-27T09:15:46+00:00

## Metadata

- **Hypothesis:** India investability_band ordering QUALITY > MARGINAL > AVOID > OK instead of expected QUALITY > OK > MARGINAL > AVOID. OK band (n=119) has 17.4% 5D WR · below AVOID (n=108) 19.2% · suggesting OK's internal calibration is broken.
- **Data source:** aegis_mr_ticket_20260827_india_band_boundary
- **Result (historical):** —
- **Sample size (forward):** N = 1 shadow days (2026-08-27 onwards)
- **Metric:** band_ordering_monotonicity
- **Reason for current status:** ARCHIVED_LOW_PRIORITY · no successor
- **Revisit condition:** N reaches 100 forward observations
- **Acceptance:** Shadow band ordering becomes strictly monotonic in 5D WR with n>=100 per band across the observation window. Regularized cross-validation split must survive at least one holdout.
- **Rejection:** Any band flips ordering within the window · treat as overfit and abort.

## Recent attempts

- `2026-08-27` n_rows=19

## Governance

- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)
- Zero auto-promotion
- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry