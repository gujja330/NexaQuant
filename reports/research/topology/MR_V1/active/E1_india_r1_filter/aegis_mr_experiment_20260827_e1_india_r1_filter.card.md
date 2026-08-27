# E1 · India R1 negative filter (weakest cohorts)

**ID:** `aegis_mr_experiment_20260827_e1_india_r1_filter`  
**Market:** INDIA  
**Status:** `ACTIVE_SHADOW`  
**5-way label:** `PROMISING_NEED_MORE_DATA`  
**Lifecycle (4-state):** `TESTED`

## 1 · Historical evidence
- n = **314**
- effect = **-11.35pp**
- source = `mr_studies_*/mr_stop_loss_sweep_*/mr_conditional_cohorts_*`

## 2 · Forward evidence
- N = **30** / target 100
- WR = None%  ·  avg = None%
- source = `reports/research/mr_evidence_report.json`

## 3 · Statistical confidence
HISTORICAL_STRONG (n=314, effect -11.35pp) · forward evidence needed

## 4 · Decision
**PENDING (forward evidence accumulating)**

## 5 · Reason
R1 top-3 with ma20_dist outside +1..+5 (n=82, 14.5% WR) AND R1 confidence 70-85 anti-signal (n=103, 13.16% WR) are the two weakest R1 cohorts. Filtering them should raise R1 5D WR toward R2 baseline 32.16%.

## 6 · Revisit condition
Forward N reaches 100 observations OR baseline shifts materially
