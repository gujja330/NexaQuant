# MON001 · Operator Dashboard — 2026-07-28
_Auto-generated 2026-07-28T12:54:42+00:00_
## Summary
- **State**: `HALT_REVIEW_REQUIRED`
- **HALT_REVIEW_REQUIRED**: `True`
- **Forward boundary**: `2026-03-28`
- **Forward trading days accumulated**: 22
- **Days until first Sharpe reading (T30)**: 8
- **Days until first MaxDD reading (T126)**: 104
- **Latest forward recommendation asof**: `2026-07-24`
- **Latest monitoring run**: `2026-07-28`
## Ledger health
- **Rows ingested**: 300
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
| sharpe_forward | — | `INSUFFICIENT_EVIDENCE` | 22 | 30 |
| max_dd_forward | — | `INSUFFICIENT_EVIDENCE` | 22 | 126 |
| ulcer_forward | — | `INSUFFICIENT_EVIDENCE` | 22 | 126 |
## Recent monitoring runs
- `mon001_diagnostics_2026-07-22.json` — state=`DIVERGED` halt=`False` recs=270
- `mon001_diagnostics_2026-07-23.json` — state=`DIVERGED` halt=`False` recs=285
- `mon001_diagnostics_2026-07-24.json` — state=`DIVERGED` halt=`False` recs=300
- `mon001_diagnostics_2026-07-27.json` — state=`DIVERGED` halt=`False` recs=300
- `mon001_diagnostics_2026-07-28.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=300
## Governance reminder
- MON001 does NOT modify production.
- HALT_REVIEW_REQUIRED is an operator-review signal only.
- Do not tune strategy in response to drift alerts.
- Refer to `docs/MON001_OPERATIONS.md` for the incident playbook.