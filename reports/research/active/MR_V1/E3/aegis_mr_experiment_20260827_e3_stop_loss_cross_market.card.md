# E3 · Stop-loss cross-market · India TIME_STOP_5D + USA TRAILING_10

**Experiment ID:** `aegis_mr_experiment_20260827_e3_stop_loss_cross_market`  
**Status:** `ACTIVE_SHADOW`  
**Route:** `active`  
**Market:** CROSS_MARKET  
**Card generated:** 2026-08-27T09:15:46+00:00

## Metadata

- **Hypothesis:** INDIA · TIME_STOP_5D expectancy +0.273% + 0.00% catastrophic on n=500. USA · TRAILING_10 expectancy +0.921% PF 1.309 on n=625. Advisory-only shadow confirms both prospectively.
- **Data source:** ['mr_stop_loss_sweep_india.json:by_policy', 'mr_stop_loss_sweep_usa.json:by_policy']
- **Result (historical):** E3 · Stop-loss cross-market · India TIME_STOP_5D + USA TRAILING_10
- **Sample size (forward):** N = 2 shadow days (2026-08-27 onwards)
- **Metric:** expectancy_gap_vs_current per market
- **Reason for current status:** ACTIVE_SHADOW · no successor
- **Revisit condition:** N reaches 100 forward observations
- **Acceptance:** INDIA: advisory median return >= CURRENT median + 0.3% AND cat-loss <= CURRENT on n>=100. USA: advisory net of TRAILING_10 >= CURRENT + 0.5% expectancy on n>=100.
- **Rejection:** MFE-captured drops by >0.5% vs CURRENT

## Recent attempts

- `2026-08-27` n_rows=19

## Governance

- Frozen · overrides require CEO explicit phrase (see MR_V1_EXPERIMENTS_FROZEN.md)
- Zero auto-promotion
- Locked-layer paths not touched: `backend/delivery`, canonical JSON, R1/R2/Registry