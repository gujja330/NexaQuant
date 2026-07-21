# MON001 · Operator Dashboard — 2026-07-21
_Auto-generated 2026-07-21T12:24:14+00:00_
## Summary
- **State**: `DIVERGED`
- **HALT_REVIEW_REQUIRED**: `False`
- **Forward boundary**: `2026-03-28`
- **Forward trading days accumulated**: 17
- **Days until first Sharpe reading (T30)**: 13
- **Days until first MaxDD reading (T126)**: 109
- **Latest forward recommendation asof**: `2026-07-20`
- **Latest monitoring run**: `2026-07-21`
## Ledger health
- **Rows ingested**: 255
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
| OPS_RUN_FAILED | `WARN` | 2 | 2026-07-14 | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: MON001 baseline envelope drift detected. Cached hash d017b352be54412655142d7bd00dd2d6fcbb1d2a50ce122d8e28e03de4197323 != freshly-computed f988b3df1572c45835d49361ed06e5cf5ff4231963f95a09a34fc6e26216015b. Either the LAB009 diagnostics CSV was mutated or the envelope-building code changed. MON001 refuses to run. |
| OPS_RUN_FAILED | `WARN` | 2 | 2026-07-14 | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: synthetic — should be caught by daily_runner |
| OPS_RUN_FAILED | `WARN` | 2 | 2026-07-14 | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: synthetic — should be caught by daily_runner |
| OPS_RUN_FAILED | `WARN` | 2 | 2026-07-14 | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: synthetic — should be caught by daily_runner |
| OPS_RUN_FAILED | `WARN` | 2 | 2026-07-14 | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: synthetic — should be caught by daily_runner |
| OPS_RUN_FAILED | `WARN` | 2 | 2026-07-14 | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: synthetic — should be caught by daily_runner |
| OPS_RUN_FAILED | `WARN` | 2 | 2026-07-14 | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: synthetic — should be caught by daily_runner |
| OPS_DATA_STALE | `WARN` | 1 | — | latest bar 2026-07-17 < previous trading session 2026-07-20 (gap 3 calendar days) |
## Metric evidence timeline
| Metric | Forward | Status | Sample | Minimum |
|---|---:|:-:|---:|---:|
| sharpe_forward | — | `INSUFFICIENT_EVIDENCE` | 17 | 30 |
| max_dd_forward | — | `INSUFFICIENT_EVIDENCE` | 17 | 126 |
| ulcer_forward | — | `INSUFFICIENT_EVIDENCE` | 17 | 126 |
## Recent monitoring runs
- `mon001_diagnostics_2026-07-15.json` — state=`DIVERGED` halt=`False` recs=150
- `mon001_diagnostics_2026-07-16.json` — state=`DIVERGED` halt=`False` recs=150
- `mon001_diagnostics_2026-07-17.json` — state=`DIVERGED` halt=`False` recs=240
- `mon001_diagnostics_2026-07-20.json` — state=`DIVERGED` halt=`False` recs=255
- `mon001_diagnostics_2026-07-21.json` — state=`DIVERGED` halt=`False` recs=255
## Governance reminder
- MON001 does NOT modify production.
- HALT_REVIEW_REQUIRED is an operator-review signal only.
- Do not tune strategy in response to drift alerts.
- Refer to `docs/MON001_OPERATIONS.md` for the incident playbook.