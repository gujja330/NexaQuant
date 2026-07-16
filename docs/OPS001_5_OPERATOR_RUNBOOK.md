# OPS001.5 · Operator Runbook

Short, actionable playbook for the human running NexaQuant. Read this once
end-to-end. Then keep it open when things break.

> If you are unsure whether an action is safe, stop and consult
> [`docs/CHANGE_CONTROL_CHECKLIST.md`](CHANGE_CONTROL_CHECKLIST.md).
> Never delete sealed files. Never edit MON001 core. Never `--no-verify`.

## 1. Daily rhythm

The daemon fires the AEGIS pipeline three times per weekday (IST):

| Slot | IST | UTC | Purpose |
|---|:-:|:-:|---|
| `primary_1615_ist` | 16:15 | 10:45 | Post-close + settle buffer |
| `backup_1830_ist` | 18:30 | 13:00 | Retry if primary missed |
| `backup_2100_ist` | 21:00 | 15:30 | Last chance same IST day |

Each slot fires at most once per calendar IST day. `ops_schedule_state.json`
enforces the dedup. If the primary succeeds, the backups are silent.

## 2. Daily checks (60 seconds)

```bash
# 1. Daemon alive?
python scripts/nexaquant_daemon.py status | jq '.daemon_running, .next_run_utc'

# 2. Latest MON001 dashboard is today's?
ls -1t india/monitoring/MON001_Forward_Validation/reports/dashboard_*.md | head -1

# 3. Any active alerts?
tail -5 reports/ops_alerts.jsonl
```

**GREEN if:** `daemon_running: true`, latest dashboard matches today's IST
date, no CRITICAL alerts in last 24h.

## 3. Weekly checks (5 minutes)

```bash
# 1. Full regression must be green.
python nexaquant/tests/test_regression.py

# 2. Commissioning canary.
python nexaquant/tests/test_ops_commissioning.py

# 3. MON001 health check.
python -m india.monitoring.MON001_Forward_Validation.ops.health_check
```

**GREEN if:** all three exit 0.

## 4. Common tasks

### 4.1 Start the daemon

```bash
# Linux
sudo systemctl start nexaquant

# Windows
schtasks /Run /TN "NexaQuant Ops Daemon"

# Manual foreground (for debugging)
python scripts/nexaquant_daemon.py start
```

### 4.2 Stop the daemon

```bash
# Linux
sudo systemctl stop nexaquant

# Windows
python scripts\nexaquant_daemon.py stop --timeout 60

# Manual
python scripts/nexaquant_daemon.py stop
```

### 4.3 Restart the daemon

```bash
# Linux
sudo systemctl restart nexaquant

# Manual
python scripts/nexaquant_daemon.py restart
```

### 4.4 Force a manual pipeline run (bypasses schedule)

```bash
python scripts/nexaquant_service.py            # with Telegram
python scripts/nexaquant_service.py --no-telegram   # dry run
```

This does NOT touch the daemon's schedule state, so the next scheduled slot
still fires. Use this only for one-off recovery scenarios.

### 4.5 View recent log events

```bash
# Last 50 events as pretty JSON.
tail -50 reports/logs/nexaquant_ops.jsonl | jq .

# Only slot-related events.
jq -c 'select(.event | startswith("slot_"))' reports/logs/nexaquant_ops.jsonl | tail -20

# Only errors.
jq -c 'select(.level=="ERROR")' reports/logs/nexaquant_ops.jsonl | tail -20
```

### 4.6 Verify MON001 seal still intact

```bash
python -c "
from india.monitoring.MON001_Forward_Validation.fingerprint import compute_fingerprint
from pathlib import Path
import yaml, json
ROOT = Path('.')
with (ROOT / 'india/monitoring/MON001_Forward_Validation/mon001.yaml').open() as f:
    cfg = yaml.safe_load(f)
sealed = json.loads((ROOT / 'india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json').read_text())
current = compute_fingerprint(ROOT, cfg['baseline_files'], cfg['baseline_constants'])
print('MATCH' if current['hash']==sealed['hash'] else 'DRIFT', current['hash'][:16]+'...')
"
```

Expected output: `MATCH 64e74483d9bd0444...`

## 5. Symptom playbook

| Symptom | First move | Second move |
|---|---|---|
| No Telegram alert today | `python scripts/telegram_health_check.py` | Check `reports/logs/nexaquant_ops.jsonl` for `slot_pipeline_failure` |
| Dashboard file has yesterday's date | `python scripts/nexaquant_daemon.py status` — is the daemon running? | If yes, force a manual pipeline run (§4.4) |
| Log file stopped growing | `df -h` — disk full? | `python scripts/nexaquant_daemon.py restart` |
| `pid_lock_held` on start | Previous daemon didn't release | `python scripts/nexaquant_daemon.py stop` (removes stale lock) then start |
| Health check reports HALT | STOP the daemon. Do NOT restart. | Read the failing check's `detail` field. Follow [`docs/OPS001B_RECOVERY.md`](OPS001B_RECOVERY.md) §5 |
| MON001 fingerprint mismatch | STOP the daemon. Do NOT restart. | Was there an edit to a sealed file? `git diff` against seal commit |
| Commissioning suite failed | Read `[FAIL]` line in output | Isolate that subsystem — SUB-N corresponds to a specific module |
| CI red on push | Read the CI log for the failing suite | Never `--no-verify` — fix the root cause |

## 6. When to escalate

Escalate to Principal (owner) when ANY of the following holds:

- MON001 fingerprint mismatch on a fresh checkout of `main`.
- Commissioning suite fails on the same subsystem twice in a row.
- `reports/logs/nexaquant_ops.jsonl` shows `slot_framework_error` on every fire.
- Telegram delivery has been silent for > 24h despite `telegram_health_check.py` passing.
- Any suggestion to modify a sealed file to "fix" a failure.

Do NOT take unilateral action on any of the above.

## 7. Never do

- Never `git push --force` to `main`.
- Never commit with `--no-verify`.
- Never delete `india/monitoring/MON001_Forward_Validation/**`.
- Never delete `india/ai_lab/**`.
- Never edit `reports/baseline_envelope_2026-07-13.json` by hand.
- Never edit `india/monitoring/MON001_Forward_Validation/reports/sealed_fingerprint.json`.
- Never edit `india/monitoring/MON001_Forward_Validation/reports/forward_ledger.jsonl` in place.
- Never bypass the daemon's PID lock by deleting the lock file while the daemon is up.
- Never share broker credentials, Telegram bot tokens, or any secret in chat/PRs/logs.

## 8. Reference index

- [`docs/OPS001B_DESIGN.md`](OPS001B_DESIGN.md) — daemon architecture
- [`docs/OPS001B_OPERATIONS.md`](OPS001B_OPERATIONS.md) — day-to-day ops
- [`docs/OPS001B_DEPLOYMENT.md`](OPS001B_DEPLOYMENT.md) — install/upgrade
- [`docs/OPS001B_RECOVERY.md`](OPS001B_RECOVERY.md) — symptom → decision matrix
- [`docs/OPS001_5_ACCEPTANCE_CHECKLIST.md`](OPS001_5_ACCEPTANCE_CHECKLIST.md) — sign-off checklist
- [`docs/OPS001_5_DEPLOYMENT_VALIDATION.md`](OPS001_5_DEPLOYMENT_VALIDATION.md) — install-time validation
- [`docs/OPS001_5_COMMISSIONING_REPORT.md`](OPS001_5_COMMISSIONING_REPORT.md) — audit record
- [`docs/MON001_CERTIFICATION.md`](MON001_CERTIFICATION.md) — sealed certification + amendment history
- [`docs/CHANGE_CONTROL_CHECKLIST.md`](CHANGE_CONTROL_CHECKLIST.md) — governance
