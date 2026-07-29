# AEGIS USA · Parallel Deployment

**Status:** v3.0 LOCKED (2026-07-29) · Constitutional Freeze active · S&P 500 + MidCap 400

This deployment shares the AEGIS architecture with India — same engines,
same data contracts, same downstream consumers. Only per-market inputs
differ: universe, benchmark, currency, trading calendar, sector mapping.

## Currency

**All prices are in USD ($).** Every renderer, formatter, dashboard
tile, Telegram message, and report under `usa/` uses `$` — never `₹`.

## Universe (v3.0 · dynamic)

**Active:** S&P 500 + S&P MidCap 400 = **918 unique tickers** (US large +
mid cap). Loaded dynamically from `usa/configs/universes/*.json` via
`usa/configs/universe.yaml → active_universe: sp500_plus_midcap400`.

Refresh the constituent lists (Wikipedia canonical) with:

```
python usa/scripts/refresh_universe.py
```

Switching universes (Russell 1000, UK, Europe, ...) requires only a new
JSON + one yaml entry — zero code changes (Article 3 of the v3.0
Constitutional Directive · dynamic universe contract).

Historical/rollback universes still available in `universe.yaml`:
`dow30` (30 tickers · original v2.0 default) · `nasdaq100` · `sp500_top50`.

## Directory layout

Mirrors the India tree so future maintenance is symmetric:

```
usa/
    configs/          — universe.yaml + engine config
    data/raw/us/      — per-ticker OHLCV parquet files
    reports/          — daily engine outputs
    scripts/          — orchestrator + market data + telegram
    research/         — engines (recommendation / fusion / etc.)
    monitoring/       — health + ops checks
    dashboard/        — SPA + serve
    telegram/         — USA-specific message renderer
    docs/             — architecture, runbook, deployment
```

## Independence guarantees

- USA pipeline invokes NO India code
- India `scripts/aegis_daily_v2.py` never touches USA files
- India CI (`.github/workflows/aegis-ci.yml`) tests India-only
- USA will get its own CI workflow (`.github/workflows/aegis-usa.yml`)
  in Phase 6
- USA fingerprint / seal (once minted) is distinct from India's
  MON001 `e4c070673568c52d…`

## Roadmap

| Phase | Scope |
|---|---|
| **1** *(this commit)* | Scaffold + universe + market data + orchestrator skeleton |
| 2 | Recommendation engine + validation + risk (USA-tuned) |
| 3 | Fusion + DNA + Knowledge Graph |
| 4 | Institutional Memory + Winner Genome + Decision Attribution + Benchmark (vs S&P 500) |
| 5 | Morning Report + Dashboard + Telegram |
| 6 | CI + Monitoring + Docs |
| 7 | Regression + smoke tests + commissioning |

## Quick start (Phase 1 only)

```powershell
# One-time (or when universe changes): build ticker universe from config
python usa\scripts\build_universe.py

# Refresh USA market data (yfinance → data/raw/us/*.parquet)
python usa\scripts\refresh_market_data.py

# Run the Phase-1 orchestrator (only refreshes data + updates universe today)
python usa\scripts\usa_daily.py
```

Phase 1 does NOT produce recommendations yet. Recommendations arrive
in Phase 2.
