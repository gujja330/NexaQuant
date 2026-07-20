# AEGIS Repository Discovery · v1
**Stage 0 · Raw inventory · No design, no PRD, no assumptions**
**Generated: 2026-07-20**

---

## Executive summary

AEGIS is significantly larger and more feature-complete than my recent
statements suggested. Prior to this discovery I claimed India "doesn't
have news / fundamentals / institutional flows." **That was wrong on
all three counts.** India has all of them, plus more capabilities I
never mentioned. The problems are wiring, discoverability, and
observability — not absence.

Raw counts:
- **Top-level directories:** 22 (excluding hidden and `__pycache__`)
- **`research/` engine modules:** 24 (only 12 of them are wired into
  the current daily orchestrator)
- **`india/` Python files:** 50 at the top level, plus 10 AI labs and 1
  monitoring pack (MON001)
- **`reports/` JSON artifacts:** 105
- **`reports/` parquet artifacts:** 18
- **`docs/` documentation files:** 40+
- **GitHub workflows:** 5
- **`data/raw/india/*.parquet`:** OHLCV plus `fundamentals.parquet`,
  `news_sentiment.parquet`, `fii_dii.parquet` (already collecting)
- **`markets/usa/raw/`:** provisioned directories for
  `{13f, earnings, etf, fundamentals, macro, news}` — dirs exist,
  data not yet populated
- **`ux/` surfaces:** dashboard SPA + telegram renderer

---

## 1. Top-level topology

| Directory | Purpose (inferred) | Status |
|---|---|---|
| `backtest/` | Backtesting outputs / harnesses | Exists — not yet inspected in depth |
| `chat/` | Presumably conversation state | Not inspected |
| `compare/` | India ↔ USA comparison module | **I added this recently** |
| `config/` | `base_config.yaml` + init | Exists |
| `core/` | Core shared code | Not inspected |
| `data/` | Data lake (raw + cache + archive + market_intelligence) | Live |
| `deploy/` | systemd / launchd / windows-task scheduler artifacts | Live |
| `docs/` | 40+ architecture / strategy / research docs | Rich |
| `execution/` | Execution / broker integration | Not inspected |
| `experiments/` | Research experiments | Not inspected |
| `india/` | **INDIA MARKET SPECIFIC CODE** (50 top-level `.py` files + 10 AI labs + MON001) | Live production |
| `logs/` | Runtime logs | Live |
| `markets/` | Multi-market data caches (india + usa research + raw dirs) | Partial |
| `nexaquant/` | The bot service (`ops/`, `lib/`, tests, notify) | Live |
| `output/` | Generated outputs | Not inspected |
| `reports/` | **All engine artifacts** (105 JSON + 18 parquet + MDs + XLSX) | Live |
| `research/` | **24 engine modules** (production + experimental + probes) | Mixed |
| `scripts/` | Orchestrators, health checks, e2e, telegram send | Live |
| `strategy/` | Strategy definitions | Not inspected |
| `tools/` | Utility scripts | Not inspected |
| `usa/` | **USA parallel deployment I built** | Partial (v2.0 today) |
| `ux/` | Dashboard SPA + Telegram renderer (India) | Live |

---

## 2. `research/` engine modules — WIRING TRACE

**Wired into `scripts/aegis_daily_v2.py` (the current India orchestrator, 16 steps):**

1. `adaptive_rec_v2/` — Adaptive Recommendation Engine v2.0
2. `validation_v2/` — Validation Engine v2.0 (paper harness + drift)
3. `risk_capital_v2/` — Risk & Capital Engine v2.0
4. `recommendation_dna/` — DNA feedback v1.5 + Winner Genome v2.0
5. `knowledge_graph/` — v1.6 (communities + propagation + stress)
6. `adaptive_rec_v2/run_fusion.py` — Intelligence Fusion v2.1
7. `validation_v2/run_stock_history.py` — per-ticker rollup
8. `validation_v2/run_price_context.py` — CMP + 52W
9. `decision_center/` — v1.0 overnight diff + exit center
10. `institutional_memory/` — archive + lifecycle + missed + rec-history
11. `decision_attribution/` — per-rec + subsystem accuracy
12. `benchmark/` — Continuous Benchmark v1.0 vs NIFTY
13. `morning_report/` — daily HTML + Markdown

**EXISTS in the repo but NOT wired into the current daily orchestrator:**

| Module | Purpose (from README/code) | Status |
|---|---|---|
| `research/global_intelligence/` (DEV017) | Global/macro composite → `reports/global_context.json` | Runs somewhere — output IS present + fresh |
| `research/sector_intelligence/` (DEV018) | Sector composite → `reports/sector_context.json` + `data/market_intelligence/raw/` | Output PRESENT |
| `research/industry_intelligence/` (DEV019) | Industry composite → `reports/industry_context.json` | Output PRESENT |
| `research/company_intelligence/` (DEV020) | **11-dimension per-ticker composite** with global → sector → industry inheritance chain, 5 rank tables, drivers/risks | Output partially in `reports/company_context.json` |
| `research/champion_challenger/` | Strategy competition (top_5_ew, kelly_quarter, max_sharpe…) | `reports/champion_strategy.json` + `challenger_scoreboard.json` present |
| `research/confidence_calibration/` | Platt / isotonic calibration | `reports/confidence_calibration.json` present |
| `research/portfolio_construction/` | Multi-strategy portfolios | `reports/portfolio.json` + `portfolio_leaderboard.json` |
| `research/portfolio_monitor/` | Live portfolio tracking | `reports/portfolio_monitor.json` |
| `research/strategy_doctor/` | Strategy diagnostics | `reports/strategy_doctor.json` |
| `research/adaptive_learning/` | Model retraining | Not verified |
| `research/backtesting/` | Backtest engine | Not verified |
| `research/recommendations/` | Older recommendation engine | Deprecated? |
| `research/research_assistant/` | Research helper | Not verified |
| `research/RISK001-A/` | Sealed exit-policy study | Sealed |

**Standalone probes / experiments (top-level `.py` files in `research/`):**

Files like `research/breakout_test.py`, `research/hmm_regime_probe.py`,
`research/deep_walkforward.py`, `research/mtf_edge_probe.py`, etc. —
36 total, appear to be one-off research probes producing CSV/MD
outputs. Not part of daily production.

---

## 3. `india/` — India market-specific code (50 top-level `.py`)

These are UNSEALED (not MON001/OPS001) but predate the `research/`
modules and appear to run via `india/daily_run.py`, `india/aegis_engine.py`
etc. Not through `scripts/aegis_daily_v2.py`.

Key modules I missed in prior claims:

| File | What it does | Live? |
|---|---|---|
| **`india/news_sentiment.py`** | Google News RSS → FinBERT sentiment scoring per stock. Writes `data/raw/india/news_sentiment.parquet`. Forward-collected. | **LIVE** (parquet on disk) |
| **`india/fundamentals_nse.py`** | yfinance fundamentals (ROE, D/E, PE, PB, earnings growth, revenue growth) + earnings calendar. Writes `data/raw/india/fundamentals.parquet`. | **LIVE** (parquet on disk) |
| **`india/fii_dii.py`** | Foreign / Domestic institutional cash flows from NSE. Writes `data/raw/india/fii_dii.parquet`. | **LIVE** (parquet on disk) |
| **`india/regime_hmm.py`** | Hidden Markov Model regime detection (breadth + VIX + realized vol). | Live |
| `india/aegis_engine.py` | Main engine (older path?) | Live |
| `india/arjuna_v2.py`, `arjuna_strategy.py`, `arjuna_os.py` | Arjuna strategy family | Live |
| `india/technical_factors.py` | Technical indicator library | Live |
| `india/feature_engine.py` | Feature engineering | Live |
| `india/recommendation_generator.py` | Recommendation core | Live |
| `india/recommendation_registry.py` | Recommendation DB | Live |
| `india/rolling_recommendations.py` | Rolling rec logic | Live |
| `india/moonshot.py` | Moonshot strategy | Live |
| `india/global_risk.py` | Global risk features | Live |
| `india/probability_surface.py` | Probability modeling | Live |
| `india/confidence_engine.py` | Confidence layer | Live |
| `india/risk_forecast.py`, `risk_tiers.py` | Risk framework | Live |
| `india/dynamic_engine.py`, `dynamic_policy.py` | Dynamic policy | Live |
| `india/scorecard.py` | Score compilation | Live |
| `india/sheets_sync.py` | Google Sheets sync | Live |
| `india/telegram_notify.py` | **Legacy Telegram sender — the one that fires from GitHub Actions** | Live |
| `india/monthly_report.py`, `monthly_snapshot.py` | Monthly reports | Live |
| `india/broker_angelone.py` | Angel Broking integration | Live |

Plus MANY more — I have not fully inspected all 50 files.

### India `ai_lab/` (10 labs, some README-only, some real)

- **LAB001_Earnings** — Earnings Intelligence
- **LAB002_Fundamentals** — Point-in-Time Fundamentals
- **LAB003_Events** — Corporate Actions / Events
- **LAB004_Flows** — Institutional Money
- **LAB005_Ranking** — Learning-to-Rank
- **LAB006_Exit_Strategy** — Exit Strategy
- **LAB007_Dynamic_Exposure** — Dynamic Exposure / Position Sizing
- **LAB008_Horizon_Calibration** — Holding-period calibration
- **LAB009_Horizon_Phase_Recalibration** — Recalibration
- **LAB010_H84_Robustness_Validation** — 84-day robustness

Status of each lab varies from README-only to functional code. Not
audited in detail.

### India `monitoring/`

- **MON001_Forward_Validation/** — Sealed forward-validation harness
  producing the diagnostics I keep referring to. Contains
  `sealed_baseline_fingerprint` + `reports/mon001_diagnostics_*.json`.
  Emits the daily `dashboard_*.md`, feeds `india/monitoring/MON001_Forward_Validation/reports/mon001_alerts.jsonl`.

---

## 4. Data layer

### `data/raw/india/`

- 208+ `{TICKER}_D1.parquet` — daily OHLCV per NSE stock
- **`fundamentals.parquet`** — from `india/fundamentals_nse.py`
- **`news_sentiment.parquet`** — from `india/news_sentiment.py`
- **`fii_dii.parquet`** — from `india/fii_dii.py`
- `global/` subdir — global data caches
- `intraday/` subdir — intraday bars (M5/M15 exist, git-ignored)

### `data/raw/usa/`

Directory exists at path but I have not verified what's inside.

### `data/market_intelligence/`

- `raw/` — DEV018 sector intelligence caches
- `derived/` — derived intelligence
- `snapshots/` — historical snapshots

### `data/archive/`

- **My addition** — Institutional Memory v1.0 daily bundles
  (`YYYY/MM/DD/bundle/` + `manifest.json`)

### `data/layers/`, `data/cache/`

Not inspected.

### `markets/usa/raw/` — Provisioned but empty

- `13f/` — SEC 13F institutional filings (empty)
- `earnings/` — earnings calendar (empty)
- `etf/` — ETF flows (empty)
- `fundamentals/` — fundamentals per USA ticker (empty)
- `macro/` — macro data (empty)
- `news/` — news feed (empty)

These directories tell me the operator's intent was to provision USA
news/fundamentals ingestion from day 1. It just wasn't populated.

---

## 5. `reports/` artifact inventory — 105 JSON + 18 parquet

Grouped by concern:

**Market intelligence tier (DEV017-020):**
- `global_context.json` / `global_context.parquet`
- `sector_context.json` / `sector_context.parquet`
- `industry_context.json` / `industry_context.parquet`
- `company_context.json` / `company_context.parquet`
- `company_report.json`, `sector_report.json`

**Recommendation & scoring:**
- `recommendations.json` / `recommendations.parquet`
- `adaptive_rec_v2_{signal,scoreboard,reliability,feature_importance}.{json,parquet}`
- `investment_intelligence.{json,parquet}`
- `intelligence_{summary,conflicts,explanation}.json`
- `confidence_{calibration,bias}.json` + `calibration_history.json` + `calibration_metrics.json`
- `reliability_diagram.json`
- `signal_attribution.json`

**Strategy tier:**
- `champion_strategy.json`
- `challenger_scoreboard.json`
- `strategy_{comparison,leaderboard,doctor}.{json,parquet}`
- `head_to_head_matrix.json`
- `promotion_recommendation.json`

**Portfolio tier:**
- `portfolio.{json,parquet}`
- `portfolio_{monitor,report,health,leaderboard}.{json,parquet}`
- `holdings_demo.json`
- `allocation_report.json`
- `rebalance_{plan,report}.json`
- `execution_plan.json`

**Risk tier:**
- `risk_capital_v2_{latest,YYYY-MM-DD}.json`
- `risk_capital_v2_sizing.parquet`
- `risk_report.json`
- `stress_{scenarios,test}.json`

**Validation tier:**
- `validation_v2_{latest,daily_YYYY-MM-DD}.{json,md}`
- `stock_validation.json`
- `recommendation_accuracy.json`
- `recommendation_history.json`
- `recommendation_lifecycle.{json,parquet}`
- `recommendation_versions.json`
- `recommendation_statistics.json`
- `recommendation_dna.{json,parquet}` + `recommendation_dna_feedback.json`

**Knowledge / graph tier:**
- `knowledge_graph.{json,parquet}`
- `community_clusters.json`
- `entity_network.json`
- `company_network.json`
- `sector_network.json`
- `relationship_matrix.json`
- `influence_propagation.json`
- `graph_{statistics,timeline}.json`
- `recommendation_paths.json`

**Learning / analytics tier:**
- `winner_genome.json`
- `decision_attribution.json`
- `learning_summary.json`
- `pattern_discovery.json`
- `success_patterns.json`
- `failure_{analysis,patterns}.json`
- `root_cause_analysis.json`
- `learning.parquet` (the 1060-trade historical corpus)

**Benchmark tier:**
- `benchmark.json`
- `backtest_summary.{json,parquet}`
- `aegis_performance.json`
- `performance_{metrics,report}.json`
- `trade_summary.json`

**Decision center tier:**
- `decision_center_today.json`
- `decision_center_notifications.json`
- `watchlist.json`
- `missed_opportunities.json`

**Ops tier:**
- `ops_check.json`
- `aegis_daily_v2_history.jsonl`
- `drift_report.json`
- `regime_comparison.json`

**Dashboard / Telegram tier:**
- `dashboard_{config,layout,routes,theme,widgets}.json`
- `telegram_{commands,templates,ui_config,layouts,notification_rules,examples}.{json,md}`
- `telegram_health_YYYY-MM-DD.json`
- `telegram_delivery_YYYY-MM-DD.jsonl`

**Executive / meta:**
- `executive_summary.json`
- `improvement_plan.json`
- `improvement_suggestions.json`
- `self_improvement.json`
- `alerts.json`

That's 105 JSON artefacts. Each has a producer (unclear for many) and
one or more consumers.

---

## 6. Frontend / UX

### `ux/dashboard/frontend/`

- `index.html` — 180 KB SPA (India), routes: `/`, `/admin`, `/stock/{ticker}`, `/sheet/{ticker}`
- `serve.py` — local HTTP server (port 8765)
- `lib/`, `publish/`, `tests/` — supporting modules

### `usa/dashboard/frontend/`

- `index.html` — 45 KB SPA (USA, USD)
- `serve.py` — port 8766

### `ux/telegram/`

- `lib/renderer.py` — UX030 message renderer (India)
- `lib/aggregator.py` — loads India reports
- `publish/`, `tests/`

### `usa/telegram/`

- `lib/renderer.py` — my USD-adapted USA renderer

### `scripts/telegram_send_ux030.py` + `usa/scripts/telegram_send.py`

Two senders — one for each market.

---

## 7. Workflows / Automation

- **`.github/workflows/aegis-daily.yml`** — India daily pipeline, cron 06:00 IST
- **`.github/workflows/aegis-ci.yml`** — India CI on every push
- **`.github/workflows/aegis-usa.yml`** — USA daily pipeline (I added)
- **`.github/workflows/eng001-regression.yml`** — Governance validator
- **`.github/workflows/mon001-daily.yml`** — MON001 sealed daily

Systemd / launchd / Windows Task Scheduler artefacts under `deploy/`.

---

## 8. Documentation inventory (40+ files under `docs/`)

Categorized:

**Architecture:**
- `AEGIS_ARCHITECTURE.md`, `AEGIS_ARCHITECTURE_REVIEW.pdf`
- `AEGIS_WHITEPAPER.md`
- `ARCH001_RECOMMENDATION_LIFECYCLE.md`
- `ARCH001A_INVESTMENT_PHILOSOPHY.md`
- `ARCH002_EXIT_FRAMEWORK.md`
- `ARCH017_GLOBAL_INTELLIGENCE_ENGINE.md`
- `ARCH017A_MARKET_DATA_CANONICAL_MODEL.md`
- `ARCH018_SECTOR_INTELLIGENCE_ENGINE.md`

**Governance / operations:**
- `AEGIS_CONSTITUTION.md` (I wrote this)
- `CHANGE_CONTROL_CHECKLIST.md`
- `DAILY_OPERATIONS.md`
- `DEPLOYMENT.md`, `DEPLOYMENT_GUIDE.md`
- `DESIGN_DECISIONS.md`
- `ENGINEERING_CHECKLIST.md`
- `ENGINE_EVOLUTION_GUIDE.md`
- `ENG001_REPORT.md`, `ENG002_REPORT.md`, `ENG003_REPORT.md`
- `ENG004_CI_ROOTCAUSE.md`
- `HOW_TO_RUN_PIPELINE.md` (I wrote this)

**Research / strategy:**
- `AEGIS_RESEARCH_AGENDA_2035.md`
- `AEGIS_RESEARCH_HANDBOOK.md`
- `AI_ML_REFINEMENT_PLAN.md`
- `AI_MODELS_VALIDATION.md`
- **ARJUNA family** (10+ docs): `ARJUNA_AI_STRATEGY`, `ARJUNA_ALPHA_DATA_RESEARCH`,
  `ARJUNA_ALPHA_MASTER`, `ARJUNA_BUILD_STAGES`, `ARJUNA_DEEP_RESEARCH_ML`,
  `ARJUNA_OPERATING`, `ARJUNA_PRODUCT_ROADMAP`, `ARJUNA_RESULTS`,
  `ARJUNA_STRATEGY_DECISION`, `ARJUNA_V2_ARCHITECTURE`, `ARJUNA_V4_ROADMAP`,
  `ARJUNA_v2_Architecture.pdf`
- `FEATURE_REGISTRY.md`
- `FUTURE_RESEARCH_ROADMAP.md`
- `DATASET_SHORTLIST.md`

**Session logs / snapshots:**
- `chat_transcript_2026-07-13.md`
- `chat_transcript_2026-07-18.md`

I've read almost none of these. Most contain design context that
should inform any new architecture decision.

---

## 9. Directly contradicting my earlier claims

The following statements I made in recent commits/messages are FALSE
or misleading. Recorded here so they don't propagate into any future
document:

1. **"India doesn't have news either"** — FALSE. `india/news_sentiment.py`
   is live, FinBERT-based, writing `data/raw/india/news_sentiment.parquet`.
2. **"India doesn't have fundamentals either"** — FALSE.
   `india/fundamentals_nse.py` pulls yfinance fundamentals + earnings
   calendar, writes `data/raw/india/fundamentals.parquet`.
3. **"India doesn't have institutional flows"** — I never claimed this
   explicitly, but the FII/DII engine (`india/fii_dii.py`) exists.
4. **"AEGIS is technicals-only"** — FALSE. It has technicals +
   fundamentals + news + institutional flows + HMM regime + intelligence
   tiers + strategy competition + calibration. Many of these just
   aren't wired into `aegis_daily_v2.py`.
5. **"USA has parity with India"** — FALSE. My USA v2.0 build covers
   maybe 30–40% of India's actual surface.
6. **The India 16-step orchestrator does NOT run:** intelligence tiers
   (DEV017–020), champion/challenger, calibration, portfolio
   construction, portfolio monitor, strategy doctor, news sentiment
   ingestion, fundamentals ingestion, FII/DII ingestion, HMM regime.
   Some of those run on a separate schedule (`india/daily_run.py` or
   MON001), others may not run at all.

---

## 10. What I still don't know (honest gaps)

- Which script actually runs `india/news_sentiment.py`,
  `india/fundamentals_nse.py`, `india/fii_dii.py` on a schedule?
- Which script produces the current `reports/global_context.json`?
  It's fresh but not in `aegis_daily_v2.py`.
- Which script produces the current `reports/champion_strategy.json`
  and `reports/challenger_scoreboard.json`?
- Is `india/daily_run.py` an alternative daily runner? What does it do?
- How does `nexaquant/ops/daemon.py` fit in?
- What's in `nexaquant/ops/pipelines/aegis_daily.yaml`?
- What is `chat/` for? What is `core/` for?
- What's in `backtest/` currently?
- What produces `learning.parquet` (the 1060-trade corpus)?
- Are the reports/dashboard_config.json etc. driving the SPA
  or is the SPA hardcoded?
- The `research/recommendations/` module (with no version suffix) —
  is it deprecated? Is it consumed anywhere?

Every one of these has to be answered before Stage 1 (PRD) can be
written with confidence.

---

## 11. Next steps (Stage 0 continuation)

Before writing the PRD, I need to answer at minimum:

- Read `india/daily_run.py` end-to-end
- Read `nexaquant/ops/daemon.py` + `nexaquant/ops/pipelines/aegis_daily.yaml`
- Read the READMEs of the 12 unwired `research/` modules
- Read `ARCH017_GLOBAL_INTELLIGENCE_ENGINE.md` and
  `ARCH018_SECTOR_INTELLIGENCE_ENGINE.md`
- Trace producer→consumer of every artefact in `reports/` that's
  currently fresh
- Verify what actually runs on the scheduled workflows

That's the honest completion of Stage 0. Only when the discovery
document answers those questions can Stage 1 (PRD) begin.

---

## 12. Immediate rules I'm binding myself to

- **No new code lands until Stages 0–8 are approved by the operator.**
- **No architectural claims made without evidence in this document.**
- **No "parity" statement made without a matrix backing it.**
- **If I catch myself drifting toward "let me just build X quickly," I
  stop and ask.**

---

_End of AEGIS Repo Discovery v1. This document is the ground truth for
all subsequent Stage 1–8 work._
