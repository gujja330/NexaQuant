# MON001 · Operator Dashboard — 2026-10-12
_Auto-generated 2026-10-12T20:11:08+00:00_
## Summary
- **State**: `DIVERGED`
- **HALT_REVIEW_REQUIRED**: `False`
- **Forward boundary**: `2026-03-28`
- **Forward trading days accumulated**: 77
- **Days until first Sharpe reading (T30)**: 0
- **Days until first MaxDD reading (T126)**: 49
- **Latest forward recommendation asof**: `2026-10-12`
- **Latest monitoring run**: `2026-10-12`
## Ledger health
- **Rows ingested**: 1004
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
| sharpe_forward | 2.5819 | `PASS` | 77 | 30 |
| max_dd_forward | — | `INSUFFICIENT_EVIDENCE` | 77 | 126 |
| ulcer_forward | — | `INSUFFICIENT_EVIDENCE` | 77 | 126 |
## Recent monitoring runs
- `mon001_diagnostics_2026-10-06.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=948
- `mon001_diagnostics_2026-10-07.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=962
- `mon001_diagnostics_2026-10-08.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=976
- `mon001_diagnostics_2026-10-09.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=990
- `mon001_diagnostics_2026-10-12.json` — state=`DIVERGED` halt=`False` recs=1004
## Governance reminder
- MON001 does NOT modify production.
- HALT_REVIEW_REQUIRED is an operator-review signal only.
- Do not tune strategy in response to drift alerts.
- Refer to `docs/MON001_OPERATIONS.md` for the incident playbook.