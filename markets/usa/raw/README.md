# USA Data Lake

Every dataset lands here **raw first**, is then **normalized** into the **feature store**, and only then
feeds research. Raw is kept forever so features can be regenerated without re-downloading.

```
markets/usa/
  raw/                  ← immutable raw pulls (one folder per dataset)
    fundamentals/         SEC EDGAR CompanyFacts JSON (Phase 5)
    earnings/             expected/actual EPS, surprise, guidance (PIT)
    insiders/             SEC Form 4 transactions
    13f/                  institutional holdings (quarterly)
    etf/                  ETF holdings + flows
    macro/                FRED series (rates/CPI/yield curve), VIX, DXY, oil, gold
    news/                 archived headlines (ticker, source, ts, url) — score later
  processed/            ← normalized, point-in-time-aligned tables (per dataset)
  features/             ← THE feature store (feature_store.parquet): one row per (symbol,date)
  research/             ← experiment outputs, notebooks, backtests
```

## Pipeline (no shortcuts)
```
Raw → Normalize (PIT-align) → Feature Store → Backtest → Walk-forward → Paper → Gate → Production
```
A dataset only influences anything after it clears the data-layer gate (IC · lift · walk-forward · DSR)
and beats the frozen baseline. Sectors and the feature store are the structure new datasets fit into.

## Status
- ✅ Feature store framework (`core/feature_store.py`) + technical features seeded
- ⬜ SEC EDGAR fundamentals (Phase 5) → `raw/fundamentals/` → normalize → feature store
- ⬜ earnings · insider · 13F · ETF · macro · news (subsequent phases, same pipeline)
