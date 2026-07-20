# AEGIS USA Constitution

**Version:** AEGIS USA v1.0 · Production Baseline
**Frozen:** 2026-07-18 (same day as India v2.0)
**Market:** United States (NYSE + NASDAQ)
**Currency:** USD ($) — never mixed with India (₹)
**Fingerprint:** *(minted once first full daily run completes)*

Independent from the [India AEGIS Constitution](../AEGIS_CONSTITUTION.md).
Modifying `usa/` never touches India. Modifying India never touches USA.

## The Freeze

USA's Phase-1 architecture is FROZEN. The 13-step daily orchestrator,
the technical scorer, the fusion layer, the risk engine, the
institutional memory archive, the benchmark, the morning report —
all of it stays as it is.

The next milestone is 30 live trading days of archived USA evidence.
Then 90 live days. Then, if evidence supports it, targeted parameter
changes.

## The 13 Locked Steps

`usa/scripts/usa_daily.py` runs exactly these in this order:

1. `build_universe`         — YAML → `reports/universe.json`
2. `refresh_market_data`    — yfinance → `data/raw/us/*.parquet`
3. `recommendations`        — technicals → composite score → action
4. `validation`             — paper harness + drift (grows over time)
5. `risk`                   — position sizing + sector caps + verdict
6. `fusion`                 — 6-dim aggregate + conflicts + why chains
7. `price_context`          — CMP + 52W bounds per ticker
8. `institutional_memory`   — archive + lifecycle + missed-opps + history
9. `winner_genome`          — signature mining (activates after 30 trades)
10. `decision_attribution`  — per-rec subsystem contributions
11. `benchmark`             — Alpha vs S&P 500
12. `morning_report`        — daily HTML + Markdown briefing
13. `ops_check`             — HEALTHY / DEGRADED / CRITICAL verdict

## Allowed (no evidence gate)

- Bug fixes where existing code contradicts its own documented behaviour
- UI polish that doesn't add new metrics or interpretive layers
- Documentation (this file, docs/, docstrings)
- Adding tickers to `configs/universe.yaml` (universe expansion is
  operational config, not architectural)
- Adjusting `SUBSYSTEM_WEIGHTS` in decision attribution once ≥ 90 days
  of live archive evidence supports the change

## Not Allowed (require ≥ 90 archive days + operator sign-off)

- New engines beyond the 13 above
- New scoring systems / new dimensions in fusion
- New pipeline steps
- New dashboards / new SPA routes
- New AI layers (ML models, LLMs, RL agents)
- Merging with India — USA stays a distinct market deployment forever
- Cross-market signal borrowing without explicit amendment

## The Constitutional Test (same 5 questions as India)

Before writing any code under `usa/`, answer:

1. What problem does it solve?
2. Can it be solved by aggregating existing data?
3. Will it measurably improve alpha vs S&P 500 or reliability?
4. What evidence justifies building it?
5. Will it break the (future) USA fingerprint?

## Currency invariant

USD ($) throughout. Every renderer, dashboard tile, Telegram formatter,
report table, and log line under `usa/` uses `$`. Never `₹`. Never
mixed. If a numeric value is shown without a currency, it MUST be a
percentage or a count.

## Operational Cadence

- **Daily:** `python usa\scripts\usa_daily.py` runs the 13 steps, archive
  grows by one day, morning report generated
- **Weekly:** operator reviews Decision Attribution trends, benchmark
  performance, missed opportunities. No changes to code.
- **Monthly:** publish `usa/docs/monthly/YYYY-MM.md` Evidence Review
- **Day 30 (≈ 2026-08-17):** Winner Genome unlocks (signature mining
  activates with ≥ 30 closed paper trades)
- **Day 90 (≈ 2026-10-17):** First formal Evidence Review; parameter
  adjustments considered
- **Day 180+:** Change USA through data, not code

## Amendment

Same protocol as India: ISO date, specific rule being amended, ≥ 90
days archive evidence, operator sign-off. First amendment cannot occur
before 2026-10-18.

---

## Amendment History

_None. USA v1.0 Constitution effective 2026-07-18._
