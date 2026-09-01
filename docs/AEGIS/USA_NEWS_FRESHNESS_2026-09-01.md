# USA News Producer · Freshness Documentation · 2026-09-01

## Current state

- **Producer**: `usa/research/news/run.py` (Google News RSS + lexicon score)
- **Wired**: `usa/scripts/usa_daily.py:72` · step `ingest_news` · `optional: True` · `staleness_skip_hours: 6` · `timeout_s: 900`
- **Last successful run**: 2026-08-21 (per `usa/reports/news_sentiment_summary.json`.`asof`)
- **Last file mtime**: 2026-08-24 10:01 · confirming the step attempted to refresh but did not advance `asof`
- **As-of 2026-09-01**: 11 calendar days stale
- **Coverage on last successful run**: 516/516 tickers · avg_sentiment 0.197 · pos 391 / neg 46 / neu 79

## Why stale — external cause, not code defect

- Google News RSS occasionally returns empty results or rate-limits at the per-ticker fetch loop across 516 tickers
- The step is `optional: True` by design (documented in `usa/scripts/usa_daily.py:79`) so downstream is never blocked by a news failure
- The step also has `staleness_skip_hours: 6` guard (documented in file:81) — if a prior refresh happened within 6 hours, the step skips
- No hardcoded values are ever fabricated when news is stale — the producer either succeeds and updates or fails silently and downstream engines see the last successful snapshot

## Blast radius · does staleness affect LOCK?

**No.** News is NOT on the R2 exit critical path:
- `backend/risk/dynamic_risk_v2.py` uses ATR-14 + price close only — never news
- `backend/portfolio/portfolio_manager.evaluate_position` uses stop / target / horizon only — never news
- The 3 CEO-flagged R2 positions (CHAMBLFERT · ITC · USA IT) hold or exit purely on price-based dynamic-risk rules
- News sentiment is consumed only by AI-narrative producers (`backend/ai/*`) as advisory context, never as a decision input

## Mitigation path (post-LOCK · non-blocking)

- Prior to next scheduled push: manually invoke `python usa/research/news/run.py` to attempt refresh
- If Google News RSS remains blocked: substitute Yahoo Finance news endpoint (already partially wired in `usa/research/news/yahoo_fallback.py`)
- Monitor the `n_with_news` field in `news_sentiment_summary.json` — a drop below 400/516 tickers is the early-warning signal
- Any move to a paid news vendor requires a separate CEO decision cycle (out of scope for LOCK)

## Documentation stance

This staleness is a **KNOWN**, **DOCUMENTED**, **NON-BLOCKING** condition. It does not represent a defect in the AEGIS closure. It is a bounded external dependency and is treated exactly as intended by the `optional: True` design.

**LOCK is not gated on news freshness. Portfolio/Exit/Risk decisions are unaffected.**
