# AEGIS Configuration Registry
**Stage 0.5 deliverable · Every config file and its actual role**

---

## Repo-root configs

| File | Role | Consumers |
|---|---|---|
| `configs/base_config.yaml` | **NOT AEGIS India/USA** — this is the NexaQuant MT5 bot config (gold/BTC/forex). Defines `system.symbols`, `live_symbols` (`BTCUSDc`, `XAUUSDc`), `live_edges` (`trend`, `breakout`), MT5 broker settings, `risk_per_trade: 0.005`, `max_drawdown_limit: 0.20`. | `config_loader.py` at repo root → `run_nexaquant.py` |
| `config_loader.py` (root) | Loads `configs/base_config.yaml`; derives per-symbol `cost` / `pip_size` from price data | `run_nexaquant.py` |
| `nexaquant/ops/pipelines/aegis_daily.yaml` | **REFERENCE pipeline** (per its own header, line 1-8) mirroring the *pre-v2* India daily flow. 8 stages: refresh_data → freshness_gate → recommendation_generator → recommendation_db → scorecard → ops_check → telegram_health_check → telegram_notify → mon001_daily | `scripts/run_pipeline_local.py` (manual) and `nexaquant/ops/pipeline.py` (via dormant daemon) — **neither consumer is scheduled** |
| `usa/configs/universe.yaml` | USA equity universe. `active_universe: dow30` (line 10) — 30 Dow tickers with symbol/name/sector/industry/exchange. Also has expansion universes (`sp500_top50`, `nasdaq100`) not activated. | `usa/scripts/build_universe.py` (step 1 of `usa_daily.py`) |

## Environment files (all git-ignored, never inspected)

| File | Purpose | Status |
|---|---|---|
| `.env.angel` | Angel Broking API credentials for `india/broker_angelone.py` | Git-ignored per `.gitignore:6,8`; not tracked (`git ls-files` returns empty) |
| `.env.telegram` | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Git-ignored; loaded by `scripts/telegram_send_ux030.py`, `usa/scripts/telegram_send.py`, `scripts/telegram_health_check.py` |
| `.env` (generic) | Fallback | Git-ignored |

**No values inspected per Stage 0.5 read-only discipline.** Both files reportedly exist locally per operator statement in prior turns.

## GitHub Actions secrets (referenced in workflows)

| Secret | Used by |
|---|---|
| `TELEGRAM_BOT_TOKEN` | `aegis-daily.yml`, `aegis-usa.yml` |
| `TELEGRAM_CHAT_ID` | Same |
| `AEGIS_SPREADSHEET_ID` | `aegis-daily.yml` (Google Sheets sync) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Optional, mentioned in workflow comments |

## Dependencies

| File | Role | Notes |
|---|---|---|
| `requirements.txt` | 39 lines — kitchen-sink superset for dev/research. Includes heavy ML stack. | Header: "dev/research dependencies" |
| `requirements-dashboard.txt` | 11 lines — Linux-safe slim for deploying `india/aegis_dashboard.py`. Excludes `MetaTrader5`, `torch`, `ray`, `transformers`. | Header note |
| `requirements-live.txt` | 11 lines — Windows-only NexaQuant bot deps. Includes `MetaTrader5`, `hmmlearn`. | Header note — NOT for AEGIS India/USA |

## Containerization

| File | Role |
|---|---|
| `Dockerfile` | Multi-purpose image. Default `CMD` serves the dashboard on :8765. Alternative CMDs for pipeline or health check via override. |
| `docker-compose.yml` | 3 services: `dashboard` (long-running :8765, bind-mounts `./reports` + `./data` read-only), `pipeline` (one-shot), `telegram` (one-shot). Explicitly requires **external scheduling** — Compose does not schedule. |

## GitHub workflow files

| Path | Trigger + purpose |
|---|---|
| `.github/workflows/aegis-daily.yml` | Cron 4×/day IST weekdays. Full India pipeline (18-step). |
| `.github/workflows/aegis-usa.yml` | Cron 20:30 UTC weekdays. `usa/scripts/usa_daily.py`. |
| `.github/workflows/aegis-ci.yml` | On push to research/scripts/dashboard + PR + manual. Ops check + SPA JS parse + morning_report smoke test. |
| `.github/workflows/mon001-daily.yml` | Cron 3×/day IST weekdays. `india.monitoring.MON001_Forward_Validation.ops.daily_runner`. |
| `.github/workflows/eng001-regression.yml` | Weekly Sunday + push/PR. Runs `nexaquant/tests/*` regression suite. |

## Deployment artifact configs

| Path | Kind | Target host |
|---|---|---|
| `deploy/aegis-pipeline.service` | systemd unit | `/opt/aegis` (Linux template) |
| `deploy/aegis-pipeline.timer` | systemd timer, Mon-Fri 00:30 UTC | Same |
| `deploy/aegis-dashboard.service` | systemd unit | Serves dashboard |
| `deploy/systemd/nexaquant.service` | systemd unit for NexaQuantDaemon | `/opt/nexaquant` (Linux template) |
| `deploy/launchd/com.nexaquant.ops.plist` | macOS launchd | `/opt/nexaquant` |
| `deploy/task-scheduler/nexaquant.xml` | Windows Task Scheduler | `C:\opt\nexaquant` |
| `deploy/aegis-windows-task.ps1` | PowerShell setup script that registers `AEGIS-Pipeline` + `AEGIS-Telegram` Windows Tasks | Operator's local machine |

**None of these have file-based proof of active installation** on the current host, except `aegis-windows-task.ps1` which the operator's daily artifact timestamps (11:0x IST) suggest may be registered.

## Runtime scripts (batch/PowerShell)

| Path | Role | Scheduled? |
|---|---|---|
| `run_daily.bat` (root) | Manual India daily runner. Calls `india/refresh_data.py` → `india/daily_run.py` → `india/recommendation_generator.py` → `india/telegram_notify.py` | **NO** — self-declared non-primary |
| `run_nexaquant.py` (root) | Manual FOREX/BTC bot runner. Iterates `data/raw/*_H1.parquet`, runs regime → entries → meta-label → simulation → PBO/DSR gate. Unrelated to AEGIS India/USA. | **NO** |

## Feature registry configs

`docs/FEATURE_REGISTRY.md` acts as an implicit config — it lists every feature/signal with `PIT / quality / live / tested / promoted` status. This is the authoritative record of what actually feeds decisions.

Currently PROMOTED (India):
- Volatility/risk rank
- HRP weighting
- Regime exposure (200-DMA + VIX + Global)
- Dynamic tradable universe

Currently PLANNED (USA):
- SEC fundamentals
- Earnings surprise
- Insider buying
- ETF flows
- 13F institutional
- FRED macro
- News/sentiment

Confirms: `markets/usa/raw/{13f,earnings,etf,fundamentals,macro,news}/` dirs are provisioned for planned work, not existing capability.

## Special config file: `india/config.py`

Not a static config, but the runtime-authoritative Python constants module. Key items:

- `regime: str = "global"` (default line 56) — the live regime engine
- `MODELS_FROZEN_UNTIL_DATA_ARRIVES = True` — the policy blocking ML re-activation per `docs/ARJUNA_V4_ROADMAP.md`
- Various HRP / risk-per-trade / holding-period parameters

Read this file first before proposing any PRD change to regime or ML behaviour.

## Summary — config surface area

- **1 config actually governing India production behaviour:** `india/config.py`
- **1 config actually governing USA production behaviour:** `usa/configs/universe.yaml`
- **1 config for the unrelated NexaQuant bot:** `configs/base_config.yaml`
- **1 reference-only pipeline YAML** never actively executed: `nexaquant/ops/pipelines/aegis_daily.yaml`
- **6 deploy templates** at various paths, none proven-installed
- **5 GitHub workflows** with cron schedules
- **3 env files** (never inspected)
