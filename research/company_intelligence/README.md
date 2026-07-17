# DEV020 — Company Intelligence Engine (v0.1)

Final tier of the AEGIS Market Intelligence hierarchy. Every AEGIS-universe
ticker receives an 11-dimension composite score with full top-down context
inheritance from DEV017 (Global) → DEV018 (Sector) → DEV019 (Industry).

## Pipeline

```
DEV017 Global      →  reports/global_context.json
        ↓
DEV018 Sector      →  reports/sector_context.json + data/market_intelligence/raw/*
        ↓
DEV019 Industry    →  reports/industry_context.json
        ↓
┌───────────────────────────────────────────────────────┐
│  DEV020  Company Intelligence Engine                    │
│                                                          │
│  Consume:                                                │
│    - constituent parquets (data/raw/india/*)             │
│    - sector index series  (DEV018 raw store)             │
│    - Nifty 50 series      (DEV017 raw store)             │
│    - industry aggregate series (rebuilt from DEV019)     │
│    - global/sector/industry bundles (JSON)               │
│                                                          │
│  Compute per ticker:                                     │
│    11-dim composite + full inheritance chain             │
│    5 rank tables (overall, sector, industry, RS, risk)   │
│    Positive drivers, negative drivers, strengths, risks  │
│    Validation: history / liquidity / price sanity        │
│                                                          │
│  Publish:                                                │
│    reports/company_context.{json,parquet}                │
└───────────────────────────────────────────────────────┘
        ↓
DEV021 (Hierarchical Recommendation Engine) — next
```

## Directory structure

```
research/company_intelligence/
├── lib/
│   └── company_catalog.py     Universe reverse-derived from DEV019 industries;
│                              every ticker linked to industry + parent sector;
│                              disk availability check
├── ingest/                     (empty — DEV020 consumes existing parquets)
├── compute/
│   └── engine.py               Per-ticker 11-dimension composite:
│                                 - trend (MA structure)
│                                 - momentum (blended 20/60/120d percentile)
│                                 - RS vs industry
│                                 - RS vs parent sector
│                                 - RS vs Nifty 50
│                                 - volatility (inverted)
│                                 - max drawdown (inverted)
│                                 - 52-week position
│                                 - liquidity (ADV in INR crore percentile)
│                                 - volume trend (20d/90d ratio)
│                                 - breakout status
│                                 - technical strength (composite proxy)
│                               5-class classification + risk score
│                               5 rank tables computed after aggregation
├── publish/
│   └── bundle.py               Writes reports/company_context.{json,parquet}
│                               with full hierarchy + rankings + drivers/risks
├── tests/
│   └── test_smoke.py           24 tests, no network required
├── run.py                       CLI matching DEV017/018/019 patterns
└── README.md                    (this file)
```

## Inputs

| Source | Purpose |
|:--|:--|
| **data/raw/india/*.parquet** | 232 AEGIS constituent daily OHLCV parquets — primary compute input |
| **reports/global_context.json** | Global context inherited per company |
| **reports/sector_context.json** | Sector score/class inherited per company |
| **reports/industry_context.json** | Industry score/class inherited per company |
| **data/market_intelligence/raw/YYYY-MM/*.parquet** | Sector indices + Nifty 50 series (for RS calculations) |
| **DEV019 industry aggregation** | Rebuilt industry price series (equal-weighted, rebased) — for RS vs industry |

## Outputs

| Path | Format | Content |
|:--|:-:|:--|
| **reports/company_context.json** | JSON | Per-company score + classification + confidence + full hierarchy inheritance + 5 rankings + positive/negative drivers + risks/strengths |
| **reports/company_context.parquet** | parquet | Flat one-row-per-company mirror with 20 columns |
| **data/market_intelligence/derived/YYYY-MM/company_*.parquet** | parquet | Per-run derived / normalized / classifications / composites |

## Execution

```bash
# Prerequisites — DEV017 + DEV018 + DEV019 must have run:
python research/global_intelligence/run.py
python research/sector_intelligence/run.py
python research/industry_intelligence/run.py

# Then DEV020:
python research/company_intelligence/run.py                # full universe
python research/company_intelligence/run.py --max 50       # dev/testing mode
python research/company_intelligence/run.py --publish-only

# Smoke tests (no network):
python research/company_intelligence/tests/test_smoke.py
```

## Composite model (11 dimensions)

| # | Sub-score | Direction | Weight |
|:-:|:--|:--|:-:|
| 1 | `norm.company.momentum` | Higher = trending up | 0.15 |
| 2 | `norm.company.rs_industry` | Higher = beating industry | 0.12 |
| 3 | `norm.company.rs_sector` | Higher = beating parent sector | 0.08 |
| 4 | `norm.company.rs_nifty` | Higher = beating Nifty 50 | 0.08 |
| 5 | `norm.company.trend` | Higher = above more MAs | 0.10 |
| 6 | `norm.company.volatility` | Higher = calmer | 0.08 |
| 7 | `norm.company.drawdown` | Higher = shallower DD | 0.08 |
| 8 | `norm.company.52w_position` | Higher = closer to 52w high | 0.08 |
| 9 | `norm.company.liquidity` | Higher = deeper ADV | 0.06 |
| 10 | `norm.company.volume_trend` | Higher = 20d vs 90d volume up | 0.07 |
| 11 | `norm.company.breakout` | Higher = near breakout | 0.05 |
|  | `norm.company.technical` (derived blend) | Higher = strong technical | 0.05 |
|  | **Sum** | | **1.00** |

## Classifications

Score-band gating with confidence guard (< 0.5 → `Unknown`):

| Class | Score range |
|:--|:-:|
| Strong-Bullish | ≥ 75 |
| Bullish | 60 – 74.9 |
| Neutral | 45 – 59.9 |
| Weak | 30 – 44.9 |
| Bearish | < 30 |
| Unknown | conf < 0.5 |

## Rankings (5 tables computed per run)

| Ranking | Description |
|:--|:--|
| `overall_rank` | Position among ALL scored companies (1 = highest score) |
| `sector_rank` | Position within parent sector's companies |
| `industry_rank` | Position within parent industry's companies |
| `rs_rank` | Position by average of `rs_industry + rs_sector + rs_nifty` |
| `risk_rank` | Position by risk score (inverted vol + inverted DD blend); 1 = safest |

## Hierarchy inheritance

Every scored company carries these inherited fields in `hierarchy`:

```
global_score:           47.12
global_posture:         Neutral
sector_key:             sector.india.banking
sector_display:         Banking
sector_score:           52.66
sector_classification:  Neutral
industry_key:           industry.india.private_banks
industry_display:       Private Banks
industry_score:         71.35
industry_classification: Bullish
```

The recommendation engine (DEV021) will consume this inheritance to compute a
context-adjusted final score per stock (e.g. penalise Weak-industry stocks even
when their company_score is elevated).

## Validation gates

- **`no_data`** — parquet missing or empty
- **`missing_close_column`** — parquet malformed
- **`insufficient_history(N<100)`** — needs 100+ bars for reliable stats
- **`invalid_latest_close`** — non-positive close
- **`low_liquidity(adv_cr<1.0)`** — ADV below ₹1 crore
- **`compute_failed` / `no_valid_dimensions`** — safety-net catchalls

Rejected tickers are recorded in `warnings` with counts by reason.

## Reuse discipline (per operator's "No duplicate code")

Every canonical entity — `RawObservation`, `DerivedMetric`, `NormalizedIndicator`,
`Classification`, `CompositeScore`, `as_dict` — is imported from
`research/global_intelligence/lib/schema.py`. Same for `confidence.py`. The
industry price aggregation logic is imported from `industry_intelligence`.

## Governance

- Emits **NO** BUY/SELL/EXIT signals. Advisory context only.
- Sealed core (MON001) untouched · `cumulative_strategy_search = 38` unchanged.
- Structurally isolated: `research/company_intelligence/` cannot be imported by
  production code per ARCH001A Article VII clause 7.1.
- Company catalog + validation thresholds all in this repo; no hardcoded
  ticker lists in production.

## v0.2 follow-ups

- Fundamentals dimensions (P/E, P/B, ROE, debt/equity — requires screener/EOD source)
- News sentiment (blocked on ARCH026)
- Analyst-consensus proxy (target price vs current)
- Confidence calibration (blocked on ARCH029)
- LAB016-A: context-adjusted stock scoring validation study
- Add remaining unmapped tickers to DEV019 industry catalog to expand universe
