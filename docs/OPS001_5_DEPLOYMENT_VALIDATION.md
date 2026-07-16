# OPS001.5 · Deployment Validation

Post-install checks that a deployed NexaQuant daemon is ready to run
unattended for months. Run these on the target host BEFORE handing the
system to production traffic (or as a scheduled canary).

## 1. What "validated deployment" means

A deployment is validated when **every one of the following holds**:

1. `python nexaquant/tests/test_ops_commissioning.py` → 23 / 23 PASS
2. `python nexaquant/tests/test_regression.py` → all suites PASS, all invariance guards hold
3. `python scripts/nexaquant_daemon.py health` → exit 0, all MON001 checks INFO
4. `python scripts/telegram_health_check.py` → OK
5. `python scripts/nexaquant_daemon.py status` → `daemon_running: true`, `next_run_utc` in the future
6. MON001 fingerprint on host equals `64e74483d9bd044402da8f5936e1d2fea5e560628a28999a9f8a1a7e260b7b42`
7. Ops daemon systemd unit / Task Scheduler task / launchd agent enabled and running
8. One scheduled slot has fired successfully (observe `slot_completed` event in `reports/logs/nexaquant_ops.jsonl`)
9. Latest MON001 daily dashboard written (`india/monitoring/MON001_Forward_Validation/reports/dashboard_YYYY-MM-DD.md` matches today's date)
10. Latest AEGIS `asof` matches today's IST trading date (`reports/ops_status.json.recommendation_last_asof`)

If any of the ten above fails → **do NOT declare the deployment validated.**
Follow [`docs/OPS001B_RECOVERY.md`](OPS001B_RECOVERY.md) to isolate the failing subsystem.

## 2. Cold-boot validation

Simulate a fresh install from scratch to verify no hidden dependency on
pre-existing state:

```bash
# 1. Wipe writable state (WARNING: destroys local logs + status).
mv reports reports.snapshot.$(date +%s)

# 2. Start daemon.
python scripts/nexaquant_daemon.py start   # foreground; use systemd/Task Scheduler for daemon mode

# 3. In another shell, confirm:
python scripts/nexaquant_daemon.py status   # daemon_running: true

# 4. Force one fire (only if a slot's window is currently open):
#    the daemon will fire the next due slot automatically within poll_interval_s (default 30s).

# 5. Confirm log file is being written:
tail -f reports/logs/nexaquant_ops.jsonl
```

**PASS criterion:** all 10 items in §1 hold after cold boot.

## 3. Restart validation

```bash
python scripts/nexaquant_daemon.py stop --timeout 60
python scripts/nexaquant_daemon.py status              # daemon_running: false, lock cleared
python scripts/nexaquant_daemon.py start
python scripts/nexaquant_daemon.py status              # daemon_running: true
```

**PASS criterion:** stop returns 0, lock removed, start returns without
error, subsequent status confirms daemon is up.

## 4. Recovery validation

Deliberately corrupt state and observe the daemon's recovery path.

### 4.1 Stale lock

```bash
python scripts/nexaquant_daemon.py stop
# Simulate a leftover from a crashed daemon:
python -c "
import json
from datetime import datetime, timedelta, timezone
open('reports/ops_daemon.lock', 'w').write(json.dumps({
    'pid': 999999999,
    'started_utc': (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat(),
    'host': 'crashed-host', 'cmdline': 'died',
}))
"
python scripts/nexaquant_daemon.py start &
sleep 5
python scripts/nexaquant_daemon.py status              # daemon_running: true (stale lock was broken)
```

**PASS criterion:** daemon started (SUB-19 subsystem verified this behaviour).

### 4.2 Interrupted pipeline recovery

If a daemon exits mid-pipeline, `reports/ops_run_state.json` remains at
`phase=running`. Next start emits a `WARN recovery_decision` event and
re-fires on the next due slot.

```bash
# Inspect current run_state.
cat reports/ops_run_state.json
```

**PASS criterion:** `phase == "completed"` under steady-state operation; any
other phase should be transient (RUNNING mid-pipeline, or a WARN emitted at
next start followed by clean recovery).

## 5. Governance validation

```bash
python nexaquant/tests/test_governance.py
python -m india.monitoring.MON001_Forward_Validation.ops.health_check
```

**PASS criterion:** both exit 0. Health check reports every check as `INFO`.

## 6. Continuous validation (weekly canary)

Schedule the commissioning suite as a weekly canary. Add to the operator's
crontab / Task Scheduler (separately from the daemon):

```
# Sunday 09:00 IST canary — commissioning suite.
0 3 * * 0    cd /opt/nexaquant && python nexaquant/tests/test_ops_commissioning.py \
             > reports/logs/commissioning_$(date +%F).log 2>&1
```

**PASS criterion:** exit code 0 every week. If any commissioning canary fails,
follow [`docs/OPS001B_RECOVERY.md`](OPS001B_RECOVERY.md) and open an incident.

## 7. Prohibited "validations"

The following do NOT constitute validation:

- "The dashboard file has today's date" alone (says nothing about pipeline success).
- "Telegram sent one message" alone (message could have wrong asof).
- "Daemon is running" alone (may be idle awaiting a slot that will never fire due to config drift).
- Manual `python -c "import nexaquant.ops"` (imports pass on a broken deployment).

Only §1 items 1-10 together constitute validation. Cherry-picking is not permitted.

## 8. What deployment validation does NOT cover

- Strategy correctness. That's `MON001-CERT-2026-07-15`, unchanged since
  the portability amendment.
- Broker connectivity. NexaQuant is currently PAPER_ONLY per `broker_layer.py`.
  If a future ENG phase enables broker orders, that validation lives in ENG003.
- Host resource capacity planning. This document assumes the host has
  ≥ 2 GB RAM, ≥ 20 GB disk, and stable network access to NSE data providers.
