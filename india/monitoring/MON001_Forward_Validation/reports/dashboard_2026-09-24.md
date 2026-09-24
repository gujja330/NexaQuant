# MON001 · Operator Dashboard — 2026-09-24
_Auto-generated 2026-09-24T19:30:50+00:00_
## Summary
- **State**: `HALT_REVIEW_REQUIRED`
- **HALT_REVIEW_REQUIRED**: `True`
- **Forward boundary**: `2026-03-28`
- **Forward trading days accumulated**: 66
- **Days until first Sharpe reading (T30)**: 0
- **Days until first MaxDD reading (T126)**: 60
- **Latest forward recommendation asof**: `2026-09-24`
- **Latest monitoring run**: `2026-09-24`
## Ledger health
- **Rows ingested**: 850
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
_No active alerts._
## Metric evidence timeline
| Metric | Forward | Status | Sample | Minimum |
|---|---:|:-:|---:|---:|
| sharpe_forward | 1.6762 | `PASS` | 66 | 30 |
| max_dd_forward | — | `INSUFFICIENT_EVIDENCE` | 66 | 126 |
| ulcer_forward | — | `INSUFFICIENT_EVIDENCE` | 66 | 126 |
## Recent monitoring runs
- `mon001_diagnostics_2026-09-18.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=794
- `mon001_diagnostics_2026-09-21.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=808
- `mon001_diagnostics_2026-09-22.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=822
- `mon001_diagnostics_2026-09-23.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=836
- `mon001_diagnostics_2026-09-24.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=850
## Governance reminder
- MON001 does NOT modify production.
- HALT_REVIEW_REQUIRED is an operator-review signal only.
- Do not tune strategy in response to drift alerts.
- Refer to `docs/MON001_OPERATIONS.md` for the incident playbook.