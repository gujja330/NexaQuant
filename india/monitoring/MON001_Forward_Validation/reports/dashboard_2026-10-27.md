# MON001 · Operator Dashboard — 2026-10-27
_Auto-generated 2026-10-27T18:42:06+00:00_
## Summary
- **State**: `HALT_REVIEW_REQUIRED`
- **HALT_REVIEW_REQUIRED**: `True`
- **Forward boundary**: `2026-03-28`
- **Forward trading days accumulated**: 83
- **Days until first Sharpe reading (T30)**: 0
- **Days until first MaxDD reading (T126)**: 43
- **Latest forward recommendation asof**: `2026-10-21`
- **Latest monitoring run**: `2026-10-21`
## Ledger health
- **Rows ingested**: 1088
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
| OPS_RUN_FAILED | `WARN` | 1 | — | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: MON001 baseline envelope drift detected. Cached hash e4ca8ecb97914f4828f6601eb5d05ebe4956099dac7c6df70df13ccaaa482812 != freshly-computed 914f0cf9579e22654ae89e6a313a42ad8f51e549f90550626d31b1c66f16e843. Either the LAB009 diagnostics CSV was mutated or the envelope-building code changed. MON001 refuses to run. |
| OPS_RUN_FAILED | `WARN` | 2 | 2026-10-22 | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: MON001 baseline envelope drift detected. Cached hash e4ca8ecb97914f4828f6601eb5d05ebe4956099dac7c6df70df13ccaaa482812 != freshly-computed 914f0cf9579e22654ae89e6a313a42ad8f51e549f90550626d31b1c66f16e843. Either the LAB009 diagnostics CSV was mutated or the envelope-building code changed. MON001 refuses to run. |
| OPS_RUN_FAILED | `WARN` | 1 | — | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: MON001 baseline envelope drift detected. Cached hash e4ca8ecb97914f4828f6601eb5d05ebe4956099dac7c6df70df13ccaaa482812 != freshly-computed 914f0cf9579e22654ae89e6a313a42ad8f51e549f90550626d31b1c66f16e843. Either the LAB009 diagnostics CSV was mutated or the envelope-building code changed. MON001 refuses to run. |
| OPS_RUN_FAILED | `WARN` | 3 | 2026-10-22 | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: MON001 baseline envelope drift detected. Cached hash e4ca8ecb97914f4828f6601eb5d05ebe4956099dac7c6df70df13ccaaa482812 != freshly-computed 914f0cf9579e22654ae89e6a313a42ad8f51e549f90550626d31b1c66f16e843. Either the LAB009 diagnostics CSV was mutated or the envelope-building code changed. MON001 refuses to run. |
| OPS_RUN_FAILED | `WARN` | 3 | 2026-10-22 | run_mon001.main raised an exception; MON001 metrics unavailable for this pass. tail: RuntimeError: MON001 baseline envelope drift detected. Cached hash e4ca8ecb97914f4828f6601eb5d05ebe4956099dac7c6df70df13ccaaa482812 != freshly-computed 914f0cf9579e22654ae89e6a313a42ad8f51e549f90550626d31b1c66f16e843. Either the LAB009 diagnostics CSV was mutated or the envelope-building code changed. MON001 refuses to run. |
## Metric evidence timeline
| Metric | Forward | Status | Sample | Minimum |
|---|---:|:-:|---:|---:|
| sharpe_forward | 3.3030 | `PASS` | 83 | 30 |
| max_dd_forward | — | `INSUFFICIENT_EVIDENCE` | 83 | 126 |
| ulcer_forward | — | `INSUFFICIENT_EVIDENCE` | 83 | 126 |
## Recent monitoring runs
- `mon001_diagnostics_2026-10-15.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=1046
- `mon001_diagnostics_2026-10-16.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=1060
- `mon001_diagnostics_2026-10-19.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=1074
- `mon001_diagnostics_2026-10-20.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=1074
- `mon001_diagnostics_2026-10-21.json` — state=`HALT_REVIEW_REQUIRED` halt=`True` recs=1088
## Governance reminder
- MON001 does NOT modify production.
- HALT_REVIEW_REQUIRED is an operator-review signal only.
- Do not tune strategy in response to drift alerts.
- Refer to `docs/MON001_OPERATIONS.md` for the incident playbook.