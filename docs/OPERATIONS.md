# AEGIS — Operations Runbook (Phase 2)

> **Goal of this phase (60–90 days): prove the system runs reliably — NOT improve recommendations.**
> No feature work. No model changes. Fix only operational defects. Accumulate live recommendations and
> evidence. In parallel, research (don't build) the first dataset for LAB-001.

## The 30-second morning check
```
python india/ops_check.py
```
Green = production is operationally healthy. The board covers:

| Check | Expected | Meaning |
|-------|----------|---------|
| Data freshness | ≤ 4 days old | yfinance refresh is appending the latest bars |
| Workbook generated | today | the engine produced `reports/AEGIS_LATEST.xlsx` |
| Recommendation count | > 0 | a portfolio was generated |
| Profile | Shield | production default profile |
| Universe size | ≥ 50 | the dynamic tradable universe built |
| Scored recommendations | growing | matured recs are being scored into the registry |
| Evidence updated | today | the scorecard refreshed |
| Recommendation DB | growing | daily snapshots accumulating (lifecycle intact) |

The same check runs in the daily GitHub Action, so a red state is visible in the Actions log too.

## Failure playbook
| Symptom | Likely cause | Action (operational only) |
|---------|--------------|---------------------------|
| Data freshness FAIL | yfinance refresh failed / Yahoo down | re-run `python india/refresh_data.py`; if Yahoo is down, wait — do NOT change the engine |
| Workbook FAIL | engine crashed | read the Action log / run `python india/recommendation_generator.py`; fix the *defect*, not the model |
| Universe size WARN/FAIL | too many symbols filtered | check `python india/universe.py` (turnover/price floors); a data gap, not a model bug |
| Scored recs not growing | registry scoring stalled | confirm `mature_date`s have passed; check the auto-score step |
| Evidence stale | scorecard didn't run | `python india/scorecard.py` |

**Rule:** anything you change in this phase must be a *defect fix*, a *dependency update*, or a *data-source
fix* — never a feature, formula, or threshold. Those are frozen until a LAB earns a change.

## The daily pipeline (already automated, 08:30 IST)
```
refresh data → run engine → update DB → scorecard → Telegram → Google Sheet → commit
```
Run it. Don't touch it. For 60 days. Collect recommendations, evidence, and any operational bugs.

## What "success" looks like in Phase 2
- The morning board is green most business days for ~2 months.
- The recommendation database and registry grow without gaps.
- Known operational failure modes (Yahoo outages, missing tickers) are understood and handled.
- A clean track record of *live* recommendations exists to compare future LAB work against.

Only after that → **Phase 3 (Research): start LAB-001.**
