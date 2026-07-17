# DEV019 — Industry Intelligence Engine (v0.1)

Industry-tier of the AEGIS Market Intelligence hierarchy. Fills the gap between
DEV018 (Sector) and the future DEV020 (Company). Consumes DEV017 + DEV018 outputs
plus the AEGIS constituent parquets; publishes `industry_context.{json,parquet}`.

Constitutional parent (planned): ARCH018A (Company Intelligence Engine) and
ARCH020 (Knowledge Graph) both consume DEV019 outputs.
Data-model parent: [`docs/ARCH017A_MARKET_DATA_CANONICAL_MODEL.md`](../../docs/ARCH017A_MARKET_DATA_CANONICAL_MODEL.md).

## Pipeline position

```
DEV017 (Global)  →  reports/global_context.json
        ↓
DEV018 (Sector)  →  reports/sector_context.json + data/market_intelligence/raw/*
        ↓
┌──────────────────────────────────────────────────────────┐
│  DEV019  Industry Intelligence Engine                     │
│                                                            │
│  Consume:  constituent parquets  (data/raw/india/*)        │
│            sector series          (from DEV018 raw store)  │
│            Nifty 50 series        (from DEV017 raw store)  │
│                                                            │
│  Compute:  10-dim strength composite per industry          │
│            RS vs sector, RS vs Nifty                       │
│            Leadership rank + intra-sector rank             │
│            6-way rotation classifier                       │
│                                                            │
│  Publish:  reports/industry_context.{json,parquet}         │
└──────────────────────────────────────────────────────────┘
        ↓
DEV020 (Company) — planned
```

## Directory structure

```
research/industry_intelligence/
├── lib/
│   └── industry_catalog.py    ~40 industries mapped to parent sectors, with
│                              constituent tickers drawn from the AEGIS universe
├── ingest/
│   └── (empty — DEV019 has no fresh ingest; consumes existing parquets)
├── compute/
│   └── engine.py              Equal-weighted industry price aggregation
│                              10-dimension composite (trend/mom/RS-nifty/
│                                RS-sector/breadth/vol/DD/52w/leadership/inst)
│                              5-class classification + 6-way rotation label
│                              Leadership rank (universe-wide) + intra-sector rank
├── publish/
│   └── bundle.py              writes reports/industry_context.{json,parquet}
├── tests/
│   └── test_smoke.py          ~20 tests including catalog validation, ticker
│                              uniqueness, parent-sector consistency, rotation
├── run.py                     top-level CLI
└── README.md                  (this file)
```

## Inputs

| Source | Purpose |
|:--|:--|
| **reports/global_context.json** | Upstream global posture (Risk-On/Off) — recorded as reference |
| **reports/sector_context.json** | Sector scores + labels — recorded; each industry lists its parent |
| **data/market_intelligence/raw/YYYY-MM/*.parquet** | Sector index series (DEV018) + Nifty 50 (DEV017); used for RS calculations |
| **data/raw/india/*.parquet** | AEGIS constituent daily bars — aggregated into industry series |

## Outputs

| Path | Format | Contents |
|:--|:-:|:--|
| **reports/industry_context.json** | JSON | Per-industry score, classification, rotation label, confidence, leadership rank, intra-sector rank, top drivers/detractors, parent-sector attribution, upstream references |
| **reports/industry_context.parquet** | parquet | One row per industry; flat schema for consumer downstreams |
| **data/market_intelligence/derived/YYYY-MM/industry_*.parquet** | parquet | Per-run derived metrics, normalized indicators, classifications, composites |

## Execution

```bash
# Prerequisites — DEV017 and DEV018 must have run:
python research/global_intelligence/run.py
python research/sector_intelligence/run.py

# Then DEV019:
python research/industry_intelligence/run.py
python research/industry_intelligence/run.py --publish-only

# Smoke tests (no network):
python research/industry_intelligence/tests/test_smoke.py
```

## Industry-level composite (10 dimensions)

| # | Sub-score | Method | Weight |
|:-:|:--|:--|:-:|
| 1 | `norm.industry.momentum` | Blended 20/60/120d ROC percentile | 0.18 |
| 2 | `norm.industry.rs_nifty` | Industry vs Nifty 50 return spread percentile | 0.15 |
| 3 | `norm.industry.rs_sector` | Industry vs parent-sector return spread | 0.10 |
| 4 | `norm.industry.breadth` | % of constituents above 200-DMA | 0.12 |
| 5 | `norm.industry.trend` | Price above N of {20/50/100/200} DMAs | 0.10 |
| 6 | `norm.industry.volatility` | 20-day realised vol percentile (inverted) | 0.08 |
| 7 | `norm.industry.drawdown` | Max drawdown 252d, mapped to [0, 100] | 0.08 |
| 8 | `norm.industry.52w_position` | Position within 52-week range | 0.07 |
| 9 | `norm.industry.leadership` | % of days outperforming Nifty (90d window) | 0.07 |
| 10 | `norm.industry.institutional` | % positive-return days (60d) proxy | 0.05 |
|  | Sum | | **1.00** |

## 5-class classification

Score ≥ 75 · Strong-Bullish
60-74 · Bullish
45-59 · Neutral
30-44 · Weak
< 30 · Bearish
(confidence < 0.5 → `Unknown`)

## 6-way rotation classifier

Based on composite score level + RS trend direction vs Nifty:

| Label | Trigger |
|:--|:--|
| **Strong-Leader** | Score ≥ 65 AND outperforming AND RS improving |
| **Emerging-Leader** | 55 ≤ score < 65 AND outperforming AND RS improving |
| **Falling-Leader** | Score ≥ 55 AND outperforming AND RS deteriorating |
| **Improving** | Score < 55 AND underperforming AND RS improving |
| **Weakening** | Score ≥ 45 AND underperforming AND RS deteriorating |
| **Lagging** | Otherwise |

## Relative rankings

Each industry receives:

- `leadership_rank` — position across ALL industries (universe-wide)
- `intra_sector_rank` — position within its parent sector's industries
- `intra_sector_total` — number of computable industries in the same sector

Downstream consumers (DEV020, ARCH024, RISK001-C) can use these to pick the
best industry within an already-strong sector, or to gate admission by
requiring `intra_sector_rank ≤ 2` etc.

## Reuse discipline

Every canonical entity — `RawObservation`, `DerivedMetric`, `NormalizedIndicator`,
`Classification`, `CompositeScore` — is imported from
`research/global_intelligence/lib/schema.py`. Same for `confidence.py`.
No entity or math duplicated.

## Governance

- Emits **NO** BUY/SELL/EXIT signals. Advisory context only.
- Sealed core (MON001) untouched · `cumulative_strategy_search = 38` unchanged.
- Structurally isolated: `research/industry_intelligence/` cannot be imported
  by `india/` or `nexaquant/` production code (per ARCH001A Article VII clause 7.1).
- Every ticker mapping is in this repo's own `industry_catalog.py`, not
  hardcoded in production.

## v0.2 follow-ups

- Fetch supplementary industry-level ETFs where they exist (some NSE thematic ETFs cover industries)
- Company-level valuation aggregation into industry P/E percentiles
- LLM-tagged industry news signal (blocked on ARCH026)
- Industry-crowding metric (needs positioning data)
- LAB016-A: industry-conditional stock scoring validation study
