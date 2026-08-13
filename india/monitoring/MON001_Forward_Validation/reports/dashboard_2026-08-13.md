# MON001 · Operator Dashboard — 2026-08-13
_Auto-generated 2026-08-13T11:46:56+00:00_
## Summary
- **State**: `HALT_REVIEW_REQUIRED`
- **HALT_REVIEW_REQUIRED**: `True`
- **Forward boundary**: `2026-03-28`
- **Forward trading days accumulated**: 36
- **Days until first Sharpe reading (T30)**: 0
- **Days until first MaxDD reading (T126)**: 90
- **Latest forward recommendation asof**: `2026-08-13`
- **Latest monitoring run**: `2026-08-13`
## Ledger health
- **Rows ingested**: 480
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
| sharpe_forward | -0.8069 | `PASS` | 36 | 30 |
| max_dd_forward | — | `INSUFFICIENT_EVIDENCE` | 36 | 126 |
| ulcer_forward | — | `INSUFFICIENT_EVIDENCE` | 36 | 126 |
## Recent monitoring runs
- `mon001_diagnostics_2026-08-07.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=405
- `mon001_diagnostics_2026-08-10.json` — state=`DIVERGED` halt=`False` recs=420
- `mon001_diagnostics_2026-08-11.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=435
- `mon001_diagnostics_2026-08-12.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=465
- `mon001_diagnostics_2026-08-13.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=480
## Governance reminder
- MON001 does NOT modify production.
- HALT_REVIEW_REQUIRED is an operator-review signal only.
- Do not tune strategy in response to drift alerts.
- Refer to `docs/MON001_OPERATIONS.md` for the incident playbook.