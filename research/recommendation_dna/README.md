# DEV028 — Recommendation DNA Engine (v0.1)

Every recommendation becomes an immutable, versioned, searchable record.
Append-only. Nothing forgotten. Every future analysis has a complete lifecycle to draw on.

## Directory structure

```
research/recommendation_dna/
├── lib/
│   ├── dna_schema.py       DNARecord dataclass with 30+ fields
│   ├── store.py            Append-only parquet-backed store, dedup by content key
│   ├── versioning.py       Detects material changes, increments version
│   └── search.py           Query interface + corpus statistics
├── compute/engine.py        Ingest from DEV023 recommendations.json
├── publish/bundle.py        5 output files
├── tests/test_smoke.py      16 tests, all pass
├── run.py                    CLI with search flags
└── README.md
```

## DNA record fields (30+)

**Identity**: `dna_id` (per-version UUID) · `recommendation_id` (stable REC-*) · `version` · `snapshot_utc` · `ticker`

**Hierarchy**: `sector` · `industry` · `company_score` · `sector_score` · `industry_score` · `global_score`

**Recommendation**: `recommendation_type` · `action` · `confidence` · `classification` · `composite_decision_score` · `conviction_pct`

**Entry/Exit plan**: `entry_price` · `stop_loss` · `target_1` · `target_2` · `trailing_stop` · `expected_holding_days`

**Portfolio membership**: `in_target_portfolios[]` · `portfolio_weight`

**Rationale**: `reasons_for[]` · `reasons_against[]`

**Outcome (populated after close)**: `outcome_return_pct` · `outcome_win` · `outcome_mfe_pct` · `outcome_mae_pct` · `outcome_exit_reason` · `outcome_holding_days` · `doctor_categories[]`

**Provenance**: `source_report` · `code_sha` · `written_at_utc`

## Versioning

A new version is created when any of these change:

- `recommendation_type`, `action`, `classification`
- `target_1`, `target_2`, `stop_loss`, `trailing_stop`

Identical re-ingests are deduplicated by content-key hash (SHA256 of `recommendation_id + version + snapshot_utc`). Idempotent — running the ingest twice adds zero rows the second time.

## Execution

```bash
# Ingest current DEV023 recommendations
python research/recommendation_dna/run.py

# Stats-only (no ingest)
python research/recommendation_dna/run.py --stats-only

# Search
python research/recommendation_dna/run.py --search-ticker IPCALAB
python research/recommendation_dna/run.py --search-sector Pharma
python research/recommendation_dna/run.py --search-recommendation Strong-Buy

# Smoke tests
python research/recommendation_dna/tests/test_smoke.py    # 16 tests
```

## Outputs (all under `reports/`)

| File | Contents |
|:--|:--|
| `recommendation_dna.json` | Latest version of every recommendation |
| `recommendation_history.json` | All versions grouped by `recommendation_id` |
| `recommendation_versions.json` | Per-rec version summary with first/latest snapshots |
| `recommendation_statistics.json` | Corpus-wide statistics |
| `recommendation_dna.parquet` | Full store as parquet |

## Store location

`data/market_intelligence/derived/recommendation_dna_store.parquet`

- Append-only
- Content-key deduplicated
- Never overwritten
- Regenerable if lost (v0.1) — future versions may add a WAL for durability

## First live ingest (2026-07-17)

```
Records added:     208 (all Strong-Buy/Buy/Watchlist/Avoid recs from DEV023)
Records deduped:   0 (first ingest)
Corpus statistics:
  Records:                208
  Unique tickers:         208
  Unique recommendations: 208

  By recommendation:
    Avoid:      127
    Buy:        44
    Watchlist:  30
    Strong-Buy: 7

  Versions: avg=1.0, max=1, with_updates=0 (first snapshot)
```

## Search example

```
python research/recommendation_dna/run.py --search-recommendation Strong-Buy

7 row(s) matched
   ticker  version  recommendation_type  confidence  company_score
  IPCALAB        1           Strong-Buy         1.0           83.5
KALYANKJIL       1           Strong-Buy         1.0           81.9
 SONACOMS        1           Strong-Buy         1.0           80.6
 EXIDEIND        1           Strong-Buy         1.0           78.1
ZYDUSLIFE        1           Strong-Buy         1.0           75.6
   RADICO        1           Strong-Buy         1.0           77.9
     OFSS        1           Strong-Buy         1.0           77.6
```

## Governance

- **Append-only.** Existing rows never modified.
- **Deterministic.** Same input → identical record content hash.
- **Reproducible.** Every row carries `code_sha` + `written_at_utc`.
- Sealed core untouched.
- Structurally isolated under `research/recommendation_dna/`.

## v0.2 follow-ups

- Live outcome binding — when a position closes, back-annotate the DNA record with realised P&L
- Search UI (currently CLI only)
- Time-series score/confidence evolution charts
- WAL for durability
- Multi-account partitioning (once broker integration exists)
