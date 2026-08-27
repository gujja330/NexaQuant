# E3 · Stop-loss cross-market · India TIME_STOP_5D + USA TRAILING_10

**ID:** `aegis_mr_experiment_20260827_e3_stop_loss_cross_market`  
**Market:** CROSS_MARKET  
**Status:** `ACTIVE_SHADOW`  
**5-way label:** `PROMISING_NEED_MORE_DATA`  
**Lifecycle (4-state):** `TESTED`

## 1 · Historical evidence
- n = **500**
- effect = **0.273pp**
- source = `mr_studies_*/mr_stop_loss_sweep_*/mr_conditional_cohorts_*`

## 2 · Forward evidence
- N = **30** / target 100
- WR = None%  ·  avg = None%
- source = `reports/research/mr_evidence_report.json`

## 3 · Statistical confidence
HISTORICAL_MODERATE (n=500) · effect size 0.273pp

## 4 · Decision
**PENDING (forward evidence accumulating)**

## 5 · Reason
INDIA · TIME_STOP_5D expectancy +0.273% + 0.00% catastrophic on n=500. USA · TRAILING_10 expectancy +0.921% PF 1.309 on n=625. Advisory-only shadow confirms both prospectively.

## 6 · Revisit condition
Forward N reaches 100 observations OR baseline shifts materially
