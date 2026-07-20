# AEGIS Data Lineage · Where data originates and how it flows
**Stage 0.5 deliverable · Runtime-verified data pipelines**

---

## A. India raw data ingestion

### A1 · Daily OHLCV (LIVE)

```
yfinance API
    │
    ▼
india/refresh_data.py  ── invoked by aegis-daily.yml
    │
    ▼
data/raw/india/{TICKER}_D1.parquet  (~208 tickers, 5y history)
    │
    ▼
data/raw/india/NSEI_D1.parquet + NSEBANK + INDIAVIX (indices)
```

**Schedule:** weekdays via `aegis-daily.yml` cron.

### A2 · FII/DII institutional flows (MANUAL ONLY)

```
NSE web API (https://www.nseindia.com/api/fiidiiTradeReact)
    │
    ▼
india/fii_dii.py  ── invoked ONLY by india/daily_run.py
    │
    ▼
data/raw/india/fii_dii.parquet  (appended forward-only, no history)
```

**Schedule:** none. Only runs when operator manually runs `run_daily.bat`.

**Evidence:** grep for `fii_dii.py` in `.yml/.yaml/.service/.timer/.ps1`: only `india/daily_run.py:39`.

### A3 · News sentiment (MANUAL ONLY)

```
Google News RSS (per stock)
    │
    ▼
FinBERT classifier (positive/negative/neutral)
    │
    ▼
india/news_sentiment.py  ── invoked ONLY by india/daily_run.py
    │
    ▼
data/raw/india/news_sentiment.parquet  (forward accumulator)
```

**Schedule:** none. Manual only.

**Consumed by:** `india/run_arjuna.py:26,49-54` reads the parquet IF it exists — but never triggers ingestion itself. So if operator doesn't run `daily_run.py`, the parquet grows stale but downstream reads continue using the last snapshot.

### A4 · Fundamentals + earnings (MANUAL ONLY, NOT WIRED)

```
yfinance Ticker(...).info  (ROE, D/E, PE, PB, profit margin, earnings growth,
                             revenue growth, market cap, beta, dividend yield)
    │
    ▼
india/fundamentals_nse.py  ── zero callers, only self-CLI usage
    │
    ▼
data/raw/india/fundamentals.parquet
```

**Schedule:** none. **Not even called by `india/daily_run.py`.**

**Consumed by:** unclear — the parquet exists on disk but no grep hits show anyone reading it in the live pipeline. This is the loosest wiring of any data source.

### A5 · Intraday bars (M5 / M15) — dev only

```
data/raw/india/{TICKER}_M5.parquet  (git-ignored, .gitignore:40)
data/raw/india/{TICKER}_M15.parquet (git-ignored, .gitignore:41)
```

Not used in production. Presumably operator-collected for research.

### A6 · Global data caches

```
data/raw/india/global/  (subdir)
```

Not verified in detail. Likely feeds the frozen intelligence hierarchy.

## B. India intelligence tier (FROZEN)

```
yfinance macro feeds ── research/global_intelligence/ingest/yfinance_ingest.py
    │
    ▼
data/market_intelligence/raw/*  (cached indicators)
    │
    ▼
research/global_intelligence/compute/engine.py  ── ran 2026-07-17 only
    │
    ▼
reports/global_context.{json,parquet}  🟡 FROZEN
    │
    ▼
research/sector_intelligence/compute/engine.py  ── ran 2026-07-17 only
    │  (inherits global as regime context)
    ▼
reports/sector_context.{json,parquet}  🟡 FROZEN
    │
    ▼
research/industry_intelligence/compute/engine.py  ── ran 2026-07-17 only
    │  (inherits sector)
    ▼
reports/industry_context.{json,parquet}  🟡 FROZEN
    │
    ▼
research/company_intelligence/compute/engine.py  ── ran 2026-07-17 only
    │  (11-dim composite per ticker with full inheritance chain)
    ▼
reports/company_context.{json,parquet}  🟡 FROZEN
```

**Every downstream consumer treats these as current signals.** See `AEGIS_REPORT_LINEAGE.md` for the 15+ consumers of `global_context.json` alone.

## C. India recommendation flow (LIVE from technical data only)

```
data/raw/india/*_D1.parquet
    │
    ▼
india/technical_factors.py + india/feature_engine.py  (imported libs)
    │
    ▼
india/recommendation_generator.py  ── invoked by aegis-daily.yml:91
    │
    ├── uses india/confidence_engine.current_regime()  → "global" regime
    ├── uses india/arjuna_strategy.py + arjuna_v2.py (HRP + regime + Global-Risk)
    │
    ▼
data/aegis_today.csv + AEGIS_LATEST.xlsx
    │
    ▼
scripts/aegis_daily_v2.py --continue  ── v2 15-step chain
    │
    ▼
reports/recommendations.json  (LIVE)
```

**Note:** `research/adaptive_rec_v2/run.py` is the FIRST step of the v2 chain, and it produces `reports/recommendations.json` from `learning.parquet` (frozen) — this is technically distinct from `india/recommendation_generator.py`'s output (`AEGIS_LATEST.xlsx`). Both exist. The v2 output is what the SPA + Telegram consume. **Two parallel recommendation engines that never explicitly reconcile.**

## D. USA raw data ingestion

### D1 · Daily OHLCV (LIVE)

```
yfinance API
    │
    ▼
usa/scripts/refresh_market_data.py  ── step 2 of usa_daily.py
    │
    ▼
usa/data/raw/us/{TICKER}_D1.parquet  (30 Dow tickers + 4 indices, 5y history)
```

**Schedule:** weekdays 20:30 UTC.

### D2 · USA fundamentals (NOT WIRED)

```
yfinance Ticker(...).info
    │
    ▼
usa/research/fundamentals/run.py  ── NEVER INVOKED (not in usa_daily.py STEPS)
    │
    ▼
usa/reports/fundamentals.json  (only exists if operator manually runs it)
```

### D3 · USA provisioned dirs (all EMPTY)

```
markets/usa/raw/
├── 13f/           (SEC 13F filings — empty)
├── earnings/      (earnings calendar — empty)
├── etf/           (ETF flows — empty)
├── fundamentals/  (empty)
├── macro/         (empty)
└── news/          (empty)
```

These directories signal design intent — a full USA multi-source pipeline was scoped — but no ingestor was ever built for them.

## E. Archive (LIVE, immutable)

```
Daily orchestrator ── research/institutional_memory/lib/archive.py
    │
    ▼
data/archive/YYYY/MM/DD/bundle/  (14 canonical files copied)
data/archive/YYYY/MM/DD/manifest.json  (sha256 per file + code_sha)
```

Same pattern in `usa/data/archive/`. Both git-ignored.

## F. What DATA is ingested daily today, unambiguously

| Data | India | USA |
|---|---|---|
| OHLCV daily bars | ✅ (208 tickers) | ✅ (30 Dow) |
| VIX / VIX-equivalent | ✅ (`INDIAVIX_D1.parquet`) | ✅ (`^VIX` in indices) |
| Broad-market index | ✅ (`NSEI_D1.parquet`) | ✅ (`^GSPC`, `^NDX`, `^DJI`) |
| Fundamentals | ❌ (module exists, unscheduled) | ❌ (module exists, unwired) |
| News / sentiment | ❌ (manual only) | ❌ (not built) |
| Institutional flows | ❌ (manual only) | ❌ (not built) |
| Earnings calendar | ❌ (module exists in fundamentals_nse, unscheduled) | ❌ (dir empty) |
| Corporate actions | ❌ | ❌ |
| Alternative data | ❌ | ❌ |
| Macro (rates, currency, etc.) | ❌ (2026-07-17 snapshot in global_context, never refreshed) | ❌ |

**Every recommendation generated today (both markets) is based on technicals + `learning.parquet` (frozen) + `global_context.json` (frozen) only.** No new fundamental / news / flow / macro data is entering the pipeline unless a human manually runs `run_daily.bat`.
