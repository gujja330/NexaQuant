# AEGIS Dependency Graph · Module-level who-calls-what
**Stage 0.5 deliverable · Runtime dependency edges only**

---

## A. India daily production DAG (from `aegis-daily.yml`)

```
                          [Cron / Windows Task]
                                  │
                                  ▼
                   ┌──── aegis-daily.yml ─────┐
                   │                           │
                   ▼                           ▼
       india/refresh_data.py         scripts/check_data_freshness.py
                   │                           │
                   ▼                           │
       india/recommendation_generator.py       │
                   │                           │
       ┌───────────┼───────────┐               │
       │           │           │               │
       ▼           ▼           ▼               │
  recommendation_ scorecard  ops_check         │
  db.py           .py        .py               │
       │                                       │
       ▼                                       │
       sheets_sync.py                          │
                   │                           │
                   ▼                           │
       scripts/aegis_daily_v2.py --continue    │
                   │                           │
       ┌───────────┴──────────────┐           │
       │ 15-step subprocess chain │           │
       │  (see EXECUTION_FLOW §A2)│           │
       └──────────────────────────┘           │
                   │                           │
                   ▼                           │
       scripts/telegram_health_check.py        │
                   │                           │
                   ▼                           │
       scripts/telegram_send_with_retry.py     │
                   │                           │
                   ▼                           │
       india/telegram_notify.py                │
                   │                           │
                   ▼                           │
       scripts/telegram_send_ux030.py          │
                   │                           │
                   ▼                           │
       git commit + push [skip ci]             │
```

## B. `scripts/aegis_daily_v2.py` — 15-step DAG

```
learning.parquet (STALE 2026-07-17)    global_context.json (STALE 2026-07-17)
    │                                          │
    │   (hard requires)                        │  (hard requires)
    ▼                                          ▼
[1] adaptive_rec_v2/run.py            [3] risk_capital_v2/run.py
    │                                          ▲
    ▼                                          │
    recommendations.json ─────────────────────┤
    │                                          │
    ├─────────────┬─────────────┬──────────────┼──────────────┬──────────┐
    ▼             ▼             ▼              ▼              ▼          ▼
[2] validation [4] dna_    [5] knowledge_ [6] fusion     [7] stock_    [8] price_
   _v2/run.py     feedback     graph        (run_fusion)     history      context
    │                                          │                          │
    │                                          ▼                          │
    │                             investment_intelligence.json            │
    │                                          │                          │
    ▼                                          │                          ▼
    validation_v2_latest.json                  ▼                     price_context.json
                             [9] decision_center/run.py
                                              │
                                              ▼
                             decision_center_today.json
                                              │
                                              ▼
                           [10] institutional_memory/run.py
                                              │
                                              ▼
                          data/archive/YYYY/MM/DD/bundle/ + rec_lifecycle
                                              │
                          ┌───────────────────┼─────────────────┐
                          ▼                   ▼                 ▼
                       [11] winner_    [12] decision_       [13] benchmark
                            _genome         attribution          (vs NIFTY)
                          │                   │                 │
                          ▼                   ▼                 ▼
                        winner_genome    decision_attrib.  benchmark.json
                          │                   │                 │
                          └───────────┬───────┴─────────────────┘
                                      ▼
                         [14] morning_report/run.py
                                      │
                                      ▼
                         morning_YYYY-MM-DD.{md,html}
                                      │
                                      ▼
                         [15] scripts/aegis_ops_check.py
                                      │
                                      ▼
                              ops_check.json
                                      │
                                      ▼
                         [16 opt] scripts/telegram_send_ux030.py
```

**Critical read of this DAG:** two nodes at the top (`learning.parquet` and `global_context.json`) are **inputs** to the daily flow but are NOT themselves produced by the daily flow. They are inherited from the 2026-07-17 sprint. **Every subsequent step is downstream of a stale input.**

## C. Wired daily step → library imports

Each `research/*/run.py` in the daily chain imports from these India modules (grep verified for a sample):

- `research/adaptive_rec_v2/compute/engine.py` reads `learning.parquet`, uses sklearn HistGradientBoosting, permutation_importance
- `research/risk_capital_v2/compute/engine.py:49` reads `global_context.json` for regime input
- `research/knowledge_graph/lib/entities.py:292` + `relationships.py:227,283` read `global_context.json`
- `research/institutional_memory/lib/archive.py:33` reads `global_context.json`
- `research/morning_report/run.py:94` reads `global_context.json`
- `research/decision_attribution/lib/attribution.py:74` reads `global_context.json`

**Consequence:** the 15-step v2 chain treats `global_context.json` as the current global-regime signal on every run. It has been static for 3+ days.

## D. Unscheduled manual chain (`run_daily.bat` → `india/daily_run.py`)

```
[Operator manually runs run_daily.bat]
              │
              ▼
   india/daily_run.py
              │
   ┌──────────┼───────────┬──────────────┐
   ▼          ▼           ▼              ▼
india/     india/     india/         india/
broker_    fii_dii    news_          run_arjuna
angelone   .py        sentiment      .py
--pull                 .py            │
                                      │  (imports arjuna_strategy)
                                      ▼
                             output/paper_log.csv
```

**None of these run automatically.**

## E. USA daily production DAG (`aegis-usa.yml` → `usa/scripts/usa_daily.py`)

```
[Cron 20:30 UTC weekdays]
         │
         ▼
usa/scripts/usa_daily.py
         │
         ▼
[1] build_universe.py ← usa/configs/universe.yaml
         │
         ▼
   universe.json
         │
         ▼
[2] refresh_market_data.py (yfinance)
         │
         ▼
   usa/data/raw/us/*.parquet
         │
         ▼
[3] usa/research/recommendations/run.py
         │
         ▼
   usa/reports/recommendations.json
         │
         ├──[4] validation/run.py
         ├──[5] risk/run.py
         ├──[6] fusion/run.py
         ├──[7] price_context/run.py
         ├──[8] institutional_memory/run.py
         ├──[9] winner_genome/run.py (stub — insufficient_data mode)
         ├──[10] decision_attribution/run.py
         ├──[11] benchmark/run.py (stub — no historical trades)
         └──[12] morning_report/run.py
                    │
                    ▼
              [13] usa_ops_check.py
                    │
                    ▼
              [14 opt] usa/scripts/telegram_send.py
                    │
                    ▼
              [15] compare/build_comparison.py (INDIA + USA)
```

USA has NO equivalent of the 4-tier intelligence hierarchy — the "fusion" step (6) is a single-tier aggregate over 6 technical dimensions.

## F. Nexaquant daemon DAG (DORMANT — never run)

```
[systemd/launchd/Task-Scheduler — install templates only, never registered]
         │
         ▼ (if it ran)
nexaquant/ops/daemon.py → NexaQuantDaemon
         │
         ▼
Scheduler.due() polling
         │  (3 IST slots: 16:15 / 18:30 / 21:00)
         ▼
NexaQuantService.run_once()
         │
         ▼
nexaquant/ops/pipelines/aegis_daily.yaml (8 stages, PRE-v2)
         │
         ▼
Various india/*.py + MON001.ops.daily_runner
         │
         ▼
nexaquant/ops/notify/* (14 channels — never fires)
```

## G. Import-graph highlights (imported-heavily nodes)

- `reports/global_context.json` — 15+ readers (biggest single dependency in the codebase)
- `reports/recommendations.json` — 12+ readers (biggest live dependency)
- `reports/learning.parquet` — 4+ hard requires (biggest stale dependency)
- `india/config.py` — imported by every `india/*.py` module
- `india/confidence_engine.py` — imported by `recommendation_generator.py` for `current_regime()` (the live regime)

## H. Fanout — modules with the most callers/consumers

| Module | Callers |
|---|---|
| `global_context.json` (as data) | 15+ |
| `research/adaptive_rec_v2/run.py` (via subprocess) | Called by `aegis_daily_v2.py` — but its output `recommendations.json` is read by 12+ downstream |
| `india/technical_factors.py` | Library imported across `india/*.py` |
| `nexaquant/ops/notify/manager.py` | Aggregates 14 notify channels — but daemon dormant |

## I. Circular dependencies

None found in the daily production chain — the DAG is a strict topological order enforced by the `requires:` field in `aegis_daily_v2.py`'s STEPS list.

## J. Dead edges (imports that never fire)

- Every `research/adaptive_learning/*.py` internal import graph — the whole module never runs
- Every `research/champion_challenger/*.py` — only test-only invocation
- All 4 intelligence engines' internal graphs — inputs stale, outputs consumed but never refreshed
