# MON001 · Operator Dashboard — 2026-08-18
_Auto-generated 2026-08-18T15:02:20+00:00_
## Summary
- **State**: `DIVERGED`
- **HALT_REVIEW_REQUIRED**: `False`
- **Forward boundary**: `2026-03-28`
- **Forward trading days accumulated**: 39
- **Days until first Sharpe reading (T30)**: 0
- **Days until first MaxDD reading (T126)**: 87
- **Latest forward recommendation asof**: `2026-08-18`
- **Latest monitoring run**: `2026-08-18`
## Ledger health
- **Rows ingested**: 510
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
| sharpe_forward | -1.1992 | `PASS` | 39 | 30 |
| max_dd_forward | — | `INSUFFICIENT_EVIDENCE` | 39 | 126 |
| ulcer_forward | — | `INSUFFICIENT_EVIDENCE` | 39 | 126 |
## Recent monitoring runs
- `mon001_diagnostics_2026-08-11.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=435
- `mon001_diagnostics_2026-08-12.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=465
- `mon001_diagnostics_2026-08-13.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=480
- `mon001_diagnostics_2026-08-14.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=480
- `mon001_diagnostics_2026-08-18.json` — state=`DIVERGED` halt=`False` recs=510
## Governance reminder
- MON001 does NOT modify production.
- HALT_REVIEW_REQUIRED is an operator-review signal only.
- Do not tune strategy in response to drift alerts.
- Refer to `docs/MON001_OPERATIONS.md` for the incident playbook.