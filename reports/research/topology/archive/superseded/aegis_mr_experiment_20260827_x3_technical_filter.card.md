# Technical filter · RSI + MA20 evidence-backed edges

**ID:** `aegis_mr_experiment_20260827_x3_technical_filter`  
**Market:** INDIA  
**Status:** `ARCHIVED_FOR_LATER`  
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
**ARCHIVED (ARCHIVED_FOR_LATER)**

## 5 · Reason
India OVERSOLD_lt30 RSI has 43.75% 5D WR (+18pp vs baseline). India above_+1_+5 ma20_dist has 37.17% WR (+11pp). India WEAK 30-45 RSI has 18.25% WR (-7pp) and below_-5_-1 ma20_dist has 17.97% WR (-8pp). Positive-filter tag on the good buckets and negative-filter tag on the bad ones should predict forward outcomes prospectively.

## 6 · Revisit condition
Forward N reaches 100 observations OR baseline shifts materially

---
_Historical backtest evidence alone did not earn this bucket. 'successful' is reserved for forward PASS · 'promising' for forward BORDERLINE with directional support · 'failed' for forward FAIL · 'superseded' for retired/archived/replaced._