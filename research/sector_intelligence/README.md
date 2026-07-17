# DEV018 — Sector Intelligence Engine (v0.1)

Sector context layer of the AEGIS Market Intelligence pipeline. Consumes
DEV017's `global_context.json` + shared raw store, produces
`reports/sector_context.json` + `.parquet`.

Constitutional parent: [`docs/ARCH018_SECTOR_INTELLIGENCE_ENGINE.md`](../../docs/ARCH018_SECTOR_INTELLIGENCE_ENGINE.md).
Data-model parent: [`docs/ARCH017A_MARKET_DATA_CANONICAL_MODEL.md`](../../docs/ARCH017A_MARKET_DATA_CANONICAL_MODEL.md).

## Pipeline

```
DEV017 (Global)
      │
      ▼
   reports/global_context.json     ← macro / risk-on-off / USD / VIX context
   data/market_intelligence/raw/*  ← shared raw store (Nifty50 already here)
      │
      ▼
┌───────────────────────────────────────────────┐
│  DEV018 — Sector Intelligence                  │
│                                                │
│  Ingest    → NSE sector indices via yfinance   │
│  Compute   → 13-dim strength model per sector  │
│  Publish   → sector_context.{json,parquet}     │
└───────────────────────────────────────────────┘
      │
      ▼
   Consumers: DEV018A (Company), DEV019 (Regime),
              DEV023 (Attribution), DEV024/025 (Adaptive H/E)
```

## Directory structure

```
research/sector_intelligence/
├── lib/
│   └── sector_catalog.py     14 NSE sector indices with fallback tickers +
│                             tenant-generic constituent map from india/sectors.py
├── ingest/
│   └── yfinance_ingest.py    fetches sector indices, writes RawObservations
├── compute/
│   └── engine.py             13-dimension composite:
│                             - price trend (20/50/100/200 DMA)
│                             - momentum (20/60/120d)
│                             - RS vs Nifty 50
│                             - realised volatility (inverted)
│                             - max drawdown (inverted)
│                             - volume trend (20d/90d ratio)
│                             - 52-week position
│                             - constituent breadth (% above 200-DMA)
│                             - leadership (outperformance frequency)
│                             - institutional strength (momentum consistency)
│                             - composite score + 5-class classification
├── publish/
│   └── bundle.py             writes reports/sector_context.{json,parquet}
├── tests/
│   └── test_smoke.py         28 tests, no network required
├── run.py                    top-level CLI
└── README.md                 (this file)
```

## Inputs

| Source | Purpose |
|:--|:--|
| **reports/global_context.json** | Upstream global context (risk-on/off, USD, VIX, etc.) — recorded in the sector bundle for consumer awareness |
| **data/market_intelligence/raw/YYYY-MM/*.parquet** | Shared raw store from DEV017; Nifty 50 series is read from here for RS computation |
| **data/raw/india/*.parquet** | AEGIS constituent OHLCV parquets — used for constituent-level sector breadth |
| **india/sectors.py** `SECTORS` dict | Tenant-generic ticker → sector map (~100 tickers) — read directly, not duplicated |

## Outputs

| Path | Format | Contents |
|:--|:-:|:--|
| **reports/sector_context.json** | JSON | Per-sector score, classification, confidence, top drivers/detractors; portfolio-level roll-up (top3, bottom3, class distribution); upstream global context reference; schema/weighting versions |
| **reports/sector_context.parquet** | parquet | Flat one-row-per-sector mirror for consumer downstreams |
| **data/market_intelligence/derived/YYYY-MM/sector_*.parquet** | parquet | Per-run derived metrics, normalized indicators, classifications, composites |

## Execution

```bash
# Prerequisite: DEV017 must have run at least once to populate the shared raw store
python research/global_intelligence/run.py

# Then run DEV018
python research/sector_intelligence/run.py

# Sub-commands (matching DEV017's pattern)
python research/sector_intelligence/run.py --ingest-only
python research/sector_intelligence/run.py --compute-only
python research/sector_intelligence/run.py --publish-only

# Smoke tests (no network)
python research/sector_intelligence/tests/test_smoke.py
```

## Sample output (headline of `sector_context.json`)

```
Banking             score 82   [Bullish]           conf 0.94
   Top drivers: rs_nifty +14.0 · momentum +12.4 · breadth +9.6
IT                  score 76   [Strong-Bullish]    conf 0.91
Auto                score 45   [Neutral]           conf 0.88
```

Full detail: `reports/sector_context.json`.

## Classifications (5-class + Unknown)

| Class | Score threshold | Confidence gate |
|:--|:-:|:-:|
| Strong-Bullish | ≥ 75 | ≥ 0.5 |
| Bullish | 60-74.9 | ≥ 0.5 |
| Neutral | 45-59.9 | ≥ 0.5 |
| Weak | 30-44.9 | ≥ 0.5 |
| Bearish | < 30 | ≥ 0.5 |
| Unknown | any | < 0.5 |

## Weight table (v1 draft)

Documented at `research/sector_intelligence/compute/engine.py::COMPOSITE_WEIGHTS_V1`.
Ten dimensions, weights sum to 1.00. Missing dimensions cause the composite to renormalise
against present dimensions and the confidence to reduce proportionally (ARCH017A §9).

## Reuse discipline

Everything in DEV018 imports from `research/global_intelligence/lib/`:

- `schema.py` — RawObservation / DerivedMetric / NormalizedIndicator / Classification / CompositeScore dataclasses (no re-declared entity types)
- `confidence.py` — `c_source` / `c_freshness` / `combine` / `tier_from_downstream`

No entity redefinition. No confidence recomputation. This satisfies the operator's
directive: *"Reuse ARCH017A canonical entities. Reuse confidence framework. Reuse UUID generation. No duplicated code."*

## Governance

- Emits **NO** BUY/SELL/EXIT signals (per ARCH018 §17.2). Advisory context only.
- Sealed core (MON001) untouched.
- Production code (`india/`, `nexaquant/`) unmodified.
- Runs entirely under `research/` — cannot be imported by production per ARCH001A Article VII clause 7.1.

## What's deferred to v0.2

- Sector-level valuation metrics (aggregate forward-P/E)
- Sector-level earnings tone (constituent EPS surprise aggregation)
- LLM-tagged news signal (blocked on ARCH026)
- Sector-crowding metric (needs positioning data — FII/DII quarterly disclosures)
- Sector-lifecycle mapping (Stovall / Fidelity business-cycle prior)
- LAB015-A discrimination study (Spearman ρ between score and forward return)
- LAB015-B sector-conditional stock scoring validation
