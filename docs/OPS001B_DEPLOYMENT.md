# OPS001-B · Deployment Guide

**Applies to:** OPS001-B daemon · **Version:** 0.1.0-ops001b

Two supported deployment models for the AEGIS + MON001 daily pipeline:

- **A. GitHub Actions cron** (default; already live). See [.github/workflows/aegis-daily.yml](../.github/workflows/aegis-daily.yml) and [.github/workflows/mon001-daily.yml](../.github/workflows/mon001-daily.yml).
- **B. Self-hosted daemon** via OPS001-B. This document covers B.

Both can coexist, but if you run both they will race on the daily Telegram
send. Pick one canonical firer per environment.

## 1. Prerequisites

| Item | Notes |
|---|---|
| Python 3.12+ | Same version CI uses |
| `pyyaml`, `pandas`, `numpy`, `pyarrow`, `scipy`, `scikit-learn` | Same as CI |
| `psutil` (optional) | Richer process metrics; monitoring falls back gracefully without it |
| Broker + Telegram secrets in `.env` (local) or `EnvironmentFile=/etc/nexaquant/nexaquant.env` (systemd) | Never commit these |
| Write access to `reports/` | Daemon writes logs, status, run/schedule state here |

## 2. Directory layout on the host

```
/opt/nexaquant/                          # WorkingDirectory
├── nexaquant/                            # Python package (from checkout)
├── india/                                # Sealed research + MON001
├── scripts/nexaquant_daemon.py           # Entrypoint
├── deploy/                               # Platform templates
└── reports/                              # Runtime state (writable)
    ├── logs/nexaquant_ops.jsonl          # Rotated JSON logs
    ├── ops_status.json                   # Current snapshot
    ├── ops_daemon.lock                   # PID lock
    ├── ops_schedule_state.json           # Last-fire per slot
    ├── ops_run_state.json                # Interrupted-run recovery data
    └── ops_metrics.jsonl                 # Append-only metrics ledger
```

## 3. Linux (systemd) — recommended

### 3.1 Install

```bash
sudo git clone https://github.com/praveen330/NexaQuant.git /opt/nexaquant
cd /opt/nexaquant

sudo useradd -r -M -d /opt/nexaquant -s /usr/sbin/nologin nexaquant
sudo chown -R nexaquant:nexaquant /opt/nexaquant/reports

sudo -u nexaquant python3 -m venv /opt/nexaquant/.venv
sudo -u nexaquant /opt/nexaquant/.venv/bin/pip install \
    pyyaml pandas numpy pyarrow scipy scikit-learn psutil

sudo mkdir -p /etc/nexaquant
sudo chown root:nexaquant /etc/nexaquant
sudo chmod 750 /etc/nexaquant
sudo tee /etc/nexaquant/nexaquant.env <<'EOF'
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
BROKER_MODE=paper
EOF
sudo chmod 640 /etc/nexaquant/nexaquant.env

sudo cp /opt/nexaquant/deploy/systemd/nexaquant.service /etc/systemd/system/
# If using the venv, adjust ExecStart to:
#   ExecStart=/opt/nexaquant/.venv/bin/python /opt/nexaquant/scripts/nexaquant_daemon.py start
sudo systemctl daemon-reload
sudo systemctl enable --now nexaquant
sudo systemctl status nexaquant
```

### 3.2 Verify

```bash
sudo journalctl -u nexaquant -n 50 -f
python3 /opt/nexaquant/scripts/nexaquant_daemon.py status
python3 /opt/nexaquant/scripts/nexaquant_daemon.py health
```

## 4. Windows (Task Scheduler)

```powershell
git clone https://github.com/praveen330/NexaQuant.git C:\opt\nexaquant
cd C:\opt\nexaquant

py -3.12 -m venv .venv
.\.venv\Scripts\pip.exe install pyyaml pandas numpy pyarrow scipy scikit-learn psutil

# Edit UserId + paths in deploy\task-scheduler\nexaquant.xml, then:
schtasks /Create /TN "NexaQuant Ops Daemon" /XML deploy\task-scheduler\nexaquant.xml
schtasks /Run /TN "NexaQuant Ops Daemon"
```

Verify:

```powershell
Get-ScheduledTask -TaskName "NexaQuant Ops Daemon" | Get-ScheduledTaskInfo
python scripts\nexaquant_daemon.py status
```

## 5. macOS (launchd)

```bash
cp deploy/launchd/com.nexaquant.ops.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.nexaquant.ops.plist
launchctl list | grep nexaquant
```

## 6. First-boot sanity checklist

Run all of these before declaring the deployment healthy:

- [ ] `python scripts/nexaquant_daemon.py health` → exit 0, all checks `INFO`
- [ ] `python nexaquant/tests/test_regression.py` → all suites PASS, all invariance guards hold
- [ ] Daemon is up: `status` shows `daemon_running: true`
- [ ] `reports/logs/nexaquant_ops.jsonl` shows `daemon_started`
- [ ] `next_run_utc` in `status` output is in the future
- [ ] MON001 fingerprint matches seal `64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42`
- [ ] `python scripts/telegram_health_check.py` → OK
- [ ] After one slot fires: `slot_completed` event appears in log

## 7. Upgrading

```bash
# Systemd
sudo systemctl stop nexaquant
sudo -u nexaquant git -C /opt/nexaquant pull
sudo systemctl start nexaquant

# Windows
python scripts\nexaquant_daemon.py stop
git pull
schtasks /Run /TN "NexaQuant Ops Daemon"
```

The daemon's stale-lock detection means an ungraceful upgrade will not
block the new daemon indefinitely (locks are stale after 6h by default).

## 8. Uninstall

```bash
# Systemd
sudo systemctl disable --now nexaquant
sudo rm /etc/systemd/system/nexaquant.service
sudo systemctl daemon-reload

# Windows
schtasks /Delete /TN "NexaQuant Ops Daemon" /F
```

## 9. Secrets

- **Never** commit `.env` or `nexaquant.env`.
- PID lock + schedule state under `reports/` are safe (no secrets, only
  pids and timestamps), but keep the `reports/` directory out of version
  control anyway to avoid leaking hostnames.
- MON001 sealed files must remain sealed. Any deployment change that
  requires touching them must go through the CHANGE_CONTROL_CHECKLIST.

## 10. What deployment does NOT change

- Any production strategy behaviour.
- MON001 fingerprint hash `64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42`.
- `cumulative_strategy_search = 38`.
- Any LAB artefact.
- Any governance checklist.

If any of the above changes as a side-effect of your deployment, stop and
investigate — an ambient environment variable or tool-version drift has
silently affected sealed logic.
