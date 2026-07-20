# How to Run AEGIS USA

**Version:** AEGIS USA v1.0 · Frozen 2026-07-18
**Currency:** USD ($) throughout. Never `₹`.

## The one command

```powershell
cd C:\Users\GPraveenKumar\Downloads\prism
python usa\scripts\usa_daily.py
```

Runs all 13 orchestrator steps in dependency order (~45 seconds on a
30-ticker Dow universe). Refreshes:

- `usa/reports/universe.json`
- `usa/data/raw/us/*.parquet` (30 tickers × 5 years OHLCV)
- All USA engines' outputs under `usa/reports/*.json`
- `usa/data/archive/YYYY/MM/DD/bundle/` (immutable daily archive)
- `usa/reports/morning_latest.{md,html}` (daily briefing)
- `usa/reports/ops_check.json` (HEALTHY / DEGRADED / CRITICAL)

## View the morning report

```powershell
start usa\reports\morning_latest.html
```

Or open the file directly — it's standalone HTML.

## Automate daily

The `.github/workflows/aegis-usa.yml` workflow runs the pipeline at
20:30 UTC on weekdays (about 30 minutes after US market close) and
commits the fresh reports back to the repo. No manual intervention
required once GitHub Actions is enabled.

## Universe expansion

Edit `usa/configs/universe.yaml`:

- `active_universe: dow30` (default) — 30 Dow constituents
- Add new universe blocks under `universes:` to support S&P 500,
  NASDAQ 100, Russell 1000, etc.
- Universe expansion is operational (Constitution: allowed).
  New engines are architectural (Constitution: forbidden until 90-day
  amendment).

## Where things live

| What | Where |
|---|---|
| Config | `usa/configs/universe.yaml` |
| Scripts | `usa/scripts/{usa_daily,build_universe,refresh_market_data,usa_ops_check}.py` |
| Engines | `usa/research/{recommendations,validation,risk,fusion,price_context,institutional_memory,winner_genome,decision_attribution,benchmark,morning_report}/` |
| Reports | `usa/reports/*.json` + `morning_latest.{md,html}` |
| Archive | `usa/data/archive/YYYY/MM/DD/bundle/` (immutable, git-ignored) |
| Constitution | `usa/AEGIS_USA_CONSTITUTION.md` |

## Verdict interpretation

- **HEALTHY** — 18/18 artifacts present, 9/9 schemas pass. Use the
  recommendations.
- **DEGRADED** — one or two non-critical warnings. Safe to proceed
  but investigate.
- **CRITICAL** — production halt. Read `usa/reports/ops_check.json`,
  fix, re-run.

## Independence from India

USA runs entirely under `usa/`. Zero calls into India code. India's
`scripts/aegis_daily_v2.py` never touches USA files. Both markets
share the repo but nothing else — separate configs, separate reports,
separate archives, separate CI, separate Constitutions.

If you break India, USA keeps running. If you break USA, India keeps
running.

## Day-1 baseline vs mature state

Day 1 (today) shows expected "insufficient data" for engines that
need historical closed trades:

- Winner Genome → mode `insufficient_data`, 0 signatures
- Decision Attribution → subsystem accuracy deferred
- Benchmark → verdict `insufficient_evidence`
- Validation → paper harness stub

All of these populate automatically as the USA archive accumulates
closed paper trades over the next 30-90 trading days.
