# AEGIS — Non-Price Dataset Shortlist (research planning, NOT implementation)

> A planning artifact for the Research Lab. Each dataset must clear the data-layer gate (IC · RQS lift ·
> walk-forward · DSR) and beat the frozen baseline before it influences production. One dataset at a time.

| Dataset | Cost | Coverage | Point-in-time? | Ingestion difficulty | Priority | Maps to |
|---------|------|----------|----------------|----------------------|----------|---------|
| Quarterly earnings surprise / guidance / revisions | Free–Low | High (NSE) | Yes (announcement date) | Medium | ⭐⭐⭐⭐⭐ | LAB-001 |
| Point-in-time fundamentals (ROE/margins/debt/growth) | Medium | High | Yes (as-reported) | High | ⭐⭐⭐⭐⭐ | LAB-002 |
| Corporate actions / events (orders, approvals, M&A, buyback) | Free | High | Yes (announcement) | Low | ⭐⭐⭐⭐ | LAB-003 |
| FII / DII flows (aggregate + stock-level holdings) | Free | Medium | Yes (disclosure) | Low | ⭐⭐⭐⭐ | LAB-004 |
| Bulk / block deals | Free | Medium | Yes | Low | ⭐⭐⭐ | LAB-004 |
| Mutual-fund holdings | Free–Low | Medium | Yes (monthly) | Medium | ⭐⭐⭐ | LAB-004 |
| Analyst estimate revisions | Expensive | Medium | Yes | High | ⭐⭐⭐ | LAB-002/005 |

## Selection notes
- **Start with earnings (LAB-001):** highest expected information, broadly available, manageable to ingest.
- **Point-in-time is non-negotiable.** Any dataset keyed to the period it *describes* rather than the date
  it became *known* introduces look-ahead and invalidates the gate verdict.
- **Coverage and missing-% matter as much as the signal.** A high-IC dataset covering 40% of the universe
  is weaker in practice than a modest one covering 90%. The gate + journal record both.
- **Free first.** Exhaust free/official NSE/exchange sources before paying for vendor feeds.

## Process for each (no shortcuts)
```
Acquire → Clean → Point-in-time align → Feature engineer → IC → Incremental lift
       → Walk-forward → Forward paper → Promotion gate (beat frozen baseline) → Promote / Reject
```
Every outcome — pass or fail — gets a page in `docs/RESEARCH_JOURNAL.md`.

_This file is a shortlist to research, not a build list. Filling in real "Cost/Coverage/PIT" values from
actual source investigation is the first concrete task of the research phase._
