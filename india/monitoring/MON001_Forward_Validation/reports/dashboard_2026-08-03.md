# MON001 · Operator Dashboard — 2026-08-03
_Auto-generated 2026-08-03T13:41:43+00:00_
## Summary
- **State**: `DIVERGED`
- **HALT_REVIEW_REQUIRED**: `False`
- **Forward boundary**: `2026-03-28`
- **Forward trading days accumulated**: 28
- **Days until first Sharpe reading (T30)**: 2
- **Days until first MaxDD reading (T126)**: 98
- **Latest forward recommendation asof**: `2026-08-03`
- **Latest monitoring run**: `2026-08-03`
## Ledger health
- **Rows ingested**: 360
- **Chain integrity**: `True`  (chain intact)
- **Duplicate rec_ids under same fingerprint**: 0
- **Forward boundary breach**: no
## Baseline fingerprint
- **Status**: `OK`
- **Sealed hash**: `e4c070673568c52d...`
- **Current hash**: `e4c070673568c52d...`
## Broker status
- **Available**: `False`
- **Reason**: broker_angelone.py order placement is disabled; no fill history ingested. MON001 remains PAPER_ONLY at seal time.
## Active alerts (last 7 days, WARN or higher)
| Dimension | Severity | Consecutive | First seen | Reason |
|---|:-:|:-:|:-:|---|
| OPS_DATA_STALE | `WARN` | 1 | — | latest bar 2026-07-24 < previous trading session 2026-07-27 (gap 3 calendar days) |
## Metric evidence timeline
| Metric | Forward | Status | Sample | Minimum |
|---|---:|:-:|---:|---:|
| sharpe_forward | — | `INSUFFICIENT_EVIDENCE` | 28 | 30 |
| max_dd_forward | — | `INSUFFICIENT_EVIDENCE` | 28 | 126 |
| ulcer_forward | — | `INSUFFICIENT_EVIDENCE` | 28 | 126 |
## Recent monitoring runs
- `mon001_diagnostics_2026-07-28.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=300
- `mon001_diagnostics_2026-07-29.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=315
- `mon001_diagnostics_2026-07-30.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=330
- `mon001_diagnostics_2026-07-31.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=345
- `mon001_diagnostics_2026-08-03.json` — state=`DIVERGED` halt=`False` recs=360
## Governance reminder
- MON001 does NOT modify production.
- HALT_REVIEW_REQUIRED is an operator-review signal only.
- Do not tune strategy in response to drift alerts.
- Refer to `docs/MON001_OPERATIONS.md` for the incident playbook.