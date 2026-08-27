# AEGIS · Research Archive Index

_Generated 2026-08-27T09:15:47+00:00_

**Total findings tracked:** 15

**Status counts:** `{'SUCCESSFUL_PROMOTION_CANDIDATE': 0, 'PROMISING_NEED_MORE_DATA': 3, 'FAILED_RETAIN_EVIDENCE': 0, 'SUPERSEDED_KEEP_HISTORY': 9, 'DATA_GAP_FIX_DATA': 3}`

---


## SUCCESSFUL_PROMOTION_CANDIDATE (0)

_(none · this bucket earned by future forward evidence)_

## PROMISING_NEED_MORE_DATA (3)

| Title | Market | Hist n | Fwd N | Decision | Revisit |
|---|---|---:|---:|---|---|
| E1 · India R1 negative filter (weakest cohorts) | INDIA | 100 | 2/100 | PENDING (accumulating) | forward N reaches 100 observations |
| E2 · India R2 rank_4_7 + RSI STRONG positive-boost | INDIA | 100 | 2/100 | PENDING (accumulating) | forward N reaches 100 observations |
| E3 · Stop-loss cross-market · India TIME_STOP_5D + USA TRAIL | CROSS_MARKET | 100 | 2/100 | PENDING (accumulating) | forward N reaches 100 observations |

## FAILED_RETAIN_EVIDENCE (0)

_(none · this bucket earned by future forward evidence)_

## SUPERSEDED_KEEP_HISTORY (9)

| Title | Market | Hist n | Fwd N | Decision | Revisit |
|---|---|---:|---:|---|---|
| ? | INDIA | 100 | 1/100 | ARCHIVED | forward N reaches 100 observations |
| ? | INDIA | 100 | 1/100 | RETIRED (→ aegis_mr_experiment_20260827_x1_india_r1_r2_ranking) | forward N reaches 100 observations |
| ? | INDIA | 100 | 1/100 | RETIRED (→ aegis_mr_experiment_20260827_x1_india_r1_r2_ranking) | forward N reaches 100 observations |
| ? | INDIA | 100 | 1/100 | RETIRED (→ aegis_mr_experiment_20260827_x2_stop_loss_time_5d) | forward N reaches 100 observations |
| ? | INDIA | 100 | 1/100 | RETIRED (→ aegis_mr_experiment_20260827_x1_india_r1_r2_ranking) | forward N reaches 100 observations |
| India R1/R2 Ranking · confidence + top-3 slot filter | INDIA | 100 | 2/100 | RETIRED (→ aegis_mr_experiment_20260827_e1_india_r1_filter) | forward N reaches 100 observations |
| India TIME_STOP_5D advisory · loss-control experiment | INDIA | 100 | 2/100 | RETIRED (→ aegis_mr_experiment_20260827_e3_stop_loss_cross_market) | forward N reaches 100 observations |
| Technical filter · RSI + MA20 evidence-backed edges | INDIA | 100 | 2/100 | ARCHIVED | forward N reaches 100 observations |
| USA MID-cap tilt · cap-weighted selection experiment | USA | 100 | 1/100 | ARCHIVED | forward N reaches 100 observations |

## DATA_GAP_FIX_DATA (3)

| Title | Market | Hist n | Fwd N | Decision | Revisit |
|---|---|---:|---:|---|---|
| Momentum · Historical corpus empty | BOTH | 0 | 0/— | BLOCKED_ON_DATA | N forward >= 20 sessions |
| USA · Fundamentals parquet empty | USA | 0 | 0/— | BLOCKED_ON_DATA | coverage >= 95% of daily-pred tickers |
| USA · Canonical portfolio JSON not locally available | USA | 0 | 0/— | BLOCKED_ON_DATA | next USA CI publishes canonical + XLSX artifact |

---

## Rules

- **SUCCESSFUL_PROMOTION_CANDIDATE:** forward acceptance PASS · never populated by historical evidence alone.
- **PROMISING_NEED_MORE_DATA:** forward BORDERLINE or ACTIVE_SHADOW · N < 100.
- **FAILED_RETAIN_EVIDENCE:** forward FAIL · retained as negative finding.
- **SUPERSEDED_KEEP_HISTORY:** retired or replaced · shadow output continues for continuity.
- **DATA_GAP_FIX_DATA:** blocked by data availability · fix data source before evaluating.

## Compliance

- No historical/failed findings deleted.
- Zero production changes.
- 5-way label uniform across cards and this index.