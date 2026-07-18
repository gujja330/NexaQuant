# AEGIS · Deployment Guide

Production deployment for `v2.1.0-RC1`. Choose the target that fits
your infrastructure: Docker, systemd (Linux), or Windows Task Scheduler.

---

## Prerequisites (all targets)

- Python 3.12
- Git
- Read/write access to the repo directory for the run user
- `.env.telegram` at repo root (mode `0600`) with:
  ```
  TELEGRAM_BOT_TOKEN=123456:ABCdef...
  TELEGRAM_CHAT_ID=12345678
  ```

## Target 1 · Docker

**Fastest path to a repeatable install.**

```bash
# 1. Build the image
docker build -t aegis:v2.1.0-rc1 .

# 2. Start the dashboard (long-running)
docker compose up -d dashboard

# 3. Run the pipeline on demand
docker compose --profile cron run --rm pipeline

# 4. Send Telegram on demand
docker compose --profile cron run --rm telegram

# 5. Schedule via host cron (Linux example)
#    Every weekday at 06:00 IST (00:30 UTC):
30 0 * * 1-5  cd /path/to/aegis && docker compose --profile cron run --rm pipeline >> /var/log/aegis.log 2>&1
35 0 * * 1-5  cd /path/to/aegis && docker compose --profile cron run --rm telegram >> /var/log/aegis.log 2>&1
```

Dashboard: `http://<host>:8765/ux/dashboard/frontend/index.html`

Health check via container:
```bash
docker exec aegis-dashboard python scripts/aegis_health_check.py
```

## Target 2 · systemd (Linux · AWS EC2 free tier or similar)

**Recommended for a single-VM production install.**

```bash
# 1. Clone + install
sudo useradd -m -s /bin/bash aegis
sudo mkdir -p /opt/aegis
sudo chown aegis:aegis /opt/aegis
sudo -u aegis git clone https://github.com/praveen330/NexaQuant.git /opt/aegis
cd /opt/aegis
sudo -u aegis python3.12 -m venv .venv
sudo -u aegis ./.venv/bin/pip install -r requirements.txt -r requirements-dashboard.txt

# 2. Provision .env.telegram (root-writes-then-locks)
sudo tee /opt/aegis/.env.telegram > /dev/null <<'EOF'
TELEGRAM_BOT_TOKEN=xxxx
TELEGRAM_CHAT_ID=xxxx
EOF
sudo chmod 0600 /opt/aegis/.env.telegram
sudo chown aegis:aegis /opt/aegis/.env.telegram

# 3. Install systemd units
sudo cp deploy/aegis-dashboard.service /etc/systemd/system/
sudo cp deploy/aegis-pipeline.service  /etc/systemd/system/
sudo cp deploy/aegis-pipeline.timer    /etc/systemd/system/
sudo systemctl daemon-reload

# 4. Enable + start
sudo systemctl enable --now aegis-dashboard.service
sudo systemctl enable --now aegis-pipeline.timer

# 5. Verify
systemctl status aegis-dashboard.service
systemctl list-timers aegis-pipeline.timer
```

Logs: `journalctl -u aegis-dashboard.service -f` /
`journalctl -u aegis-pipeline.service -f`.

## Target 3 · Windows Task Scheduler

**Simplest for a Windows-native operator workstation.**

```powershell
# 1. Clone the repo
git clone https://github.com/praveen330/NexaQuant.git C:\aegis
cd C:\aegis

# 2. Create a venv + install
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt -r requirements-dashboard.txt

# 3. Create .env.telegram at the repo root with TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID

# 4. Register the scheduled tasks (run PowerShell as Administrator)
.\deploy\aegis-windows-task.ps1

# 5. Start the dashboard manually (or install as a Windows service via NSSM if needed)
.\.venv\Scripts\python.exe ux\dashboard\frontend\serve.py
```

The setup script registers two tasks:
- **AEGIS-Pipeline** — 06:00 IST weekdays · `scripts/aegis_daily_v2.py`
- **AEGIS-Telegram** — 06:05 IST weekdays · `scripts/telegram_send_with_retry.py`

Verify:
```powershell
Get-ScheduledTask -TaskName AEGIS-*
```

## Health checks

Every 5 minutes (recommended for production):

```bash
python scripts/aegis_health_check.py          # human output
python scripts/aegis_health_check.py --json    # machine output (for Prometheus / Nagios)
```

Exit codes: `0` HEALTHY · `1` DEGRADED · `2` CRITICAL.

Suggested crontab entry:
```
*/5 * * * *  cd /opt/aegis && ./.venv/bin/python scripts/aegis_health_check.py --json >> /var/log/aegis-health.log 2>&1
```

## Log rotation

- systemd journal handles retention on Linux (configure via
  `/etc/systemd/journald.conf`).
- Windows Event Log via Task Scheduler stdout capture.
- Docker: `docker compose logs --tail=100 dashboard`.

The orchestrator itself writes an append-only history file at
`reports/aegis_daily_v2_history.jsonl`. Prune monthly if it grows large
(each entry is ~1 KB).

## Backup

Critical state that MUST be backed up:
- `data/market_intelligence/derived/decisions/` — daily snapshot history
  (Decision Center diffs would restart if lost)
- `data/market_intelligence/derived/validation_v2/paper_trades.parquet` —
  paper-trading ledger (30-day operation continuity resets if lost)
- `reports/` — one week of history is enough (older is in git)
- `docs/` — governance stack

Simple daily backup:
```bash
tar czf /backup/aegis-$(date +%F).tgz \
    /opt/aegis/data/market_intelligence/derived \
    /opt/aegis/reports \
    /opt/aegis/docs
```

Retain 30 days.

## Rollback

If a release ships bad output:

```bash
cd /opt/aegis
git fetch origin
git log --oneline -20                # find last known good commit
sudo systemctl stop aegis-pipeline.timer aegis-pipeline.service
sudo -u aegis git checkout <known_good_commit>
sudo -u aegis git checkout -b rollback-$(date +%F)
sudo systemctl start aegis-dashboard.service
```

Then investigate before re-enabling the timer.

## Upgrade

Rolling upgrade for a Phase 2 point release:
```bash
cd /opt/aegis
sudo systemctl stop aegis-pipeline.timer   # disable daily fires during upgrade
sudo -u aegis git pull
sudo -u aegis ./.venv/bin/pip install -r requirements.txt -r requirements-dashboard.txt
python scripts/aegis_health_check.py
python scripts/e2e_test.py                 # verify end-to-end
sudo systemctl restart aegis-dashboard.service
sudo systemctl start aegis-pipeline.timer  # re-enable
```

## Resource footprint

Observed on the reference dev host during this release:
- Full daily pipeline: ~30-40s CPU (single-threaded)
- Peak memory: ~350 MB
- Dashboard: <30 MB steady-state · <5% CPU serving requests
- Disk: `reports/` = ~50 MB · `data/raw/` = ~200 MB · derived state = ~10 MB

**Reference minimum host:** 1 vCPU · 1 GB RAM · 10 GB disk.
AWS EC2 t2.micro (free tier) is sufficient.

## What's NOT in this deployment

- **No web auth** — dashboard is a local HTTP server. Do NOT expose to
  the public internet without a reverse proxy + auth. Bind to `127.0.0.1`
  by default; see `serve.py`.
- **No TLS termination** — front with Caddy / nginx if you expose beyond
  loopback.
- **No multi-user isolation** — Phase 3 governance work.
- **No paging** — health check writes to log; wire to your paging system
  (PagerDuty / OpsGenie / etc.) if you need alerts.

See [PHASE2_PRODUCTION_AUDIT.md](PHASE2_PRODUCTION_AUDIT.md) §6 for the
full institutional-readiness blocker list.
