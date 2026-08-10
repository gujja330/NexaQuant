# MON001 · Operator Dashboard — 2026-08-10
_Auto-generated 2026-08-10T11:47:35+00:00_
## Summary
- **State**: `DIVERGED`
- **HALT_REVIEW_REQUIRED**: `False`
- **Forward boundary**: `2026-03-28`
- **Forward trading days accumulated**: 32
- **Days until first Sharpe reading (T30)**: 0
- **Days until first MaxDD reading (T126)**: 94
- **Latest forward recommendation asof**: `2026-08-07`
- **Latest monitoring run**: `2026-08-10`
## Ledger health
- **Rows ingested**: 420
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
| OPS_RUN_FAILED | `WARN` | 1 | — | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: synthetic — should be caught by daily_runner |
| OPS_RUN_FAILED | `WARN` | 2 | 2026-08-07 | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: commissioning synthetic — must be absorbed by daily_runner |
## Metric evidence timeline
| Metric | Forward | Status | Sample | Minimum |
|---|---:|:-:|---:|---:|
| sharpe_forward | 1.3507 | `PASS` | 32 | 30 |
| max_dd_forward | — | `INSUFFICIENT_EVIDENCE` | 32 | 126 |
| ulcer_forward | — | `INSUFFICIENT_EVIDENCE` | 32 | 126 |
## Recent monitoring runs
- `mon001_diagnostics_2026-08-04.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=375
- `mon001_diagnostics_2026-08-05.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=390
- `mon001_diagnostics_2026-08-06.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=405
- `mon001_diagnostics_2026-08-07.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=405
- `mon001_diagnostics_2026-08-10.json` — state=`DIVERGED` halt=`False` recs=420
## Governance reminder
- MON001 does NOT modify production.
- HALT_REVIEW_REQUIRED is an operator-review signal only.
- Do not tune strategy in response to drift alerts.
- Refer to `docs/MON001_OPERATIONS.md` for the incident playbook.