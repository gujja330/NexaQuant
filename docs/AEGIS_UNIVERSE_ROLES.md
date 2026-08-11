# AEGIS Universe Roles · Definitive Semantics

**Locked: 2026-08-11 · CEO P0 pipeline hygiene sprint**

The word "recommendation" appears in many files with very different meanings.
This document is the SINGLE SOURCE OF TRUTH for what each artifact represents.
Every writer stamps a `universe_role` field so downstream code can behave
correctly without guessing from file names.

## The four roles

| role | meaning | actionable? |
|---|---|---|
| `universe_scan`        | full universe technically scored, no selection applied  | ❌ NO |
| `selected_candidates`  | canonical selected set for the day (SSoT)                | ✅ YES |
| `sized_positions`      | selected set after risk budgeting (Kelly/vol/caps)       | ✅ YES |
| `portfolio_positions`  | final portfolio after N-name construction + cash rules  | ✅ YES |

## Canonical file map

### India

| file | role | typical size | writer |
|---|---|---|---|
| `data/aegis_today.csv`                 | `universe_scan`       | ~500 rows | `india/recommendation_generator.py` |
| `reports/recommendations_v3.json`      | `selected_candidates` | 15        | `backend/recommendation/adaptive_rec_v2/…` |
| `reports/recommendations.json`         | `selected_candidates` | 15        | `backend/recommendation/ssot/bridge.py` |
| `reports/sized_positions.json`         | `sized_positions`     | 5-15      | `backend/risk_engine/…` |
| `reports/portfolio_v3.json`            | `portfolio_positions` | 5-8       | `backend/portfolio/portfolio_engine/…` |

### USA

| file | role | typical size | writer |
|---|---|---|---|
| `usa/data/raw/us/*.parquet`               | `universe_scan` (raw)   | 516 tickers | ingest |
| `usa/reports/recommendations.json`        | `universe_scan`         | 507         | `usa/research/recommendations/run.py` |
| `usa/reports/recommendations_v3.json`     | `selected_candidates`   | 15          | `backend/recommendation/adaptive_rec_v2/…` |
| `usa/reports/sized_positions.json`        | `sized_positions`       | 10          | `backend/risk_engine/…` |
| `usa/reports/portfolio_v3.json`           | `portfolio_positions`   | 5           | `backend/portfolio/portfolio_engine/…` |

**Note**: India's `recommendations.json` is the SELECTED set (15).
USA's `recommendations.json` is the UNIVERSE SCAN (507). Same name,
opposite semantics. This is the exact confusion this doc exists to end.
Use `universe_role` for programmatic disambiguation, never the filename.

## P0 outcome dataset ingestion rule

`backend/research/outcome_dataset.py` sources from:

1. `position_store/{market}/positions.json` — canonical opened positions
2. `reports/research/rank_history.jsonl` — runner tag per emission

It NEVER reads `recommendations.json` or the universe scan. Only positions
with a `rank_history` entry become `OutcomeRow`s. This means:

- `n_positions` in outcome_dataset ≠ number of recommendations for the day
- `n_positions` = cumulative opened positions across all past days
- Runner attribution (R1/R2) comes from rank_history, not the scan file

## The 15 vs 507 vs 5 breakdown

For a typical USA daily run:

```
516  universe (S&P + MidCap 400)
 -9  SKIP: no price data (delisted, class B tickers, etc.)
507  → usa/reports/recommendations.json          [universe_scan · not actionable]
 15  → usa/reports/recommendations_v3.json       [selected_candidates · SSoT]
 10  → usa/reports/sized_positions.json          [sized_positions · risk-budgeted]
  5  → usa/reports/portfolio_v3.json             [portfolio_positions · final]
```

## Contract for new code

Any new consumer of a `recommendations*.json` file MUST:

1. Read `universe_role` from the payload
2. If `universe_role != "selected_candidates"`, do not treat rows as actionable
3. If `universe_role` is missing (pre-2026-08-11 artifact), assume `universe_scan`
   and refuse to act on it

Any new writer of a `recommendations*.json` file MUST stamp `universe_role`
and `universe_role_note` at emission time.

## History

- **2026-08-11**: CEO manual pipeline audit surfaced 15-vs-507 confusion in
  the same run. Root cause: identical file name, opposite semantics, no
  programmatic marker. This doc + `universe_role` stamps close that gap
  without touching model logic.
