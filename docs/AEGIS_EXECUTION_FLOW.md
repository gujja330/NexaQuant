# AEGIS Execution Flow · Runtime paths
**Stage 0.5 deliverable · Every path that ACTUALLY runs**

---

## A. Scheduled paths (proven running)

### A1 · India daily pipeline
- **Trigger:** `.github/workflows/aegis-daily.yml`
- **Schedule:** 4 cron attempts weekdays, `30 0 * * 1-5` / `0 1 * * 1-5` / `30 1 * * 1-5` / `30 2 * * 1-5` (~06:00 / 06:30 / 07:00 / 08:00 IST)
- **Guard:** once-per-IST-day via `data/.published` (workflow lines 48-59)
- **Sequence:**
  1. `india/refresh_data.py` — pull day's OHLCV
  2. `scripts/check_data_freshness.py` — freshness gate
  3. `india/recommendation_generator.py` (fail-fast, line 91)
  4. `scripts/check_data_freshness.py` on `data/aegis_today.csv`
  5. `india/recommendation_db.py` + `india/scorecard.py` + `india/ops_check.py` (masked, non-critical)
  6. `india/sheets_sync.py` (Google Sheets)
  7. **`python scripts/aegis_daily_v2.py --continue`** (line 139) — runs 15 v2 engines
  8. `scripts/telegram_health_check.py` (line 148)
  9. `scripts/telegram_send_with_retry.py --attempts 4` (line 156, wraps `india/telegram_notify.py`)
  10. `scripts/telegram_send_ux030.py` (line 168, `continue-on-error: true`)
  11. Commit + push `[skip ci]`
- **Live evidence:** commit `87eae2c` "AEGIS daily: append market data + refresh report + DB", 2026-07-20 04:15 UTC. Ledger `reports/aegis_daily_v2_history.jsonl` last entry `run_utc: 2026-07-20T05:38:54+00:00, n_success: 15, n_failure: 0`.

### A2 · India v2 orchestrator (`scripts/aegis_daily_v2.py`)
Called from A1 step 7. Runs 15 subprocess steps in dependency order:

| # | Script | Requires |
|---|---|---|
| 1 | `research/adaptive_rec_v2/run.py` | `reports/learning.parquet` |
| 2 | `research/validation_v2/run.py` | `reports/recommendations.json` |
| 3 | `research/risk_capital_v2/run.py` | `recommendations.json`, `global_context.json` |
| 4 | `research/recommendation_dna/run_feedback.py` | `reports/recommendation_dna.parquet` |
| 5 | `research/knowledge_graph/run.py` | `reports/recommendations.json` |
| 6 | `research/adaptive_rec_v2/run_fusion.py` | (uses whatever is available) |
| 7 | `research/validation_v2/run_stock_history.py` | `reports/learning.parquet` |
| 8 | `research/validation_v2/run_price_context.py` | `reports/recommendations.json` |
| 9 | `research/decision_center/run.py` | (baseline mode ok if no prior snapshot) |
| 10 | `research/institutional_memory/run.py` | `reports/recommendations.json` |
| 11 | `research/recommendation_dna/run_winner_genome.py` | `learning.parquet`, `recommendations.json` |
| 12 | `research/decision_attribution/run.py` | `reports/recommendations.json` |
| 13 | `research/benchmark/run.py` | `learning.parquet`, `NSEI_D1.parquet` |
| 14 | `research/morning_report/run.py` | `recommendations.json`, `benchmark.json` |
| 15 | `scripts/aegis_ops_check.py` | (verifies everything) |
| 16 | `scripts/telegram_send_ux030.py` | optional, requires TELEGRAM_* env |

Every step invokes `subprocess.run([sys.executable, str(script)], ...)` at line 260-265. Ledger appended at line 298-301, 375-382.

### A3 · MON001 forward validator
- **Trigger:** `.github/workflows/mon001-daily.yml`
- **Schedule:** `0 11 * * 1-5` / `15 13 * * 1-5` / `45 15 * * 1-5` (~16:30 / 18:45 / 21:15 IST)
- **Guard:** `.mon001_published` marker (lines 55-67)
- **Command:** `python -m india.monitoring.MON001_Forward_Validation.ops.daily_runner` (line 72)
- **Output:** `india/monitoring/MON001_Forward_Validation/ledger/` + `.../reports/` (committed lines 82-85)
- **Broker-agnostic, no Telegram** (line 10-11)

### A4 · USA daily pipeline
- **Trigger:** `.github/workflows/aegis-usa.yml`
- **Schedule:** `30 20 * * 1-5` (20:30 UTC ~ 16:30 EDT / 30 min after US close)
- **Command:** `python usa/scripts/usa_daily.py` (line 34)
- **Sequence:** 13 subprocess steps (build_universe → refresh_market_data → recommendations → validation → risk → fusion → price_context → institutional_memory → winner_genome → decision_attribution → benchmark → morning_report → ops_check) + optional telegram + comparison_report

### A5 · India CI on push
- **Trigger:** `.github/workflows/aegis-ci.yml`
- **On:** push to `main` on `research/**` `scripts/**` dashboard html; PRs; manual
- **Does NOT re-run the pipeline** (explicit, workflow lines 10-12)
- **Runs:** `scripts/aegis_ops_check.py` + `node --check` on SPA JS + `research/morning_report/run.py` smoke test

### A6 · ENG001 governance regression
- **Trigger:** `.github/workflows/eng001-regression.yml`
- **Schedule:** weekly Sunday cron (line 21) + every push/PR
- **Runs:** `nexaquant/tests/{test_lib,test_regression,test_ci_discipline,test_governance}.py` (lines 59-63)

---

## B. Unscheduled paths (code exists, not on any timer)

### B1 · `india/daily_run.py`
- **Trigger:** ONLY `run_daily.bat` (repo root)
- **`run_daily.bat` itself:** unscheduled. Its header explicitly says: *"PRIMARY SCHEDULER = GitHub Actions … This .bat is for local manual runs / laptop-only debugging."* (`run_daily.bat:5-6`)
- **Sequence (`india/daily_run.py:24-52`):**
  1. (optional) `india/broker_angelone.py --pull`
  2. `india/fii_dii.py`
  3. `india/news_sentiment.py`
  4. `india/run_arjuna.py --capital <cap>`
  5. Append basket to `output/paper_log.csv`
- **Consequence:** if the operator doesn't manually run `run_daily.bat`, none of `fii_dii.py`, `news_sentiment.py`, `run_arjuna.py` executes.

### B2 · `scripts/run_pipeline_local.py`
- Reads `nexaquant/ops/pipelines/aegis_daily.yaml`, runs each `stage["command"]` via subprocess (lines 73, 193-198).
- **Zero references in any workflow/scheduler.** Purely manual.

### B3 · `nexaquant/ops/daemon.py` (NexaQuantDaemon)
- Full daemon: PID lock, SIGTERM/SIGINT/SIGBREAK handlers, `Scheduler` polling 3 IST slots (16:15 / 18:30 / 21:00), on-due firing `NexaQuantService.run_once()` → executes stages in `nexaquant/ops/pipelines/aegis_daily.yaml`.
- **Never actually run in this checkout.** `reports/ops_daemon.lock`, `reports/ops_run_state.json`, `reports/ops_schedule_state.json` — **all absent**.
- Install templates at `deploy/{systemd,launchd,task-scheduler}/` point to `/opt/nexaquant` (Linux/macOS) or `C:\opt\nexaquant` (Windows) — paths that don't exist in this repo.

### B4 · `scripts/e2e_test.py`
- Runs `scripts/aegis_daily_v2.py --continue` in-process (line 38-40) then 8 `tests/test_smoke.py` files across `research/*` + `ux/*`.
- **Zero scheduler references.** Manual only.

### B5 · `research/*/run.py` (unwired engines)
- `research/{global,sector,industry,company}_intelligence/run.py`
- `research/{champion_challenger,confidence_calibration,portfolio_construction,portfolio_monitor,strategy_doctor,adaptive_learning,backtesting,recommendations,research_assistant,recommendation_dna}/run.py`
- **None called by any orchestrator.** All were run ONCE on 2026-07-17. See `AEGIS_MODULE_REGISTRY.md` for per-module status.

### B6 · `run_nexaquant.py` (repo root)
- The FOREX/BTC/GOLD bot stack — completely independent from AEGIS India/USA.
- Uses `config_loader.py` + `configs/base_config.yaml` + `strategy/` + `backtest/`.
- Manual invocation only.

---

## C. Deployment artifacts (install-only, no live host proof)

| Artifact | Purpose | Live evidence |
|---|---|---|
| `deploy/aegis-pipeline.service` + `.timer` | systemd unit + Mon-Fri 00:30 UTC timer, runs `scripts/aegis_daily_v2.py --continue` from `/opt/aegis` | Template only |
| `deploy/aegis-dashboard.service` | Serves the dashboard | Template only |
| `deploy/systemd/nexaquant.service` | NexaQuantDaemon systemd unit at `/opt/nexaquant` | Template only |
| `deploy/launchd/com.nexaquant.ops.plist` | macOS launchd unit | Template only |
| `deploy/task-scheduler/nexaquant.xml` | Windows Task Scheduler at `C:\opt\nexaquant` | Template only |
| `deploy/aegis-windows-task.ps1` | Registers `AEGIS-Pipeline` + `AEGIS-Telegram` scheduled tasks weekdays at 06:00 | **Plausibly registered locally** (2026-07-20 11:08 IST v2 artifact timestamps match `--continue` mode + IST offset), but no direct file-based proof |

---

## D. Docker

- `Dockerfile` — multi-purpose. Default CMD serves dashboard on :8765. Overrides available for pipeline runner + health check.
- `docker-compose.yml` — 3 services: `dashboard` (long-running :8765), `pipeline` (one-shot), `telegram` (one-shot). Header explicitly notes: *"schedule externally"* — Compose does not itself schedule.

---

## Summary — what runs today

**Definitely on a schedule:**
- India daily pipeline (`aegis-daily.yml`) — weekdays, 4 attempts, ~06:00-08:00 IST
- India v2 engines (subprocess of above) — same schedule
- MON001 forward validator (`mon001-daily.yml`) — weekdays, 3 attempts, ~16:30-21:15 IST
- USA daily pipeline (`aegis-usa.yml`) — weekdays, 20:30 UTC
- ENG001 governance regression — weekly Sunday + on every push

**Definitely NOT on a schedule (code exists, manual only):**
- `india/daily_run.py` and everything downstream: FII/DII, news sentiment, arjuna run
- `india/fundamentals_nse.py` (no caller at all)
- `nexaquant` daemon (never run in this environment)
- All 12 "unwired" `research/*/run.py` modules
- `run_nexaquant.py` (unrelated bot)

**Every scheduled workflow ultimately calls `scripts/aegis_daily_v2.py` or `usa/scripts/usa_daily.py` as the actual work step.**
