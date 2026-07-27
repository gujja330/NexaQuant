# AEGIS Sprint A1 · Repository Audit
### 🔒 LOCKED 2026-07-24 · Wave 1 · Repository Intelligence

**Purpose:** first prerequisite for [Phase 3 execution](AEGIS_PHASE3_MASTER_ROADMAP.md). Repository evidence only — no assumptions. Every downstream sprint reads this document.

**Scope covered (10 sections):** recommendation entry points · Runner 1 dependency map · Runner 2 dependency map · history-producer inventory · engines inventory · orchestrators · duplicate/overlapping logic · sealed files · disconnected engines · reports produced but never consumed.

**Cross-cutting risks flagged at the bottom** — six severe findings that shape every downstream sprint.

---

## 1. Recommendation entry points

Ten producers found (not two — Runner 1 alone has four sub-variants across India + USA, and there are legacy adapters + a bridge script). "Recommendation-shaped output" = files matching `recommendations*.json` · `*_recommendation*.parquet` · `aegis_*.csv` · `investment_intelligence.json` · `intelligence_summary.json` · `execution_plan.json` · `trade_summary.json` · `watchlist.json`.

| # | Producer script | Runner | Output file(s) | Downstream consumers |
|---|---|---|---|---|
| 1 | `india/recommendation_generator.py` (950 LOC monolith) | **Runner 1 · legacy** — `.github/workflows/aegis-daily.yml` step "Run AEGIS engine" | `data/aegis_today.csv` · `data/aegis_candidates.csv` · `data/aegis_registry.csv` · `reports/AEGIS_<date>.xlsx` | `india/recommendation_db.py` · `india/telegram_notify.py` · `india/scorecard.py` · `india/ops_check.py` · `india/sheets_sync.py` · `india/aegis_dashboard.py` · `india/monitoring/MON001_Forward_Validation/*` · `backend/replay/runner1_ingest.py` |
| 2 | `india/recommendation_db.py` | **Runner 1 · legacy support** | `data/aegis_recommendation_db.csv` (append-only ledger) | feeds `runner1_ingest.py` walk-forward |
| 3 | `research/adaptive_rec_v2/run.py` | **Runner 1 · v2 signal model** — `scripts/aegis_daily_v2.py` step `adaptive_rec_v2` | `reports/adaptive_rec_v2_signal.json` (+ `_scoreboard`, `_feature_importance`, `_reliability`, `_signal.parquet`, `_migration.md`) | `run_fusion.py` (fusion) · read-only in docs. **Parquet has no `ticker` column** (falls back in `research/risk_capital_v2/compute/engine.py::_load_calibrated_conf`) |
| 4 | `research/adaptive_rec_v2/run_fusion.py` | **Runner 1 · Fusion v2.1** — `aegis_daily_v2` step `fusion` | `reports/investment_intelligence.json` (+ `.parquet`) · `intelligence_summary.json` · `intelligence_conflicts.json` · `intelligence_explanation.json` | `scripts/aegis_ops_check.py` · `ux/telegram/lib/aggregator.py` · `usa/research/fusion/run.py` (mirror) · `research/morning_report/*` · `research/decision_attribution/*` · `research/institutional_memory/*` · `research/recommendation_dna/lib/winner_genome.py` |
| 5 | `research/recommendations/run.py` (DEV023 · **DEPRECATED** per `docs/AEGIS_STAGE0_COMPLETION.md`) | **NOT in any orchestrator; run out-of-band** | `reports/recommendations.json` (last mtime 2026-07-17) · `.parquet` · `watchlist.json` · `trade_summary.json` · `execution_plan.json` | `research/adaptive_rec_v2/compute/fusion_engine.py` · `research/risk_capital_v2/compute/engine.py` · `research/validation_v2/*` · `research/knowledge_graph/lib/{entities,relationships}.py` · `research/recommendation_dna/compute/engine.py` · `research/institutional_memory/lib/*` · `research/decision_center/lib/snapshot.py` · `research/morning_report/*` · `research/decision_attribution/lib/attribution.py` · `research/benchmark/*` · `ux/telegram/lib/aggregator.py` · `ux/dashboard/lib/{widgets,routes}.py` · `scripts/aegis_ops_check.py` · `compare/build_comparison.py` — **~30 downstream engines but no orchestrator regenerates it** |
| 6 | `india/recommendation_intelligence/run.py` (wraps `backend.recommendation.RecommendationEngine`) | **Runner 2 · Rec v3** — `aegis_daily_v2` step `recommendation_intelligence` | `reports/recommendations_v3.json` (+ `_summary`, `_conflicts`, `ai_recommendation_narrative`) · appends `reports/recommendation_history.parquet` | `india/risk_engine/run.py` · `usa/scripts/usa_ops_check.py` · `backend/replay/*` · `backend/learning/*` · `backend/benchmark/*` |
| 7 | `usa/research/recommendation_intelligence/run.py` | **Runner 2 · Rec v3 · USA** — `usa/scripts/usa_daily.py` step `recommendation_intelligence` | `usa/reports/recommendations_v3.json` (+ derivatives) · appends `usa/reports/recommendation_history.parquet` | `usa/research/risk_engine/run.py` · `usa/scripts/usa_ops_check.py` · `usa/research/portfolio_engine/run.py` (chain) |
| 8 | `usa/research/recommendations/run.py` | **Runner 1 · USA analog · WIRED** — `usa/scripts/usa_daily.py` step `recommendations` | `usa/reports/recommendations.json` | `usa/research/validation/run.py` · `usa/research/risk/run.py` · `usa/research/fusion/run.py` · `usa/research/institutional_memory/run.py` · `usa/research/winner_genome/run.py` · `usa/research/decision_attribution/run.py` · `usa/research/benchmark/run.py` · `usa/research/morning_report/run.py` · `usa/telegram/lib/renderer.py` · `compare/build_comparison.py` |
| 9 | `india/rolling_recommendations.py` | **Research/evidence only** (not orchestrated) | Not in `reports/` — writes to `india/evidence/` | `india/monthly_report.py` · `india/monthly_snapshot.py` · `india/evidence/arjuna_monthly_report.py` |
| 10 | `backend/replay/runner1_ingest.py::ingest_legacy_ledger` | **Runner 1 · replay bridge** (CLI + `backend/tests/test_sprint77_runner1.py`) | `reports/recommendation_history_runner1.parquet` · `reports/learning_corpus_runner1.parquet` | `backend/replay/walk_forward.py::run_walk_forward_runner1` · `backend/benchmark/report.py` → `reports/benchmark_runner1_india.json` · `reports/walkforward_runner1_*.json` |

---

## 2. Runner 1 full dependency map

### 2a. `research/adaptive_rec_v2/run.py` → `compute/engine.py` → `publish/bundle.py`

| Direction | Path | Notes |
|---|---|---|
| INPUT | `reports/learning.parquet` (via `lib/features.py::load_learning`, hard-coded `LEARNING = _ROOT / "reports" / "learning.parquet"`) | **Only input.** NUMERIC_FEATURES = `dim_momentum, dim_trend, dim_rs_nifty, dim_volatility, dim_drawdown, dim_position_52w, score_at_entry, confidence`. CATEGORICAL = `sector, industry`. Label = `is_winner`. Return field = `return_pct`. |
| OUTPUT | `reports/adaptive_rec_v2_signal.json` | Headline metrics + Precision@K delta vs v1.4 baseline |
| OUTPUT | `_scoreboard.json` · `_feature_importance.json` · `_reliability.json` · `_signal.parquet` · `_migration.md` | Model scoreboard + per-feature importance + reliability curves + per-test-row predictions (**no ticker column**) + human-readable migration guide |

### 2b. `research/adaptive_rec_v2/run_fusion.py` → `compute/fusion_engine.py`

| Direction | Path |
|---|---|
| INPUT | `reports/recommendations.json` (source of tickers · DEV023 output — **the keystone gap · see cross-cutting risk #1**) |
| INPUT | `reports/learning.parquet` · `validation_v2_latest.json` · `risk_capital_v2_latest.json` · `entity_network.json` · `recommendation_dna_feedback.json` · `confidence_calibration.json` · `recommendation_paths.json` |
| OUTPUT | `reports/investment_intelligence.json` (+ `.parquet`) · `intelligence_summary.json` · `intelligence_conflicts.json` · `intelligence_explanation.json` |

Downstream: Telegram (`ux/telegram/lib/aggregator.py` · `scripts/telegram_send_ux030.py`) · dashboard (`ux/dashboard/lib/widgets.py`) · morning report · decision attribution · ops check.

### 2c. `india/recommendation_generator.py` (950-line legacy monolith)

**Imports (INPUTS via `india.*` modules):** `india.arjuna_v2` · `india.feature_engine.load_panels` · `india.technical_factors._rsi` · `india.data_nse.NIFTY200` · `india.sectors.SECTORS/sector_of` · `india.confidence_engine.current_regime` · `india.probability_surface.horizon_view/mode_of` · `india.capital_ladder.rupees` · `india.config.VERSION` · `india.horizon_matrix` · `india.dynamic_policy`.

| Direction | Path (evidence lines) |
|---|---|
| INPUT | `data/aegis_registry.csv` (line 183) |
| INPUT (via `feature_engine.load_panels`) | `data/raw/india/NIFTY200/*_D1.parquet` |
| OUTPUT | `data/aegis_registry.csv` (line 190, 941 rewrite) · `data/aegis_today.csv` (483) · `data/aegis_candidates.csv` (551) · `reports/AEGIS_<date>.xlsx` (930) |

**Does NOT write to `reports/*.json`.** Nothing here feeds `reports/recommendations.json`.

Downstream: workflow step 6 in `aegis-daily.yml` invokes it; step 7 verifies `aegis_today.csv` freshness gates Telegram. `india/recommendation_db.py` snapshots CSV → `data/aegis_recommendation_db.csv`. `india/telegram_notify.py` reads CSVs and delivers sealed OPS001-I Telegram diary. `india/{scorecard,ops_check,sheets_sync,aegis_dashboard}.py`, `india/monitoring/MON001_Forward_Validation/*` all read these CSVs. `backend/replay/runner1_ingest.py` reshapes `aegis_recommendation_db.csv` → `reports/recommendation_history_runner1.parquet` + `learning_corpus_runner1.parquet`.

---

## 3. Runner 2 (Rec Engine v3) full dependency map

### 3a. `backend/recommendation/engine.py`

Composed of `conflict.py` + `calibration.py` + `regime_adjust.py` + `classifier.py` + `explainer.py` + `types.py`. Pure composition — takes `ensemble_top_rows`, `features_df`, `selected_features`; emits `RecommendationBatch`. **No I/O of its own.**

### 3b. `india/recommendation_intelligence/run.py`

| Direction | Path |
|---|---|
| INPUT | `reports/ensemble.json` (Sprint 2.7 · Model Factory) — **FATAL if missing** |
| INPUT | `reports/market_intelligence_summary.json` (regime) · `reports/selected_features.json` (Sprint 2.6) · Feature-Store snapshot via `backend.feature_store.feature_history.list_snapshots(_ROOT, "india")` (latest) → parquet under `features/india/` |
| OUTPUT | `reports/recommendations_v3.json` (+ `_summary`, `_conflicts`, `ai_recommendation_narrative`) |
| SIDE-EFFECT | appends `reports/recommendation_history.parquet` via `backend.persistence.append_snapshot_row` (fail-open) · `register_model(...)` writes to `model_registry.jsonl` |

Downstream chain: `risk_engine → portfolio_engine → execution_simulator → learning_engine`. Also: `backend/replay/*` · `scripts/aegis_ops_check.py` (schema).

### 3c. `usa/research/recommendation_intelligence/run.py`

Same shape under `usa/reports/`. Downstream: identical chain.

---

## 4. History-producer inventory

| History file | Producer (dedupe key) | Populated |
|---|---|---|
| `reports/recommendation_history.parquet` | `india/recommendation_intelligence/run.py:171` → `append_snapshot_row` (**(market, asof)**) | ✅ · 2026-07-21 · 927 KB |
| `reports/recommendation_history_runner1.parquet` | `backend/replay/runner1_ingest.py:65` (also `:173`) — (market, asof) via keep-mask | ✅ · 2026-07-21 · 20 KB |
| `reports/portfolio_history.parquet` | `india/portfolio_engine/run.py:168` → append_snapshot_row (market, asof) | ✅ · 2026-07-21 · 16 KB |
| `reports/risk_history.parquet` | `india/risk_engine/run.py:180` (market, asof) | ✅ · 2026-07-21 · 20 KB |
| `reports/execution_history.parquet` | `india/execution_simulator/run.py:233` (market, asof) | ❌ **not populated** |
| `reports/learning_history.parquet` | `india/learning_engine/run.py:156` (market, asof) | ❌ **not populated** |
| `reports/learning_corpus.parquet` | `india/learning_engine/run.py` (market, ticker, rec_asof) | ❌ **not populated** |
| `reports/learning_corpus_runner1.parquet` | `backend/replay/runner1_ingest.py:174` (market, ticker, rec_asof) | ✅ |
| `reports/macro_history.parquet` | `india/macro_intel/run.py:155` (market, asof) | ✅ · 2026-07-24 |
| `reports/factor_library_history.parquet` | `india/factor_library/run.py:37` | ✅ · 2026-07-21 · 10 KB |
| `reports/aegis_daily_v2_history.jsonl` | `scripts/aegis_daily_v2.py:46` (`_append_ledger`) | ✅ · 2026-07-24 · 152 KB |
| `reports/backend_validation_history.jsonl` | `india/backend_validation/run.py:61` via `pipeline.append_history` | ✅ · 2026-07-24 · 15 KB |
| `reports/portfolio_state_history.jsonl` | `india/portfolio_engine/run.py` via `backend/portfolio/state.py:21` | ✅ · 2026-07-24 · 3.8 KB |
| `usa/reports/recommendation_history.parquet` | `usa/research/recommendation_intelligence/run.py:141` | ✅ |
| `usa/reports/portfolio_history.parquet` | `usa/research/portfolio_engine/run.py:148` | ✅ |
| `usa/reports/risk_history.parquet` | `usa/research/risk_engine/run.py:162` | ✅ |
| `usa/reports/execution_history.parquet` | `usa/research/execution_simulator/run.py:200` | ❌ |
| `usa/reports/{learning,factor_library,macro,commodity_intelligence,currency_intelligence,bond_intelligence,macro_regime,sector_rotation}_history.parquet` | corresponding `usa/research/*/run.py` | ✅ |
| `usa/reports/backend_validation_history.jsonl` | `usa/backend_validation/run.py:54` | ✅ |
| `usa/reports/portfolio_state_history.jsonl` | `usa/research/portfolio_engine/run.py` via `backend/portfolio/state.py:20` | ✅ |
| `usa/reports/usa_daily_history.jsonl` | `usa/scripts/usa_daily.py:41` | ✅ |
| `features/quality_history.parquet` | `backend/feature_intelligence/quality.py:19` (`QUALITY_HISTORY_PATH`) | ✅ |
| `data/market_intelligence/derived/{calibration,champion,champion_challenger,trade_history_cache}_history.parquet` | `research/{confidence_calibration,champion_challenger}/*` | ✅ |

**All parquet history writers except `feature_intelligence/quality.py` and `runner1_ingest.py` route through the single `backend.persistence.append_snapshot_row` primitive** with `HISTORY_SCHEMA_VERSION = "1.0.0"`.

---

## 5. Engines inventory (across `backend/`, `india/`, `usa/research/`, `research/`, `ux/`)

Legend for **Daily?**: `aegis_daily_v2` = `scripts/aegis_daily_v2.py` step name · `usa_daily` = `usa/scripts/usa_daily.py` step name · `aegis-daily` = `.github/workflows/aegis-daily.yml` invocation.

### 5a. `backend/` (all libraries + one CLI)

| Engine | Daily invoker | `--asof`? | Sprint test |
|---|---|---|---|
| `backend/validation/` | via `india/backend_validation/run.py` (aegis_daily_v2) + USA | No | `backend/validation/tests/test_backend_validation.py` |
| `backend/canonical/` | library only | n/a | `test_sprint2.py` |
| `backend/market_intelligence/` | via `india/market_intelligence/run.py` + USA | No | `test_sprint2.py` |
| `backend/ai/` | library imported by every engine | n/a | multiple |
| `backend/feature_store/` | via `india/feature_store/run.py` + USA | No | `test_sprint25.py` |
| `backend/feature_intelligence/` | via `india/feature_intelligence/run.py` + USA | No | `test_sprint26.py` |
| `backend/model_registry/` | library | n/a | `test_sprint26.py` |
| `backend/promotion/` | library | n/a | `test_sprint26.py` |
| `backend/model_factory/` | via `india/model_factory/run.py` + USA | No | `test_sprint27.py` |
| `backend/recommendation/` | via `india/recommendation_intelligence/run.py` + USA | No | `test_sprint3.py` |
| `backend/risk/` | via `india/risk_engine/run.py` + USA | No | `test_sprint4.py` |
| `backend/portfolio/` | via `india/portfolio_engine/run.py` + USA | No | `test_sprint5.py` |
| `backend/learning/` | via `india/learning_engine/run.py` + USA | No | `test_sprint6.py` |
| `backend/execution/` | via `india/execution_simulator/run.py` + USA | No | `test_sprint7.py` |
| `backend/statistics/` | library used by `backend/benchmark/report.py` | n/a | `test_sprint7.py` |
| `backend/factor_library/` | via `india/factor_library/run.py` + USA | No | `test_sprint75.py` |
| `backend/macro_intel/` | via `india/macro_intel/run.py` + USA | No | `test_sprint65.py` |
| `backend/persistence/` | library used by every runner | n/a | `test_sprint75.py` |
| `backend/replay/` | CLI `python -m backend.replay backfill ...` (NOT in daily · tests only) | **YES (`--asof` per row + `--from`/`--to` CLI in `controller.py`)** | `test_sprint76.py` · `test_sprint77.py` · `test_sprint77_runner1.py` |
| `backend/benchmark/` | CLI only | n/a | `test_sprint78.py` |

### 5b. `india/` (every engine's `run.py`)

| Engine | aegis_daily_v2 step? | `--asof`? | Test |
|---|---|---|---|
| `india/backend_validation/run.py` | `backend_validation` | No | `test_backend_validation.py` |
| `india/macro_intel/run.py` | `macro_intel` | No | `test_sprint65.py` |
| `india/factor_library/run.py` | `factor_library` | No | `test_sprint75.py` |
| `india/market_intelligence/run.py` | `market_intelligence` | No | `test_sprint2.py` |
| `india/feature_store/run.py` | `feature_store` | No | `test_sprint25.py` |
| `india/feature_intelligence/run.py` | `feature_intelligence` | No | `test_sprint26.py` |
| `india/model_factory/run.py` | `model_factory` | No | `test_sprint27.py` |
| `india/recommendation_intelligence/run.py` | `recommendation_intelligence` | No | `test_sprint3.py` |
| `india/risk_engine/run.py` | `risk_engine` | No | `test_sprint4.py` |
| `india/portfolio_engine/run.py` | `portfolio_engine` | No | `test_sprint5.py` |
| `india/learning_engine/run.py` | `learning_engine` | No | `test_sprint6.py` |
| `india/execution_simulator/run.py` | `execution_simulator` | No | `test_sprint7.py` |
| `india/recommendation_generator.py` | `.github/workflows/aegis-daily.yml` (Runner 1) | No | `nexaquant/tests/test_regression.py` + `test_ops001i_telegram_format.py` |
| `india/monitoring/MON001_Forward_Validation/` | `.github/workflows/mon001-daily.yml` | n/a | `test_mon001_framework.py` + `test_mon001_ops.py` + `test_regression.py` fingerprint |
| `india/rolling_recommendations.py` | not orchestrated | No | none |
| `india/ai_lab/LAB*` (LAB006–LAB010) | manual only | mixed | `india/ai_lab/tests/test_lab_framework.py` + `test_regression.py` |

### 5c. `usa/research/` (33 engines)

Every engine invoked via `usa/scripts/usa_daily.py` step; all lack `--asof`. Tests where applicable route to `backend/tests/test_sprint*.py` per Sprint 2..7.8 numbering. Additional USA-specific engines with no Sprint-test counterpart:

`usa/scripts/build_universe.py` · `refresh_market_data.py` · `usa/research/{fundamentals,news,earnings,insider,etf_flows,macro,corporate_actions,sec_13f}/run.py` (Sprint 1B ingestion) · `usa/research/{recommendations,validation,risk,fusion,price_context,institutional_memory,winner_genome,decision_attribution,benchmark,morning_report}/run.py` (Runner-1-shape mirrors).

### 5d. `research/` (legacy · SEALED — do not modify)

| Engine | aegis_daily_v2 step | Status |
|---|---|---|
| `research/adaptive_rec_v2/{run,run_fusion}.py` | `adaptive_rec_v2` · `fusion` | wired · sealed |
| `research/validation_v2/{run,run_stock_history,run_price_context}.py` | `validation_v2` · `stock_validation` · `price_context` | wired |
| `research/risk_capital_v2/run.py` | `risk_capital_v2` | wired |
| `research/recommendation_dna/run_feedback.py` + `run_winner_genome.py` | `dna_feedback` · `winner_genome` | wired |
| `research/recommendation_dna/run.py` (base) | **NOT wired** — declared `requires: reports/recommendation_dna.parquet` but nothing daily-produces it | ⚠️ |
| `research/knowledge_graph/run.py` | `knowledge_graph` | wired |
| `research/decision_center/run.py` | `decision_center` | wired |
| `research/institutional_memory/run.py` | `institutional_memory` | wired |
| `research/decision_attribution/run.py` | `decision_attribution` | wired |
| `research/benchmark/run.py` | `benchmark` | wired |
| `research/morning_report/run.py` | `morning_report` (+ aegis-ci smoke) | wired |
| `research/recommendations/run.py` | **NOT wired** — deprecated per `docs/AEGIS_STAGE0_COMPLETION.md:67`; still emits `reports/recommendations.json` when run manually. **Keystone gap · see risk #1.** | ⚠️ deprecated |
| `research/adaptive_learning/run.py` | **NOT wired** | orphan |
| `research/backtesting/run.py` | **NOT wired** | orphan |
| `research/champion_challenger/run.py` | **NOT wired** — writes `champion_strategy.json` which is REQUIRED by `scripts/aegis_ops_check.py:49` | ⚠️ risk |
| `research/company_intelligence/run.py` | **NOT wired** | orphan |
| `research/confidence_calibration/run.py` | **NOT wired** — writes `confidence_calibration.parquet` consumed by `risk_capital_v2` + `fusion_engine` (silent fallback today) | ⚠️ risk |
| `research/global_intelligence/run.py` | **NOT wired** — writes `global_context.json` REQUIRED by ops_check + risk_capital_v2 | ⚠️ risk |
| `research/industry_intelligence/run.py` | **NOT wired** | orphan |
| `research/portfolio_construction/run.py` | **NOT wired** | orphan |
| `research/portfolio_monitor/run.py` | **NOT wired** | orphan |
| `research/research_assistant/run.py` | **NOT wired** | orphan |
| `research/sector_intelligence/run.py` | **NOT wired** | orphan |
| `research/strategy_doctor/run.py` | **NOT wired** | orphan |
| `research/RISK001-A/` + `research/*_probe.py` + `research/*_walkforward.py` etc. | probes / research | not for production |

### 5e. `ux/`

| Engine | Status |
|---|---|
| `ux/dashboard/run.py` | NOT orchestrated · writes `dashboard_{layout,widgets,routes,theme,config}.json` |
| `ux/telegram/run.py` | NOT orchestrated · writes `telegram_{templates,layouts,commands,notification_rules,ui_config}.json` — but `scripts/telegram_send_ux030.py` reads live `reports/*.json` via aggregator, not these config files |

### 5f. `nexaquant/`

`nexaquant/ops/*` daemon/service scaffolding · not orchestrated · governance & sealed-fingerprint regression only.

**Verified via `Grep '--asof'`:** only hits are `backend/replay/controller.py`, `backend/replay/types.py`, and two docs. **No `run.py` script in the repository accepts `--asof`.** Every engine reads "latest" from Feature Store or current `reports/*.json` — cross-cutting risk #2.

---

## 6. Orchestrators

### 6a. `.github/workflows/aegis-daily.yml` — INDIA DAILY (Runner 1 pipeline)

15 steps · guard → deps → refresh → freshness → **Run AEGIS engine (Runner 1)** → verify aegis_today.csv → DB/scorecard/ops → sheets → **`scripts/aegis_daily_v2.py --continue`** (see 6b) → Telegram health → Telegram legacy → Telegram UX030 → upload → commit.

### 6b. `scripts/aegis_daily_v2.py` — Phase 2 orchestrator (28 steps)

`ingest_fii_dii → ingest_news_sentiment → ingest_fundamentals → ingest_corporate_actions → backend_validation → macro_intel → factor_library → market_intelligence → feature_store → feature_intelligence → model_factory → recommendation_intelligence (Runner 2) → risk_engine → portfolio_engine → learning_engine → execution_simulator → adaptive_rec_v2 → validation_v2 → risk_capital_v2 → dna_feedback → knowledge_graph → fusion → stock_validation → price_context → decision_center → institutional_memory → winner_genome → decision_attribution → benchmark → morning_report → ops_check → telegram`

Per-step outputs in `produces` list · ledger appended to `reports/aegis_daily_v2_history.jsonl`.

### 6c. `.github/workflows/mon001-daily.yml`

1 step: `python -m india.monitoring.MON001_Forward_Validation.ops.daily_runner` → `india/monitoring/MON001_Forward_Validation/{ledger,reports}/*`.

### 6d. `.github/workflows/aegis-usa.yml` → `usa/scripts/usa_daily.py` (33 steps)

`build_universe → refresh_market_data → ingest_{fundamentals,news,earnings,insider,etf_flows,macro,corporate_actions,sec_13f} → backend_validation → macro_intel → factor_library → market_intelligence → feature_store → feature_intelligence → model_factory → recommendation_intelligence (Runner 2) → risk_engine → portfolio_engine → learning_engine → execution_simulator → recommendations (Runner-1-analog) → validation → risk → fusion → price_context → institutional_memory → winner_genome → decision_attribution → benchmark → morning_report → ops_check → telegram → comparison_report`

### 6e. `.github/workflows/aegis-ci.yml`

`aegis_ops_check.py --ci` + all `backend/tests/test_sprint*.py` + `test_backend_validation.py` + `test_telegram_notify_fallback.py` + SPA JS parse + morning report smoke.

### 6f. `.github/workflows/eng001-regression.yml`

`nexaquant/tests/test_{ci_discipline,lib,regression,governance}.py` + MON001 health-check.

---

## 7. Duplicate / overlapping logic

| Pair | Overlap |
|---|---|
| `india/recommendation_generator.py` + `research/adaptive_rec_v2/run.py` + `research/recommendations/run.py` (deprecated) + `india/recommendation_intelligence/run.py` + `usa/research/recommendations/run.py` | **Five recommendation-generating scripts.** `docs/AEGIS_STAGE0_COMPLETION.md` marks `research/recommendations/run.py` deprecated · `usa/research/recommendations/run.py` "actively wired"; India Runner 1 remains source of Telegram truth. |
| `research/adaptive_rec_v2/run_fusion.py` + `usa/research/fusion/run.py` | Two fusion engines · equivalent 10-dimension logic · one per market. |
| `india/telegram_notify.py` + `scripts/telegram_send_ux030.py` + `scripts/telegram_send_with_retry.py` + `scripts/telegram_health_check.py` + `usa/scripts/telegram_send.py` + `nexaquant/ops/notify/telegram.py` | **Six Telegram senders.** aegis-daily runs BOTH legacy AND UX030 in same job. Cross-cutting risk #4. |
| `scripts/aegis_ops_check.py` + `usa/scripts/usa_ops_check.py` + `india/ops_check.py` + `scripts/aegis_health_check.py` + `scripts/telegram_health_check.py` + `scripts/check_data_freshness.py` | **Six ops/health check scripts** with overlapping artifact + freshness + fingerprint checks. |
| `backend/persistence/history_writer.py::append_snapshot_row` (canonical) + `backend/replay/runner1_ingest.py` (bespoke) + `india/backend_validation/run.py::append_history` (JSONL) + `india/portfolio_engine/run.py` uses BOTH `append_state_history` (JSONL) AND `append_snapshot_row` (parquet) | **Three history-writing paradigms** coexist. Cross-cutting risk #3. |
| `research/benchmark/run.py` + `usa/research/benchmark/run.py` + `backend/benchmark/report.py` | **Three benchmark producers** for same conceptual metric family. |
| `research/validation_v2/run.py` + `usa/research/validation/run.py` + `india/backend_validation/run.py` + `usa/backend_validation/run.py` + `backend/validation/*` + `research/{final_validation,validation_runner}.py` | Multiple validation entry-points; not all same layer (data-foundation vs strategy). |
| `india/risk_engine/run.py` (Sprint 4 · Runner 2) + `research/risk_capital_v2/run.py` (Runner 1 · v2) + `usa/research/risk_engine/run.py` (Runner 2 · USA) + `usa/research/risk/run.py` (USA · Runner-1-shape) | **Four risk-sizing engines.** |
| `research/institutional_memory/run.py` + `usa/research/institutional_memory/run.py` — writes per-market `recommendation_history.json`, `recommendation_lifecycle.json`, `missed_opportunities.json` — separate from persistence-layer `recommendation_history.parquet` writer | `.json` vs `.parquet` variants overlap in per-ticker-lifecycle scope with different keys. |

---

## 8. Sealed files (confirmed on disk)

| Sealed asset | Path |
|---|---|
| `india/telegram_notify.py` — OPS001-I message contract | ✅ present · 950-line header |
| `research/adaptive_rec_v2/` (full package) | ✅ · `run.py`, `run_fusion.py`, `compute/{engine,fusion_engine}.py`, `publish/{bundle,fusion_bundle}.py`, `lib/{features,model,metrics,reliability,dimensions,fusion,conflicts}.py`, `tests/{test_smoke,test_fusion}.py` |
| `research/risk_capital_v2/` (full package) | ✅ · `run.py`, `compute/engine.py`, `lib/`, `publish/`, `tests/` |
| `india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json` | ✅ present |
| `india/monitoring/MON001_Forward_Validation/sealed_baseline_fingerprint.txt` | Referenced by `scripts/aegis_ops_check.py:190` — returns "checked=False" when absent |
| MON001 supporting files | ✅ all present in `india/monitoring/MON001_Forward_Validation/` (`baseline_envelope.py`, `broker_layer.py`, `fingerprint.py`, `forward_ledger.py`, `monitor.py`, `preregistration.md`, `report.py`, `run_mon001.py`, `mon001.yaml`, `test_mon001_framework.py`, `test_mon001_ops.py`, `launchers/`, `ledger/`, `ops/`, `reports/` w/ 10+ daily diagnostics) |
| `nexaquant/lib/paths.py` · `__init__.py` — sealed constants for `cumulative_strategy_search` invariant | ✅ referenced in `nexaquant/tests/test_regression.py` |
| `scripts/telegram_send_with_retry.py` — sealed retry wrapper | ✅ |

Fingerprint values referenced in docs:
- **Current v2:** `e4c070673568c52d419dea1e70060d2319b4622dc5268634ecd848327840a8bf` (per `docs/OPS001-M_FIRST_PRODUCTION_AUDIT.md:281`)
- Re-sealed 2026-07-15: `64e74483d9bd0444…` · original v1 `064d8b04eb85b819…` superseded (`docs/MON001_CERTIFICATION.md:40`)

---

## 9. Disconnected engines (no daily invocation)

| Engine | Consequence |
|---|---|
| `research/recommendations/run.py` | ⚠️ DEPRECATED — produces `reports/recommendations.json` that ~30 engines depend on; **no orchestrator regenerates it.** |
| `research/champion_challenger/run.py` | ⚠️ Writes `champion_strategy.json` which is **REQUIRED** per `scripts/aegis_ops_check.py:49` — ops-check flags stale/missing on fresh env |
| `research/confidence_calibration/run.py` | ⚠️ Writes `confidence_calibration.parquet` consumed by `risk_capital_v2` + `fusion_engine`; both fall back to raw confidence today |
| `research/global_intelligence/run.py` | ⚠️ Writes `global_context.json` **REQUIRED** by `aegis_ops_check.py:48` AND `risk_capital_v2::_load_regime` |
| `research/industry_intelligence/run.py` | Orphan — no reader found in `.py` files |
| `research/sector_intelligence/run.py` | Orphan — referenced only in dashboard widget config |
| `research/company_intelligence/run.py` | Consumed by deprecated `research/recommendations/*` and `research/recommendation_dna/*` |
| `research/adaptive_learning/run.py` | Only consumer: `ux/dashboard/lib/widgets.py` |
| `research/backtesting/run.py` | Dashboard-widget only consumers |
| `research/portfolio_construction/run.py` | Only deprecated DEV023 reads it |
| `research/portfolio_monitor/run.py` | Widget-config only |
| `research/research_assistant/run.py` | Widget-config only |
| `research/strategy_doctor/run.py` | Widget-config only |
| `research/recommendation_dna/run.py` (base) | ⚠️ Base DNA — its output `recommendation_dna.parquet` is declared `requires` by `run_feedback.py` which IS wired · nothing daily-produces the parquet |
| `ux/dashboard/run.py` · `ux/telegram/run.py` | SPA + config renderers; not orchestrated · SPA reads at page-load |
| `india/rolling_recommendations.py` · `india/evidence/*` (37 files) | Research/lab probes |
| `research/RISK001-A/` · `research/*_probe.py` etc. | Research probes |

---

## 10. Reports produced but never consumed

Files declared in `produces` lists but with no reader (`open("reports/…")` / `pd.read_parquet` / `_load_json`) in `.py`:

- **Knowledge graph orphans:** `entity_network.json`, `company_network.json`, `sector_network.json`, `relationship_matrix.json`, `graph_timeline.json`, `graph_statistics.json`, `community_clusters.json`, `influence_propagation.json`, `recommendation_paths.json` — all loaded into `fusion_engine._load_context` ctx dict but not consumed downstream (grep-verified)
- **Research widget-only:** `pattern_discovery.json`, `success_patterns.json`, `failure_patterns.json`, `root_cause_analysis.json`, `self_improvement.json`, `improvement_plan.json`, `improvement_suggestions.json`, `holdings_demo.json`, `regime_comparison.json`
- **DNA widget-only:** `recommendation_versions.json`, `recommendation_statistics.json`, `recommendation_accuracy.json`
- **Research assistant/champion widget-only:** `company_report.json`, `comparison_report.json`, `head_to_head_matrix.json`
- **Portfolio construction/monitor widget-only:** `allocation_report.json`, `rebalance_plan.json`, `rebalance_report.json`, `portfolio_report.json`, `portfolio_health.json`, `portfolio_leaderboard.json`, `portfolio_monitor.json/.parquet`
- **UX metadata:** `telegram_examples.md`, `dashboard_{layout,widgets,routes,theme,config}.json`, `telegram_{templates,layouts,commands,notification_rules,ui_config}.json`
- **Calibration/drift:** `calibration_metrics.json`, `reliability_diagram.json`, `confidence_bias.json`, `drift_report.json`, `challenger_scoreboard.json`
- **Replay:** `backfill_summary.json`, `learning_backfill_summary.json`
- **Uncertain:** `alerts.json` (unclear producer)

**Substantive downstream orphans that will block ops-check** if the disconnected producers aren't manually kicked: `champion_strategy.json` · `global_context.json` · `confidence_calibration.json` (silent fallback consumers today).

---

## Cross-Cutting Risks (six severe findings)

1. **`reports/recommendations.json` is a keystone artifact with no daily producer.** ~30 modules read it. Current mtime 2026-07-17 vs other reports 2026-07-24 — the gap is already actively causing stale downstream data (this is the same root cause behind the "IPCALAB repeats daily" Telegram incident of 2026-07-24).
2. **Zero `run.py` scripts accept `--asof`.** Only `backend/replay/controller.py` does. Phase 3 replay/walk-forward on live engines is currently impossible without invasive changes to every runner. Sprint 7.7 replay is the ONLY end-to-end replay path today; even that runs via headless engine drivers (`backend/replay/engine_drivers.py`) bypassing the runners.
3. **Two parallel history schemas** coexist (Runner 1 bespoke `_runner1.parquet` writer, Runner 2 canonical `append_snapshot_row`), joined only in `backend/replay/walk_forward.py::run_walk_forward_runner1`.
4. **Six Telegram senders** in the daily path with subtly different responsibilities — sealed contract lives only in `india/telegram_notify.py`.
5. **`research/recommendation_dna/run.py`** (DNA base) is not orchestrated but `run_feedback.py` (`requires: reports/recommendation_dna.parquet`) is — the parquet is produced offline.
6. **Ops check requires `champion_strategy.json`** produced only by `research/champion_challenger/run.py` — a disconnected engine.

---

**End of Sprint A1 Repository Audit · LOCKED 2026-07-24**
