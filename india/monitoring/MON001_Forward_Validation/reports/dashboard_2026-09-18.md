# MON001 · Operator Dashboard — 2026-09-18
_Auto-generated 2026-09-18T14:51:16+00:00_
## Summary
- **State**: `HALT_REVIEW_REQUIRED`
- **HALT_REVIEW_REQUIRED**: `True`
- **Forward boundary**: `2026-03-28`
- **Forward trading days accumulated**: 61
- **Days until first Sharpe reading (T30)**: 0
- **Days until first MaxDD reading (T126)**: 65
- **Latest forward recommendation asof**: `2026-09-17`
- **Latest monitoring run**: `2026-09-18`
## Ledger health
- **Rows ingested**: 794
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
| OPS_DATA_STALE | `WARN` | 1 | — | latest bar 2026-09-11 < previous trading session 2026-09-14 (gap 3 calendar days) |
## Metric evidence timeline
| Metric | Forward | Status | Sample | Minimum |
|---|---:|:-:|---:|---:|
| sharpe_forward | 1.1156 | `PASS` | 61 | 30 |
| max_dd_forward | — | `INSUFFICIENT_EVIDENCE` | 61 | 126 |
| ulcer_forward | — | `INSUFFICIENT_EVIDENCE` | 61 | 126 |
## Recent monitoring runs
- `mon001_diagnostics_2026-09-14.json` — state=`DIVERGED` halt=`False` recs=750
- `mon001_diagnostics_2026-09-15.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=750
- `mon001_diagnostics_2026-09-16.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=780
- `mon001_diagnostics_2026-09-17.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=780
- `mon001_diagnostics_2026-09-18.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=794
## Governance reminder
- MON001 does NOT modify production.
- HALT_REVIEW_REQUIRED is an operator-review signal only.
- Do not tune strategy in response to drift alerts.
- Refer to `docs/MON001_OPERATIONS.md` for the incident playbook.