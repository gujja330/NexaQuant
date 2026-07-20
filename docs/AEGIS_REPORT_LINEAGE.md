# AEGIS Report Lineage · Producer → Consumer per artifact
**Stage 0.5 deliverable · Every fresh `reports/*.json` traced to origin and use**

Freshness scale:
- 🟢 **LIVE_DAILY** — refreshed by the current daily orchestrator
- 🟡 **FROZEN_2026-07-17** — produced once during the DEV017-030 build sprint, unchanged since
- ⚪ **INTERMEDIATE** — refreshed by v2 orchestrator but consumed only by that same run

---

## A. Intelligence hierarchy (all FROZEN)

| Artifact | Producer | Consumers | Freshness |
|---|---|---|---|
| `reports/global_context.json` + `.parquet` | `research/global_intelligence/run.py` → `publish/bundle.py:96-97` (never invoked at runtime) | 15+ consumers: `company_intelligence/compute/engine.py:34`, `industry_intelligence/compute/engine.py:36`, `sector_intelligence/compute/engine.py:42`, `research/champion_challenger/lib/strategies_io.py:57`, `research/decision_attribution/lib/attribution.py:74`, `research/institutional_memory/lib/archive.py:33`, `research/knowledge_graph/lib/entities.py:292` + `relationships.py:227,283`, `research/morning_report/run.py:94`, `research/research_assistant/lib/loaders.py:58`, **`research/risk_capital_v2/compute/engine.py:49` (LIVE DAILY STEP)** ← reads stale file, `scripts/aegis_ops_check.py:47`, `ux/dashboard/lib/widgets.py:28,168`, `ux/telegram/lib/aggregator.py:60`, `ux/dashboard/frontend/index.html:885` (SPA renders this — see line 1498) | 🟡 FROZEN 2026-07-17 14:37 |
| `reports/sector_context.json` + `.parquet` | `research/sector_intelligence/` (never invoked) | Sector/industry/company inheritance chain | 🟡 FROZEN 2026-07-17 14:48 |
| `reports/industry_context.json` + `.parquet` | `research/industry_intelligence/` (never invoked) | `company_intelligence` reads it | 🟡 FROZEN 2026-07-17 15:04 |
| `reports/company_context.json` + `.parquet` | `research/company_intelligence/` (never invoked) | Not consumed by any wired step (terminal) | 🟡 FROZEN 2026-07-17 15:47 |

**Critical implication:** `research/risk_capital_v2/compute/engine.py:49` reads `global_context.json` on EVERY daily run and treats it as the current regime signal — but the file has been static since 2026-07-17.

## B. Strategy tier (all FROZEN, but ACTIVELY RENDERED in SPA)

| Artifact | Producer | Consumers | Freshness |
|---|---|---|---|
| `reports/champion_strategy.json` | `research/champion_challenger/run.py` (only invoked via `e2e_test.py:108` unit test) | **SPA:** `index.html:886` fetches into `STATE.champion_strategy`, rendered at lines `1500, 2081, 3754, 3781` | 🟡 FROZEN 2026-07-17 18:03 |
| `reports/challenger_scoreboard.json` | Same producer | **SPA:** `index.html:902, 3777` | 🟡 FROZEN 2026-07-17 18:03 |
| `reports/head_to_head_matrix.json` | Same producer | Not verified | 🟡 FROZEN |
| `reports/promotion_recommendation.json` | Same producer | Not verified | 🟡 FROZEN |

## C. Calibration + confidence (all FROZEN, RENDERED IN SPA)

| Artifact | Producer | Consumers | Freshness |
|---|---|---|---|
| `reports/confidence_calibration.json` + `.parquet` | `research/confidence_calibration/run.py` (never invoked) | **SPA:** `index.html:887, 1507, 3678, 3811, 3865` | 🟡 FROZEN 2026-07-17 17:39 |
| `reports/calibration_metrics.json` | Same | Not verified | 🟡 FROZEN |
| `reports/calibration_history.json` | Same | Not verified | 🟡 FROZEN |
| `reports/reliability_diagram.json` | Same | Not verified | 🟡 FROZEN |
| `reports/confidence_bias.json` | Same | Not verified | 🟡 FROZEN |

## D. Portfolio tier (all FROZEN)

| Artifact | Producer | Consumers | Freshness |
|---|---|---|---|
| `reports/portfolio.json` + `.parquet` | `research/portfolio_construction/run.py` (never invoked) | Not consumed by any live step | 🟡 FROZEN 2026-07-17 16:22 |
| `reports/portfolio_monitor.json` + `.parquet` | `research/portfolio_monitor/run.py` (never invoked) | Not consumed by any live step | 🟡 FROZEN 2026-07-17 16:49 |
| `reports/portfolio_leaderboard.json` | portfolio_construction | Not verified | 🟡 FROZEN |
| `reports/allocation_report.json` | portfolio_construction | Not verified | 🟡 FROZEN |
| `reports/rebalance_plan.json` + `rebalance_report.json` | portfolio_construction | Not verified | 🟡 FROZEN |
| `reports/execution_plan.json` | Same tier | Not verified | 🟡 FROZEN |

## E. Learning corpus (CRITICAL FROZEN DEPENDENCY)

| Artifact | Producer | Consumers | Freshness |
|---|---|---|---|
| `reports/learning.parquet` | `research/adaptive_learning/run.py` (never invoked since day 1) | **HARD `requires:` DEPENDENCY of 4 LIVE DAILY STEPS:** `adaptive_rec_v2` (`aegis_daily_v2.py:58`), `stock_validation` (:104), `winner_genome` (:135), `benchmark` (:149) | 🟡 FROZEN 2026-07-17 17:06 |

**This is FINDING 1 in `AEGIS_STAGE0_COMPLETION.md`.** The daily pipeline trains and scores against a corpus that never updates.

| Related | Same producer, same freeze | Consumers |
|---|---|---|
| `reports/learning_summary.json` | Same | Various |
| `reports/recommendation_accuracy.json` | Same | Various |
| `reports/pattern_discovery.json` | Same | Various |
| `reports/success_patterns.json` + `failure_patterns.json` | Same | Various |
| `reports/improvement_plan.json` + `improvement_suggestions.json` | Same | Various |
| `reports/root_cause_analysis.json` | Same | Various |
| `reports/failure_analysis.json` | Same | Various |
| `reports/self_improvement.json` | Same | Various |
| `reports/recommendation_dna.parquet` | `research/recommendation_dna/run.py` (never invoked) | Hard dependency of `dna_feedback` step (`aegis_daily_v2.py:79`) and `winner_genome` step (:135) | 🟡 FROZEN 2026-07-17 17:22 |

## F. Live daily artifacts (refreshed every run)

These 20+ files are refreshed by the current 15-step orchestrator on every daily run. Freshness confirmed by `2026-07-20 11:0x IST` mtimes matching the day's ledger entry.

| Artifact | Producer step | Key consumers |
|---|---|---|
| `reports/recommendations.json` + `.parquet` | Step 1 (`adaptive_rec_v2/run.py`) | Steps 2, 5, 8, 10, 12, 13, 14; SPA; Telegram |
| `reports/adaptive_rec_v2_{signal,scoreboard,reliability,feature_importance}.json` + `.parquet` | Step 1 | Various |
| `reports/investment_intelligence.json` + `.parquet` | Step 6 (`run_fusion.py`) | SPA extensively (many line refs); Telegram UX030 |
| `reports/intelligence_summary.json` | Step 6 | SPA, Telegram |
| `reports/intelligence_conflicts.json` | Step 6 | SPA |
| `reports/intelligence_explanation.json` | Step 6 | SPA |
| `reports/validation_v2_latest.json` + `daily_YYYY-MM-DD.json/.md` | Step 2 | Ops check, SPA |
| `reports/stock_validation.json` | Step 7 | SPA (Sheet route) |
| `reports/price_context.json` | Step 8 | SPA, Telegram |
| `reports/risk_capital_v2_latest.json` + `YYYY-MM-DD.json` | Step 3 | SPA, Telegram, ops check |
| `reports/risk_capital_v2_sizing.parquet` | Step 3 | Same |
| `reports/risk_capital_v2_explanation_YYYY-MM-DD.md` | Step 3 | Docs archive |
| `reports/recommendation_dna_feedback.json` | Step 4 (`run_feedback.py`) | Step 6 (fusion); SPA |
| `reports/knowledge_graph.{json,parquet}` | Step 5 | SPA |
| `reports/community_clusters.json` | Step 5 | SPA |
| `reports/stress_scenarios.json` | Step 5 | SPA |
| `reports/graph_statistics.json` | Step 5 | SPA |
| `reports/entity_network.json`, `company_network.json`, `sector_network.json` | Step 5 | SPA |
| `reports/relationship_matrix.json` | Step 5 | SPA |
| `reports/recommendation_paths.json` | Step 5 | SPA |
| `reports/influence_propagation.json` | Step 5 | SPA |
| `reports/graph_timeline.json` | Step 5 | SPA |
| `reports/decision_center_today.json` | Step 9 | SPA (top of dashboard) |
| `reports/decision_center_notifications.json` | Step 9 | SPA + Telegram |
| `reports/watchlist.json` | Step 9 | SPA |
| `reports/missed_opportunities.json` | Step 10 (`institutional_memory/run.py`) | SPA |
| `reports/recommendation_lifecycle.json` + `.parquet` | Step 10 | SPA + morning report |
| `reports/recommendation_history.json` | Step 10 | SPA (Sheet + Stock Detail) |
| `reports/winner_genome.json` | Step 11 (`run_winner_genome.py`) | SPA, Telegram |
| `reports/decision_attribution.json` | Step 12 | SPA (Decision Card + Admin), Telegram |
| `reports/benchmark.json` | Step 13 | SPA, Telegram |
| `reports/morning_YYYY-MM-DD.{md,html}` + `morning_latest.{md,html}` | Step 14 | Directly opened; SPA top nav "📄 MORNING" link |
| `reports/ops_check.json` | Step 15 | Verifies everything |
| `reports/aegis_daily_v2_history.jsonl` | Written by orchestrator itself | Health monitoring |
| `reports/telegram_delivery_YYYY-MM-DD.jsonl` | `telegram_send_ux030.py` | Delivery ledger |
| `reports/telegram_health_YYYY-MM-DD.json` | `telegram_health_check.py` | Health ledger |

## G. Legacy India pipeline (pre-v2) — refreshed by `aegis-daily.yml` steps 3-6

| Artifact | Producer |
|---|---|
| `reports/AEGIS_LATEST.xlsx` | `india/recommendation_generator.py` (workflow line 91) |
| `data/aegis_today.csv`, `data/aegis_candidates.csv`, `data/aegis_recommendation_db.csv`, `data/aegis_registry.csv` | Same chain |

## H. Orphaned artifacts (produced but never consumed)

| Artifact | Producer | Why orphaned |
|---|---|---|
| `reports/dashboard_config.json` | `ux/dashboard/publish/bundle.py` (commit `26dab3a`, UX031) | SPA layout is hardcoded in `index.html`; no consumer found |
| `reports/dashboard_layout.json` | Same | Same |
| `reports/dashboard_routes.json` | Same | Same |
| `reports/dashboard_theme.json` | Same | Same |
| `reports/dashboard_widgets.json` | Same | Same |
| `reports/telegram_commands.json`, `telegram_templates.json`, `telegram_ui_config.json`, `telegram_layouts.json`, `telegram_notification_rules.json`, `telegram_examples.md` | `ux/telegram/publish/` | Renderer is hardcoded; no consumer found |
| `reports/executive_summary.json` | Not traced (likely UX030 sprint) | No live consumer verified |
| `reports/company_report.json`, `sector_report.json` | intelligence engines | Terminal; no downstream |
| `reports/regime_comparison.json` | Not traced | No live consumer |
| `reports/drift_report.json` | Not traced | Possible consumer in SPA |
| `reports/signal_attribution.json` | Not traced | Possible SPA use |
| `reports/trade_summary.json` | Not traced | — |
| `reports/portfolio_health.json`, `portfolio_report.json`, `holdings_demo.json` | Various | — |
| `reports/aegis_performance.json`, `performance_metrics.json`, `performance_report.json` | Not traced | — |
| `reports/comparison_report.json` | Not traced (may be old cross-market compare) | — |
| `reports/recommendation_statistics.json`, `recommendation_versions.json` | Not traced | — |
| `reports/alerts.json` | Not traced | — |
| `reports/stress_test.json` | Possibly duplicate of `stress_scenarios.json` | — |
| `reports/backtest_summary.{json,parquet}` | `research/backtesting/` (never invoked) | 🟡 FROZEN |
| `reports/strategy_comparison.json` | Not traced | — |
| `reports/strategy_leaderboard.parquet` | Not traced | — |
| `reports/baseline_envelope_YYYY-MM-DD.json` | Historical | Frozen |

---

## Aggregate

- **~35 artifacts refreshed every daily run** (production live)
- **~15 artifacts frozen since 2026-07-17**, of which **5 are actively rendered in the SPA** as if live (champion_strategy, challenger_scoreboard, confidence_calibration, strategy_doctor, global_context)
- **~20 artifacts orphaned** (produced once, never consumed by any live path)
- **`learning.parquet` frozen but is a HARD `requires:` of 4 live daily steps** (the most critical staleness — see FINDING 1)

The scale of orphaned + frozen artifacts (~35) is comparable to the count of live artifacts (~35). Roughly half of `reports/` is dead weight or stale data being surfaced as live.
