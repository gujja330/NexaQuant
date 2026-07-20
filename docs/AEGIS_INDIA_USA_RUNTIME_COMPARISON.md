# AEGIS India ↔ USA · Runtime Comparison
**Stage 0.5 deliverable · Cell-by-cell, runtime-verified (not file-presence)**

Corrects the earlier "USA has full parity" claim. Real answer per this audit:

- **USA has full parity** on orchestration shape + core always-on engines
- **USA has ZERO** for: MON001 forward validator, 4-tier intelligence hierarchy, champion/challenger, confidence calibration, portfolio construction/monitor, news ingestion, institutional flow ingestion, earnings, macro, alternative data
- **USA's own `usa/research/fundamentals/run.py` exists but is NOT wired into its own orchestrator** (`usa/scripts/usa_daily.py` STEPS list has zero matches for "fundamentals")

---

## Cell-by-cell matrix

Legend:
- **BOTH_LIVE** — both markets run this daily
- **BOTH_STATIC** — both markets have this but neither runs it daily (frozen)
- **INDIA_LIVE / INDIA_MANUAL / INDIA_FROZEN** — status specific to India
- **USA_LIVE / USA_MISSING / USA_STUB** — status specific to USA
- **NEITHER** — not implemented in either market

### 1. Orchestration + Ops

| Capability | India | USA | Verdict |
|---|---|---|---|
| Daily orchestrator | `scripts/aegis_daily_v2.py` (15 steps) | `usa/scripts/usa_daily.py` (13 steps) | **BOTH_LIVE** |
| Pre-v2 daily orchestrator | `aegis-daily.yml` steps 1-6 (India generator + DB + scorecard) | — | **INDIA_LIVE** |
| Sealed forward validator | `india/monitoring/MON001_Forward_Validation` | Not built | **INDIA_LIVE** |
| CI on push | `aegis-ci.yml` (ops check + SPA parse + morning report smoke) | Not built | **INDIA_LIVE** |
| Governance regression | `eng001-regression.yml` (weekly + push) | Not built | **INDIA_LIVE** |
| Ops check | `scripts/aegis_ops_check.py` (22 artifacts, 9 schemas) | `usa/scripts/usa_ops_check.py` (18 artifacts, 9 schemas) | **BOTH_LIVE** — but neither checks recency |
| Deploy templates (systemd + launchd + Task Scheduler) | Yes (never proven-installed) | Not built | **INDIA_LIVE** (templates) |

### 2. Market data

| Capability | India | USA | Verdict |
|---|---|---|---|
| Daily OHLCV | `india/refresh_data.py` (yfinance NSE, 208 tickers) | `usa/scripts/refresh_market_data.py` (yfinance, 30 Dow) | **BOTH_LIVE** |
| Broad-market index | `NSEI_D1.parquet` | `^GSPC_D1.parquet` (S&P 500) | **BOTH_LIVE** |
| VIX-equivalent | `INDIAVIX_D1.parquet` | `^VIX_D1.parquet` | **BOTH_LIVE** |
| Sector-level indices | `NSEBANK_D1.parquet` | `^NDX` (NASDAQ 100) + `^DJI` (Dow) | **BOTH_LIVE** |
| Historical trade corpus | `reports/learning.parquet` (1060 trades, **FROZEN 2026-07-17**) | Not built | **INDIA_STATIC** |
| Corporate actions | Provisioned dir `markets/usa/raw/earnings/` (empty) | Same (empty) | **NEITHER** |
| ETF flows | `markets/usa/raw/etf/` (empty) | Same | **NEITHER** |

### 3. Fundamentals / news / flows / macro

| Capability | India | USA | Verdict |
|---|---|---|---|
| Fundamentals ingestion | `india/fundamentals_nse.py` (never invoked by any orchestrator) | `usa/research/fundamentals/run.py` (never invoked by `usa_daily.py`) + `core/usa_fundamentals.py` (research-only) | **BOTH exist as code, NEITHER runs in production** |
| News sentiment | `india/news_sentiment.py` (Google News RSS + FinBERT) — **manual only** | Not built | **INDIA_MANUAL** |
| Institutional flows (FII/DII) | `india/fii_dii.py` (NSE web API) — **manual only** | Not built | **INDIA_MANUAL** |
| Earnings calendar | Part of `india/fundamentals_nse.py` — unscheduled | Not built | **INDIA_MANUAL** |
| Macro / rates / currency | Frozen in `global_context.json` (2026-07-17) | Not built | **INDIA_STATIC** |
| SEC 13F institutional | Provisioned `markets/usa/raw/13f/` (empty) | Same | **NEITHER** |
| Insider transactions | Provisioned `markets/usa/raw/13f/` conceptually | Not built | **NEITHER** |
| Alternative data | Not built | Not built | **NEITHER** |

### 4. Regime detection

| Capability | India | USA | Verdict |
|---|---|---|---|
| Live regime engine | `india/confidence_engine.current_regime()` — "global" regime (200-DMA + VIX + Global-Risk gate) | `usa/research/risk/run.py` may embed simpler regime logic — not fully verified | **INDIA_LIVE**; USA has a lighter substitute |
| HMM regime | `india/regime_hmm.py` (dormant BY DESIGN per ARJUNA rejection) | Not built | **INDIA_DORMANT** |

### 5. Intelligence hierarchy (Global → Sector → Industry → Company)

| Capability | India | USA | Verdict |
|---|---|---|---|
| Global Intelligence (DEV017) | `research/global_intelligence/` — **FROZEN 2026-07-17** | Not built | **INDIA_FROZEN**, USA_MISSING |
| Sector Intelligence (DEV018) | `research/sector_intelligence/` — FROZEN | Not built | **INDIA_FROZEN**, USA_MISSING |
| Industry Intelligence (DEV019) | `research/industry_intelligence/` — FROZEN | Not built | **INDIA_FROZEN**, USA_MISSING |
| Company Intelligence (DEV020) | `research/company_intelligence/` — 11-dim composite, FROZEN | Not built (USA's `fusion` step is a flat single-tier 6-dim aggregate) | **INDIA_FROZEN**, USA has simpler substitute |

### 6. Recommendation engine

| Capability | India | USA | Verdict |
|---|---|---|---|
| Recommendation generator (pre-v2) | `india/recommendation_generator.py` (HRP + regime + Global-Risk, produces `AEGIS_LATEST.xlsx`) | Not built (USA uses only the v2 path) | **INDIA_LIVE** |
| Adaptive Rec v2 | `research/adaptive_rec_v2/run.py` (produces `recommendations.json`) | `usa/research/recommendations/run.py` (technical scoring on Dow 30) | **BOTH_LIVE** — different logic |
| Fusion | `research/adaptive_rec_v2/run_fusion.py` (10 dims) | `usa/research/fusion/run.py` (6 dims) | **BOTH_LIVE** — different depths |

### 7. Portfolio + risk

| Capability | India | USA | Verdict |
|---|---|---|---|
| Risk & capital | `research/risk_capital_v2/run.py` | `usa/research/risk/run.py` | **BOTH_LIVE** |
| Portfolio construction (multi-strategy) | `research/portfolio_construction/` — FROZEN | Not built (USA's `risk` step handles sizing) | **INDIA_FROZEN**, USA_MISSING as designed |
| Portfolio monitor | `research/portfolio_monitor/` — FROZEN | Not built | **INDIA_FROZEN** |
| Champion/Challenger | `research/champion_challenger/` — FROZEN | Not built | **INDIA_FROZEN** |
| Confidence calibration | `research/confidence_calibration/` — FROZEN | Not built | **INDIA_FROZEN** |
| Strategy doctor | `research/strategy_doctor/` — FROZEN | Not built | **INDIA_FROZEN** |

### 8. Learning / historical evidence

| Capability | India | USA | Verdict |
|---|---|---|---|
| Recommendation DNA | `research/recommendation_dna/{run_feedback, run_winner_genome}` — LIVE (feedback + winner genome production steps); but `run.py` (produces `.parquet`) is FROZEN | `usa/research/winner_genome/run.py` — stub (insufficient_data mode) | **BOTH_LIVE** but USA has no historical corpus |
| Winner Genome | Above | Stub (needs archive) | **BOTH_LIVE** but USA is empty |
| Institutional Memory | `research/institutional_memory/run.py` (LIVE) | `usa/research/institutional_memory/run.py` (LIVE) | **BOTH_LIVE** |
| Decision Attribution | `research/decision_attribution/run.py` (LIVE, with backtester-derived accuracy) | `usa/research/decision_attribution/run.py` (LIVE, but subsystem accuracy unavailable) | **BOTH_LIVE** with USA reduced |
| Continuous Benchmark | `research/benchmark/run.py` (LIVE, 1060 trades vs NIFTY) | `usa/research/benchmark/run.py` (stub — insufficient_evidence) | **BOTH_LIVE** but USA is empty |
| Knowledge Graph | `research/knowledge_graph/run.py` (LIVE) | Not built | **INDIA_LIVE**, USA_MISSING |
| Adaptive learning | `research/adaptive_learning/` — FROZEN (but its output `learning.parquet` is a live-pipeline dependency) | Not built | **INDIA_STATIC (critical)** |
| Backtesting | `research/backtesting/` — NEVER_INVOKED | Not built | **NEITHER runs** |

### 9. Delivery / UX

| Capability | India | USA | Verdict |
|---|---|---|---|
| Dashboard SPA | `ux/dashboard/frontend/index.html` (180 KB, routes: `/`, `/admin`, `/stock/{ticker}`, `/sheet/{ticker}`) | `usa/dashboard/frontend/index.html` (45 KB, routes: `/`, `/admin`, `/compare`, `/stock/{ticker}`) | **BOTH_LIVE** — USA lighter |
| Dashboard server | `ux/dashboard/frontend/serve.py` (port 8765) | `usa/dashboard/frontend/serve.py` (port 8766) | **BOTH_LIVE** |
| Telegram sender (legacy) | `india/telegram_notify.py` (via retry wrapper) | Not built | **INDIA_LIVE** |
| Telegram sender (UX030) | `scripts/telegram_send_ux030.py` | `usa/scripts/telegram_send.py` | **BOTH_LIVE** |
| Morning Report | `research/morning_report/run.py` | `usa/research/morning_report/run.py` | **BOTH_LIVE** |
| Google Sheets sync | `india/sheets_sync.py` | Not built | **INDIA_LIVE** |
| Excel export | `AEGIS_LATEST.xlsx` via `recommendation_generator.py` | Not built | **INDIA_LIVE** |

### 10. Cross-market

| Capability | India | USA | Verdict |
|---|---|---|---|
| India ↔ USA comparison | `compare/build_comparison.py` (I added) | Same | **BOTH_LIVE** (bidirectional) |
| Cross-market SPA route | `#/compare` in USA SPA | Same | **BOTH_LIVE** |

### 11. Constitutions + docs

| Capability | India | USA | Verdict |
|---|---|---|---|
| Constitution | `AEGIS_CONSTITUTION.md` (root) | `usa/AEGIS_USA_CONSTITUTION.md` | **BOTH** |
| Runbook | `docs/HOW_TO_RUN_PIPELINE.md` | `usa/docs/HOW_TO_RUN_USA.md` | **BOTH** |
| Design docs (ARCH, ARJUNA family) | 40+ under `docs/` | Not built | **INDIA_ONLY** |

---

## Aggregate parity score (runtime-verified)

Counting only cells where the CAPABILITY EXISTS AT ALL:
- **BOTH_LIVE:** ~15 cells
- **INDIA_LIVE / USA_MISSING:** ~10 cells (major gaps)
- **INDIA_FROZEN / USA_MISSING:** ~8 cells (both markets miss the same capability but India at least has the artifact)
- **INDIA_MANUAL / USA_MISSING:** 4 cells (news, FII/DII, fundamentals, earnings)
- **NEITHER:** ~5 cells (13F, insider, alt data, corporate actions, macro-live)

**Corrected parity estimate:** USA runtime-parity with India is ~50% on the *live-daily* surface (15/~30), dropping to ~35% when you include capabilities where India has code (even if frozen) and USA has nothing.

**Corrected earlier claim:** I previously said USA had 30-40% parity, then walked it back to "full parity." The runtime-verified answer is **~50% of live capabilities and ~35% of total capabilities in the repo**. Neither prior number was right.

---

## What USA would need for TRUE runtime parity

1. **Historical trade corpus** — a USA equivalent of `learning.parquet`. Would take building a paper-trade replay engine (walk price history, apply the recommendation logic, track outcomes).
2. **MON001-equivalent** forward validator for USA.
3. **Champion/Challenger** for USA.
4. **Confidence calibration** for USA.
5. **Portfolio construction (multi-strategy)** for USA.
6. **Portfolio monitor** for USA.
7. **Knowledge graph** for USA.
8. **News ingestion** for USA (RSS or similar).
9. **Institutional flow ingestion** for USA (SEC 13F).
10. **Wire `usa/research/fundamentals/run.py` into `usa_daily.py`.**

Even after 1-10, both markets would still share the **stale learning corpus** and **stale global_context** issues (FINDING 1 and FINDING 2 from the completion doc). Those are cross-market problems, not USA-only.

---

## What India would need for TRUE production readiness

Independent of USA parity, India has these unresolved runtime issues:

1. **`learning.parquet` regeneration** — the corpus needs a scheduled rebuild step, currently frozen since 2026-07-17.
2. **Intelligence tier refresh** — either wire the 4-tier engines into a daily cadence, or explicitly decommission and remove the SPA tiles reading their stale outputs.
3. **News + FII/DII + fundamentals scheduling** — decide whether these belong in the daily orchestrator or remain manual, and act accordingly.
4. **Ops check recency** — extend `scripts/aegis_ops_check.py` to verify artifact freshness, not just existence.
5. **Reconcile ARCH017/017A/018 docs** with the code they claim doesn't exist.
