# AEGIS Production vs Research · Runtime-verified split
**Stage 0.5 deliverable · Every significant module classified**

Definitions:
- **PRODUCTION** — invoked by a scheduled orchestrator, runs today
- **PRODUCTION_MANUAL** — reachable only through manual entry points, runs when operator triggers
- **RESEARCH** — one-off experiment, artifact from single date, not on the critical path
- **PROTOTYPE** — has code but never demonstrably run (README-only, or code without artifacts)
- **DEPRECATED** — superseded by a newer version, present but unused
- **ARCHIVED** — historical snapshot preserved for audit
- **DORMANT** — full implementation exists (systemd/task/daemon-ready) but never actually run in this environment
- **INDEPENDENT** — unrelated to AEGIS India/USA

---

## Production (scheduled, live)

### India — invoked daily by `aegis-daily.yml`

- `india/refresh_data.py`
- `india/recommendation_generator.py`
- `india/recommendation_db.py`
- `india/scorecard.py`
- `india/ops_check.py`
- `india/sheets_sync.py`
- `india/telegram_notify.py` (via retry wrapper)
- `scripts/aegis_daily_v2.py`
- All 15 v2 engines (`research/adaptive_rec_v2/`, `validation_v2/`, `risk_capital_v2/`, `recommendation_dna/{run_feedback, run_winner_genome}`, `knowledge_graph/`, `decision_center/`, `institutional_memory/`, `decision_attribution/`, `benchmark/`, `morning_report/`)
- `scripts/aegis_ops_check.py`
- `scripts/aegis_health_check.py` (Docker override)
- `scripts/telegram_health_check.py`
- `scripts/telegram_send_with_retry.py`
- `scripts/telegram_send_ux030.py`
- `scripts/check_data_freshness.py`

### India — invoked daily by `mon001-daily.yml`

- `india/monitoring/MON001_Forward_Validation/ops/daily_runner.py` (sealed)

### USA — invoked daily by `aegis-usa.yml`

- `usa/scripts/usa_daily.py`
- `usa/scripts/build_universe.py`
- `usa/scripts/refresh_market_data.py`
- `usa/scripts/usa_ops_check.py`
- `usa/scripts/telegram_send.py`
- `usa/research/{recommendations, validation, risk, fusion, price_context, institutional_memory, winner_genome, decision_attribution, benchmark, morning_report}/run.py`
- `compare/build_comparison.py`

### CI — invoked on push / weekly

- `nexaquant/tests/` (all suites, via `eng001-regression.yml`)
- `scripts/aegis_ops_check.py` (via `aegis-ci.yml`)

---

## Production_Manual (code exists, unscheduled)

### The `india/daily_run.py` chain

- `india/daily_run.py` (only caller: `run_daily.bat`)
- `india/broker_angelone.py --pull`
- `india/fii_dii.py`
- `india/news_sentiment.py`
- `india/run_arjuna.py`

### Standalone runners

- `scripts/run_pipeline_local.py` (executes `nexaquant/ops/pipelines/aegis_daily.yaml` locally)
- `scripts/e2e_test.py` (test harness)
- `scripts/aegis_profile.py`
- `usa/dashboard/frontend/serve.py`
- `ux/dashboard/frontend/serve.py`

### Ingestion (unscheduled)

- `india/fundamentals_nse.py` (no caller anywhere)

---

## Research (one-off experiments, off critical path)

### `research/` top-level probes (36 files, all dated 2026-07-13 approximately)

`breakout_test.py`, `confidence_sizing_test.py`, `cross_sectional_test.py`, `deep_walkforward.py`, `edge_probe.py`, `exit_probe.py`, `expansion_test.py`, `final_validation.py`, `hmm_regime_probe.py`, `long_short_probe.py`, `long_short_walkforward.py`, `lot_size_sim.py`, `macro_gate_test.py`, `mean_reversion_test.py`, `meta_label_probe.py`, `mtf_edge_probe.py`, `multi_asset_portfolio.py`, `pair_compare.py`, `playbook_backtest.py`, `portfolio_results.py`, `pyramid_test.py`, `regime_gated_probe.py`, `sizing_overlay_test.py`, `smc_probe.py`, `streak_test.py`, `three_year_results.py`, `timeframe_compare.py`, `trade_report.py`, `tsm_test.py`, `vol_target_test.py`, `walk_forward_yearly.py`, `validation_runner.py`

Plus CSV/parquet outputs from these probes (`equity_curves.csv`, `policy_comparison.csv`, `position_level_analysis.parquet`, `RISK001-A_RESULTS.md`).

### AI Labs (2026-07-13 batch)

- `india/ai_lab/LAB006_Exit_Strategy/`
- `india/ai_lab/LAB007_Dynamic_Exposure/`
- `india/ai_lab/LAB008_Horizon_Calibration/`
- `india/ai_lab/LAB009_Horizon_Phase_Recalibration/`
- `india/ai_lab/LAB010_H84_Robustness_Validation/`

### Sealed research

- `research/RISK001-A/` (exit-policy study, sealed)

---

## Prototype (README-only or design-only)

- `india/ai_lab/LAB001_Earnings/` (README only)
- `india/ai_lab/LAB002_Fundamentals/` (README only)
- `india/ai_lab/LAB003_Events/` (README only)
- `india/ai_lab/LAB004_Flows/` (README only)
- `india/ai_lab/LAB005_Ranking/` (README only)

---

## Frozen (built once, never re-run) — the biggest category by count

These modules have `run.py` files but zero callers anywhere. All produced their output artifact on **2026-07-17** during the DEV017-030 build sprint.

- `research/global_intelligence/` (DEV017)
- `research/sector_intelligence/` (DEV018)
- `research/industry_intelligence/` (DEV019)
- `research/company_intelligence/` (DEV020)
- `research/portfolio_construction/` (DEV022)
- `research/portfolio_monitor/` (DEV024)
- `research/adaptive_learning/` (DEV025+026)
- `research/strategy_doctor/` (DEV027)
- `research/recommendation_dna/run.py` (DEV028, distinct from wired `run_feedback.py` / `run_winner_genome.py`)
- `research/confidence_calibration/` (DEV029)
- `research/champion_challenger/` (DEV030) — test-only invocation via `e2e_test.py`
- `research/backtesting/` — never invoked at all
- `research/recommendations/` (India root — do not confuse with `usa/research/recommendations/`) — never invoked
- `research/research_assistant/` — never invoked

**These are the modules the discovery doc thought were "wired somewhere else." They are not. They ran once and their outputs are actively rendered as if current in the SPA — the Finding 2 staleness bug.**

---

## Dormant (deployable, never deployed in this environment)

- `nexaquant/ops/daemon.py` (`NexaQuantDaemon`)
- `nexaquant/ops/pipeline.py`
- `nexaquant/ops/monitoring.py`
- `nexaquant/ops/notify/*.py` (14 notify channels)
- `nexaquant/ops/cli.py`
- All install templates: `deploy/systemd/nexaquant.service`, `deploy/launchd/com.nexaquant.ops.plist`, `deploy/task-scheduler/nexaquant.xml`, `deploy/aegis-pipeline.service`, `deploy/aegis-dashboard.service`

---

## Independent (not part of AEGIS India/USA)

- `run_nexaquant.py` (repo root) — FOREX/BTC/GOLD MT5 bot
- `config_loader.py` (repo root) — config for the above
- `config/base_config.yaml` — same
- `strategy/` — MT5 bot strategy code
- `backtest/` — MT5 bot backtester

---

## Deprecated (superseded)

- `india/aegis_engine.py` — appears superseded by `india/recommendation_generator.py` + v2 chain
- `india/backpaper.py` — earlier backtester, superseded by `research/backtesting/` (which is itself frozen)
- `research/recommendations/run.py` — India-root recommendation engine, superseded by `research/adaptive_rec_v2/run.py`
- `research/recommendation_dna/run.py` — DEV028 original, superseded by `run_feedback.py` + `run_winner_genome.py` for production paths

---

## Archived (historical)

- `research/RISK001-A_RESULTS.md`
- `docs/chat_transcript_*.md`
- Committed daily reports from prior dates
- `reports/baseline_envelope_2026-07-13.json`
- `reports/risk_capital_v2_2026-07-18.json`, `2026-07-20.json` (daily snapshots)

---

## Grand tally

| Category | Approx count |
|---|---|
| PRODUCTION (scheduled) | 25 |
| PRODUCTION_MANUAL | 12 |
| RESEARCH (one-off) | 40+ |
| PROTOTYPE (README-only) | 5 (LAB001-005) |
| FROZEN | 14 |
| DORMANT | 5 templates + full nexaquant/ops framework |
| INDEPENDENT | 4 (nexaquant/, config_loader, strategy/, backtest/) |
| DEPRECATED | 4 (aegis_engine, backpaper, research/recommendations, research/recommendation_dna/run.py) |
| ARCHIVED | ~10+ |

**~25 modules do the daily work. ~60+ modules exist, don't run daily, but consume repo space, dashboard tiles, or import-graph edges — and 14 of them produce data that the live pipeline still reads and treats as current.**
