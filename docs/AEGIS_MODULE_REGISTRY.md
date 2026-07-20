# AEGIS Module Registry · Every module classified with runtime status
**Stage 0.5 deliverable · Runtime-verified, not file-presence based**

Classifications:
- **PRODUCTION_DAILY** — invoked in a scheduled orchestrator
- **PRODUCTION_MANUAL** — invoked only through manual entry points
- **DORMANT_TEMPLATE** — installable, never actually deployed
- **FROZEN_ONE_TIME** — ran exactly once (evidence: git log on artifact), never since
- **UNIT_TEST_ONLY** — code exercised only in CI tests
- **NEVER_INVOKED** — no caller anywhere in repo
- **RESEARCH_EXPERIMENT** — one-off research probe, artifact from single date
- **INDEPENDENT** — unrelated to AEGIS pipeline

---

## `scripts/` (repo root)

| File | Classification | Caller |
|---|---|---|
| `scripts/aegis_daily_v2.py` | **PRODUCTION_DAILY** | `aegis-daily.yml:139`, `aegis-pipeline.service:28`, `aegis-windows-task.ps1:24` |
| `scripts/aegis_ops_check.py` | **PRODUCTION_DAILY** | Step 15 of `aegis_daily_v2.py`; also `aegis-ci.yml:46` |
| `scripts/aegis_health_check.py` | **PRODUCTION_MANUAL** | Not scheduled; Docker override option |
| `scripts/aegis_profile.py` | **PRODUCTION_MANUAL** | Standalone profiler |
| `scripts/check_data_freshness.py` | **PRODUCTION_DAILY** | `aegis-daily.yml` (2 invocations) |
| `scripts/e2e_test.py` | **UNIT_TEST_ONLY** | Manual invocation |
| `scripts/nexaquant_daemon.py` | **DORMANT_TEMPLATE** | Referenced by systemd unit, no live evidence |
| `scripts/nexaquant_service.py` | **DORMANT_TEMPLATE** | Same |
| `scripts/run_pipeline_local.py` | **PRODUCTION_MANUAL** | No scheduler references |
| `scripts/telegram_health_check.py` | **PRODUCTION_DAILY** | `aegis-daily.yml:148` |
| `scripts/telegram_send_ux030.py` | **PRODUCTION_DAILY** | Step 16 of `aegis_daily_v2.py`; also `aegis-daily.yml:168` |
| `scripts/telegram_send_with_retry.py` | **PRODUCTION_DAILY** | `aegis-daily.yml:156` |

## `research/` engine modules

### Wired into `scripts/aegis_daily_v2.py` (production)

| Module | Steps invoked | Classification |
|---|---|---|
| `research/adaptive_rec_v2/` | `run.py` (step 1) + `run_fusion.py` (step 6) | **PRODUCTION_DAILY** |
| `research/validation_v2/` | `run.py` (2) + `run_stock_history.py` (7) + `run_price_context.py` (8) | **PRODUCTION_DAILY** |
| `research/risk_capital_v2/` | `run.py` (3) | **PRODUCTION_DAILY** |
| `research/recommendation_dna/` | `run_feedback.py` (4) + `run_winner_genome.py` (11) — **but NOT `run.py`** | **PRODUCTION_DAILY** for feedback/WG; **NEVER_INVOKED** for `run.py` (the one producing `recommendation_dna.parquet`) |
| `research/knowledge_graph/` | `run.py` (5) | **PRODUCTION_DAILY** |
| `research/decision_center/` | `run.py` (9) | **PRODUCTION_DAILY** |
| `research/institutional_memory/` | `run.py` (10) | **PRODUCTION_DAILY** |
| `research/decision_attribution/` | `run.py` (12) | **PRODUCTION_DAILY** |
| `research/benchmark/` | `run.py` (13) | **PRODUCTION_DAILY** |
| `research/morning_report/` | `run.py` (14) | **PRODUCTION_DAILY** |

### NOT wired — all FROZEN_ONE_TIME (dated 2026-07-17, unchanged since)

| Module | Artifact | Last git touch |
|---|---|---|
| `research/global_intelligence/` (DEV017) | `reports/global_context.json` | `9a53072` · 2026-07-17 14:37:51 |
| `research/sector_intelligence/` (DEV018) | `reports/sector_context.json` | `d128e2a` · 2026-07-17 14:48:59 |
| `research/industry_intelligence/` (DEV019) | `reports/industry_context.json` | `ae89837` · 2026-07-17 15:04:42 |
| `research/company_intelligence/` (DEV020) | `reports/company_context.json` | `e711561` · 2026-07-17 15:47:09 |
| `research/champion_challenger/` (DEV030) | `reports/champion_strategy.json` + `challenger_scoreboard.json` | `3dac403` · 2026-07-17 18:03:35 (test-only invocation via `e2e_test.py:108`) |
| `research/confidence_calibration/` (DEV029) | `reports/confidence_calibration.json` | `52b2d55` · 2026-07-17 17:39:25 |
| `research/portfolio_construction/` (DEV022) | `reports/portfolio.json` | `28ececa` · 2026-07-17 16:22:22 |
| `research/portfolio_monitor/` (DEV024) | `reports/portfolio_monitor.json` | `50a8dfa` · 2026-07-17 16:49:25 |
| `research/strategy_doctor/` (DEV027) | `reports/strategy_doctor.json` | `0e955b1` · 2026-07-17 17:22:35 |
| `research/adaptive_learning/` (DEV025+026) | `reports/learning.parquet` + related | `59b2b31` · 2026-07-17 17:06:23 |
| `research/backtesting/` | (none live) | **NEVER_INVOKED** |
| `research/recommendations/` (root) | (none) | **NEVER_INVOKED** — do not confuse with `usa/research/recommendations/` |
| `research/research_assistant/` | (none live) | **NEVER_INVOKED** |
| `research/recommendation_dna/run.py` (as opposed to the wired `run_feedback.py` / `run_winner_genome.py`) | `reports/recommendation_dna.parquet` | Same commit `0e955b1`, **NEVER_INVOKED** since |
| `research/RISK001-A/` | (sealed exit-policy study) | **RESEARCH_EXPERIMENT** |

### Standalone probes (top-level `.py` files in `research/`)

36 files — all **RESEARCH_EXPERIMENT** classification. Examples: `breakout_test.py`, `hmm_regime_probe.py`, `deep_walkforward.py`, `edge_probe.py`, `mtf_edge_probe.py`, `long_short_probe.py`, `meta_label_probe.py`, `smc_probe.py`, etc. Not part of daily production.

---

## `india/` (50 top-level `.py` files)

### Called by `aegis-daily.yml` (production daily)

| File | Invocation |
|---|---|
| `india/refresh_data.py` | `aegis-daily.yml` (yfinance pull) |
| `india/recommendation_generator.py` | `aegis-daily.yml:91` (fail-fast) |
| `india/recommendation_db.py` | `aegis-daily.yml` |
| `india/scorecard.py` | `aegis-daily.yml` |
| `india/ops_check.py` | `aegis-daily.yml` (masked) |
| `india/sheets_sync.py` | `aegis-daily.yml` |
| `india/telegram_notify.py` | Via `scripts/telegram_send_with_retry.py:156` |

### Called by `run_daily.bat` → `india/daily_run.py` (MANUAL only)

| File | Classification |
|---|---|
| `india/daily_run.py` | **PRODUCTION_MANUAL** |
| `india/broker_angelone.py` | **PRODUCTION_MANUAL** |
| `india/fii_dii.py` | **PRODUCTION_MANUAL** |
| `india/news_sentiment.py` | **PRODUCTION_MANUAL** |
| `india/run_arjuna.py` | **PRODUCTION_MANUAL** |
| `india/fundamentals_nse.py` | **NEVER_INVOKED** — zero callers, not even from `daily_run.py` |

### Imported as libraries by production code

| File | Purpose |
|---|---|
| `india/technical_factors.py`, `india/feature_engine.py`, `india/labels.py` | Feature engineering library |
| `india/dataset.py`, `india/data_nse.py`, `india/data_layer_gate.py` | Data access |
| `india/config.py` | Config (sets `MODELS_FROZEN_UNTIL_DATA_ARRIVES = True`) |
| `india/confidence_engine.py` | Live regime engine (via `current_regime()` — the "global" regime) |
| `india/risk_forecast.py`, `india/risk_tiers.py` | Risk framework |
| `india/global_risk.py` | Global risk features |
| `india/dynamic_engine.py`, `india/dynamic_policy.py` | Dynamic policy |
| `india/probability_surface.py` | Probability modeling |
| `india/rolling_recommendations.py` | Rolling rec logic |
| `india/recommendation_registry.py` | Recommendation DB |
| `india/arjuna_v2.py`, `india/arjuna_strategy.py`, `india/arjuna_os.py` | Arjuna strategy family (imported by `recommendation_generator.py` chain) |
| `india/moonshot.py` | Moonshot strategy |
| `india/goal_engine.py`, `india/capital_ladder.py`, `india/horizon_matrix.py`, `india/exit_reasons.py`, `india/sectors.py`, `india/universe.py`, `india/equity_engine.py`, `india/validation.py`, `india/probability_surface.py`, `india/monthly_report.py`, `india/monthly_snapshot.py`, `india/backpaper.py`, `india/aegis_engine.py`, `india/aegis_dashboard.py`, `india/results_report.py`, `india/ai_reopen.py` | Various — need per-file audit for classification |

### Dormant-by-design (rejected per evidence)

| File | Why dormant | Evidence |
|---|---|---|
| `india/regime_hmm.py` | HMM tested and LOST (1.06 vs 1.64 Sharpe) — rejected in production | `docs/ARJUNA_ALPHA_MASTER.md:48`. Live `CONFIG.regime = "global"` in `india/recommendation_generator.py:44` |

---

## `usa/`

| Path | Classification |
|---|---|
| `usa/scripts/usa_daily.py` | **PRODUCTION_DAILY** (`aegis-usa.yml:34`) |
| `usa/scripts/build_universe.py` | **PRODUCTION_DAILY** (step 1 of `usa_daily.py`) |
| `usa/scripts/refresh_market_data.py` | **PRODUCTION_DAILY** (step 2) |
| `usa/scripts/usa_ops_check.py` | **PRODUCTION_DAILY** (step 13) |
| `usa/scripts/telegram_send.py` | **PRODUCTION_DAILY** (optional, step 14) |
| `usa/research/recommendations/run.py` | **PRODUCTION_DAILY** (step 3) |
| `usa/research/validation/run.py` | **PRODUCTION_DAILY** (step 4) |
| `usa/research/risk/run.py` | **PRODUCTION_DAILY** (step 5) |
| `usa/research/fusion/run.py` | **PRODUCTION_DAILY** (step 6) |
| `usa/research/price_context/run.py` | **PRODUCTION_DAILY** (step 7) |
| `usa/research/institutional_memory/run.py` | **PRODUCTION_DAILY** (step 8) |
| `usa/research/winner_genome/run.py` | **PRODUCTION_DAILY** (step 9) |
| `usa/research/decision_attribution/run.py` | **PRODUCTION_DAILY** (step 10) |
| `usa/research/benchmark/run.py` | **PRODUCTION_DAILY** (step 11) |
| `usa/research/morning_report/run.py` | **PRODUCTION_DAILY** (step 12) |
| `usa/research/fundamentals/run.py` | **NEVER_INVOKED** — module exists but not in `usa_daily.py` (grep confirms 0 matches for "fundamentals" in orchestrator) |
| `usa/dashboard/frontend/serve.py` | **PRODUCTION_MANUAL** (dashboard viewer) |
| `usa/telegram/lib/renderer.py` | Library (used by `telegram_send.py`) |

## `nexaquant/`

| Path | Classification |
|---|---|
| `nexaquant/ops/daemon.py` (`NexaQuantDaemon`) | **DORMANT_TEMPLATE** — never actually run |
| `nexaquant/ops/pipeline.py` | Library (called by daemon when it runs) |
| `nexaquant/ops/cli.py` | Manual CLI |
| `nexaquant/ops/monitoring.py` | Library |
| `nexaquant/ops/notify/*.py` (14 files: base, dashboard, discord, email, file, health, history, manager, retry_queue, routing, slack, telegram, templates, webhook) | Full notify framework — code exists, unit-tested, never fires in production because daemon is dormant |
| `nexaquant/lib/*.py` | Utility libraries |
| `nexaquant/tests/*.py` | **UNIT_TEST_ONLY** — run by `eng001-regression.yml` weekly + on push/PR |

## `ux/`

| Path | Classification |
|---|---|
| `ux/dashboard/frontend/index.html` | **PRODUCTION_MANUAL** (India SPA) |
| `ux/dashboard/frontend/serve.py` | **PRODUCTION_MANUAL** (static server, port 8765) |
| `ux/dashboard/lib/*.py` | Library helpers (widgets, aggregator) |
| `ux/dashboard/publish/bundle.py` | Produces `dashboard_config.json` etc. — **effectively NEVER_INVOKED** in current workflows; when it did run, its outputs are orphaned (SPA doesn't read them) |
| `ux/telegram/lib/renderer.py` | Library (used by `telegram_send_ux030.py`) |
| `ux/telegram/lib/aggregator.py` | Library (loads all reports for renderer) |

## `run_nexaquant.py` + `config_loader.py` + `strategy/` + `backtest/`

**INDEPENDENT** — these are the FOREX/BTC/GOLD MT5 bot stack. Not part of AEGIS India/USA. Only entry: `python run_nexaquant.py` (manual).

---

## Aggregate counts

| Classification | Count of significant modules |
|---|---|
| PRODUCTION_DAILY | ~25 (India v2 pipeline steps + USA pipeline steps + workflow helpers) |
| PRODUCTION_MANUAL | ~10 (india/daily_run.py chain + local runners + dashboard) |
| FROZEN_ONE_TIME | 11 (DEV017-020, DEV022, 024, 025+26, 027, 028, 029, 030) |
| DORMANT_TEMPLATE | 1 (nexaquant daemon) + 5 deploy templates |
| NEVER_INVOKED | ~8 (research/{backtesting,recommendations,research_assistant,recommendation_dna}/run.py + india/fundamentals_nse.py + usa/research/fundamentals + dashboard_config.json producer) |
| UNIT_TEST_ONLY | nexaquant/tests + scripts/e2e_test.py |
| RESEARCH_EXPERIMENT | ~40 (research/*.py top-level probes + LAB006-010) |
| INDEPENDENT | 1 (run_nexaquant.py + config_loader.py + strategy/ + backtest/) |
