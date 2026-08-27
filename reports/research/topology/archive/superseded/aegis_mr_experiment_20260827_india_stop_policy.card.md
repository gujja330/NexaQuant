# ?

**ID:** `aegis_mr_experiment_20260827_india_stop_policy`  
**Market:** INDIA  
**Status:** `SUPERSEDED_BY`  
**5-way label:** `SUPERSEDED_KEEP_HISTORY`  
**Lifecycle (4-state):** `TESTED`

## 1 · Historical evidence
- n = **0**
- effect = **Nonepp**
- source = `mr_studies_*/mr_stop_loss_sweep_*/mr_conditional_cohorts_*`

## 2 · Forward evidence
- N = **15** / target 100
- WR = None%  ·  avg = None%
- source = `reports/research/mr_evidence_report.json`

## 3 · Statistical confidence
OBSERVATION_ONLY (n=0)

## 4 · Decision
**RETIRED (superseded by aegis_mr_experiment_20260827_x2_stop_loss_time_5d)**

## 5 · Reason
Under 30-day historical replay, TIME_STOP_5D exit produces avg expectancy of -0.613% vs CURRENT -0.886%. TIME_STOP_5D also eliminates all catastrophic >10% losses (0.00% vs 0.20%).

## 6 · Revisit condition
Forward N reaches 100 observations OR baseline shifts materially

---
_Historical backtest evidence alone did not earn this bucket. 'successful' is reserved for forward PASS · 'promising' for forward BORDERLINE with directional support · 'failed' for forward FAIL · 'superseded' for retired/archived/replaced._