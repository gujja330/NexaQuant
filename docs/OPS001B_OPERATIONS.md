# OPS001-B · Operations Runbook

Day-to-day operator reference. If you are the person on call, read this first.

## 1. Where things live

| Artifact | Path |
|---|---|
| Daemon entrypoint | `scripts/nexaquant_daemon.py` |
| Daemon config defaults | `nexaquant/ops/daemon.py::default_daemon_config` |
| Pipeline YAML | `nexaquant/ops/pipelines/aegis_daily.yaml` |
| PID lock | `reports/ops_daemon.lock` |
| Structured logs | `reports/logs/nexaquant_ops.jsonl` (+ rotated `.1`, `.2`, ...) |
| Schedule state | `reports/ops_schedule_state.json` |
| Run state | `reports/ops_run_state.json` |
| Ops status snapshot | `reports/ops_status.json` |
| Metrics ledger | `reports/ops_metrics.jsonl` |
| Ops alerts | `reports/ops_alerts.jsonl` |

## 2. Everyday commands

```bash
# Foreground start (systemd / Task Scheduler / launchd normally invokes this).
python scripts/nexaquant_daemon.py start

# Status summary as JSON.
python scripts/nexaquant_daemon.py status

# Health check (runs MON001 sealed health module, no daemon required).
python scripts/nexaquant_daemon.py health

# Graceful stop with 30s timeout.
python scripts/nexaquant_daemon.py stop

# stop + start.
python scripts/nexaquant_daemon.py restart
```

## 3. Linux (systemd)

```bash
# Install
sudo cp deploy/systemd/nexaquant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nexaquant

# Watch
sudo systemctl status nexaquant
sudo journalctl -u nexaquant -f          # JSON per line

# Restart
sudo systemctl restart nexaquant
```

## 4. Windows (Task Scheduler)

```powershell
# Install (edit UserId + paths in deploy/task-scheduler/nexaquant.xml first)
schtasks /Create /TN "NexaQuant Ops Daemon" /XML deploy\task-scheduler\nexaquant.xml

# Start
schtasks /Run /TN "NexaQuant Ops Daemon"

# Stop
python scripts\nexaquant_daemon.py stop
```

## 5. macOS (launchd)

```bash
cp deploy/launchd/com.nexaquant.ops.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.nexaquant.ops.plist
launchctl list | grep nexaquant
```

## 6. Reading the JSON logs

Each line is one event. Common event names:

| Event | Emitted when |
|---|---|
| `daemon_started` | After lock acquired, before loop begins |
| `recovery_decision` | Prior run state was non-idle |
| `slot_firing` | A slot's fire window is open and it hasn't fired today |
| `slot_completed` | Pipeline returned 0 |
| `slot_pipeline_failure` | Pipeline returned 1 |
| `slot_framework_error` | Unexpected exception during a slot |
| `shutdown_signal` | SIGTERM / SIGINT / SIGBREAK received |
| `daemon_exited` | Loop returned; lock about to release |

Filter for one slot:

```bash
jq -c 'select(.slot=="primary_1615_ist")' reports/logs/nexaquant_ops.jsonl
```

## 7. Interpreting `status` output

```json
{
  "daemon_running": true,
  "lock_holder": {"pid": 12345, "started_utc": "2026-07-16T10:44:00+00:00", ...},
  "slots": [
    {"name": "primary_1615_ist", "last_fired_utc": "2026-07-16T10:45:12+00:00"},
    ...
  ],
  "next_run_utc": "2026-07-17T10:45:00+00:00",
  "ops_status_snapshot": {"mon001_state": "OK", "mon001_halt": false, ...}
}
```

- **`daemon_running: false`** → no daemon holds the lock. Start it.
- **`daemon_running: true` but `last_fired_utc` is old** → daemon is up but
  hasn't hit a fire window. Compare against `next_run_utc`.
- **`ops_status_snapshot.mon001_halt: true`** → MON001 has flagged the strategy.
  Investigate MON001 alerts (`reports/ops_alerts.jsonl` + MON001 dashboard).

## 8. Common failure signatures

| Symptom | Likely cause | Fix |
|---|---|---|
| `pid_lock_held — another daemon is already running` on start | Previous daemon didn't release lock. | `stop` then `start` — the CLI will remove stale locks. |
| Log records stop appearing but daemon reports `daemon_running: true` | Slot's fire window has passed for the day. | Wait for next slot or trigger manually (see §9). |
| `slot_framework_error` on every fire | Import failure or config drift. | Read `traceback` field in the log record; compare imports to `nexaquant/ops/service.py`. |
| Telegram alerts stop | Bot token rotation or chat-id change. | Run `python scripts/telegram_health_check.py`. |

## 9. Manual pipeline trigger (bypasses schedule)

Not needed under normal operation. If required — e.g., testing after an
amendment — invoke OPS001-A's single-shot entrypoint directly:

```bash
python scripts/nexaquant_service.py --no-telegram    # single pass, no notifier
python scripts/nexaquant_service.py                  # single pass with Telegram
```

This does NOT touch the daemon's PID lock or schedule state.

## 10. Rotating a broken run_state

If `reports/ops_run_state.json` is corrupt (e.g., partial write during a crash):

```bash
# Safe — the daemon will treat missing file as IDLE.
mv reports/ops_run_state.json reports/ops_run_state.json.corrupt.$(date +%s)
```

Next daemon start emits `recovery_decision NONE`.

## 11. Rotating a broken schedule state

```bash
# Safe — daemon will treat missing file as "no slot has fired today".
# Impact: today's already-fired slots may re-fire once more if their window
# is still open.
mv reports/ops_schedule_state.json reports/ops_schedule_state.json.bak
```

## 12. What you MUST NOT touch

- `india/monitoring/MON001_Forward_Validation/**` (sealed).
- `india/recommendation_registry.py`, `india/recommendation_generator.py`,
  `india/confidence_engine.py`, `india/arjuna_v2.py`, `india/data_nse.py` (sealed).
- `india/ai_lab/**` (LAB evidence, sealed).
- `docs/MON001_CERTIFICATION.md` unless explicitly running a certification
  amendment ceremony.

## 13. Escalation

If health check returns non-zero AND MON001 halt is asserted:

1. Do not restart the daemon aggressively.
2. Read `reports/logs/nexaquant_ops.jsonl` (last 500 lines).
3. Read `india/monitoring/MON001_Forward_Validation/reports/dashboard_$(date +%F).md`.
4. Follow `docs/RECOVERY.md`.
