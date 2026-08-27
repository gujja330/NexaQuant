# India R1/R2 Ranking · confidence + top-3 slot filter

**ID:** `aegis_mr_experiment_20260827_x1_india_r1_r2_ranking`  
**Market:** INDIA  
**Status:** `SUPERSEDED_BY`  
**5-way label:** `SUPERSEDED_KEEP_HISTORY`  
**Lifecycle (4-state):** `TESTED`

## 1 · Historical evidence
- n = **0**
- effect = **Nonepp**
- source = `mr_studies_*/mr_stop_loss_sweep_*/mr_conditional_cohorts_*`

## 2 · Forward evidence
- N = **30** / target 100
- WR = None%  ·  avg = None%
- source = `reports/research/mr_evidence_report.json`

## 3 · Statistical confidence
OBSERVATION_ONLY (n=0)

## 4 · Decision
**RETIRED (superseded by aegis_mr_experiment_20260827_e1_india_r1_filter)**

## 5 · Reason
Two mechanisms compound to produce India's negative alpha vs universe: (a) R1 top-3 slot is anti-correlated with outcome when ma20_dist is outside +1..+5, and (b) confidence 70-85 band is an anti-signal. Applying both filters in shadow should raise India 5D WR toward or above universe baseline 32.25%.

## 6 · Revisit condition
Forward N reaches 100 observations OR baseline shifts materially

---
_Historical backtest evidence alone did not earn this bucket. 'successful' is reserved for forward PASS · 'promising' for forward BORDERLINE with directional support · 'failed' for forward FAIL · 'superseded' for retired/archived/replaced._