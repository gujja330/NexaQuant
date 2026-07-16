# OPS001-C · Notifications Operator Guide

Day-to-day guide for the human operating the NexaQuant notification bus.
Companion to `docs/OPS001C_DESIGN.md` (architecture).

## 1. What lives where

| Channel | Env vars | Class |
|---|---|---|
| **file** | (none — always on) | `nexaquant.ops.notify.file.FileChannel` |
| **telegram** | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `nexaquant.ops.notify.telegram.TelegramChannel` |
| **email** | `NEXAQUANT_SMTP_*` | `nexaquant.ops.notify.email.EmailChannel` |
| **slack** | `NEXAQUANT_SLACK_WEBHOOK_URL` | `nexaquant.ops.notify.slack.SlackChannel` |
| **discord** | `NEXAQUANT_DISCORD_WEBHOOK_URL` | `nexaquant.ops.notify.discord.DiscordChannel` |
| **webhook** | `NEXAQUANT_WEBHOOK_URL` (+ headers) | `nexaquant.ops.notify.webhook.WebhookChannel` |

Runtime state files (all under `reports/`):

| File | What |
|---|---|
| `ops_alerts.jsonl` | Every emitted notification (durable audit log) |
| `ops_notify_queue.jsonl` | Pending retries |
| `ops_notify_delivered.jsonl` | Deliveries that succeeded on retry |
| `ops_notify_dlq.jsonl` | Dead-letter — retry exhausted |

## 2. Set up a channel

### 2.1 Telegram (already covered in OPS001-A)

```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
python scripts/telegram_health_check.py    # verify
```

### 2.2 Email (SMTP)

Recommend a dedicated app-specific password on Gmail / Outlook / Fastmail.

```bash
export NEXAQUANT_SMTP_HOST="smtp.gmail.com"
export NEXAQUANT_SMTP_PORT="587"
export NEXAQUANT_SMTP_USER="ops-bot@yourdomain"
export NEXAQUANT_SMTP_PASSWORD="app-password"
export NEXAQUANT_SMTP_FROM="ops-bot@yourdomain"
export NEXAQUANT_SMTP_TO="you@yourdomain,team@yourdomain"
# STARTTLS is on by default; set to 0 to disable.
export NEXAQUANT_SMTP_USE_TLS="1"

python scripts/nexaquant_daemon.py notify test --severity ERROR --message "email verify"
```

### 2.3 Slack (Incoming Webhook)

Create an app → Add Incoming Webhook → paste the URL.

```bash
export NEXAQUANT_SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../..."
python scripts/nexaquant_daemon.py notify test --severity CRITICAL
```

### 2.4 Discord (Webhook)

Channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL.

```bash
export NEXAQUANT_DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/.../..."
python scripts/nexaquant_daemon.py notify test --severity CRITICAL
```

### 2.5 Generic HTTP webhook (Opsgenie, PagerDuty, custom endpoint)

```bash
export NEXAQUANT_WEBHOOK_URL="https://api.opsgenie.com/v2/alerts"
export NEXAQUANT_WEBHOOK_METHOD="POST"
export NEXAQUANT_WEBHOOK_AUTH_HEADER="Authorization: GenieKey ..."
python scripts/nexaquant_daemon.py notify test --severity CRITICAL
```

## 3. Escalation defaults

| Severity | Channels |
|---|---|
| INFO | file (audit only) |
| WARN | telegram, file |
| ERROR | telegram, email, file |
| CRITICAL | telegram, email, slack, discord, webhook, file |

**Unconfigured channels are silently skipped.** If you haven't set up
Slack/Discord/Webhook, CRITICAL still lands in Telegram + Email + file.

## 4. Templates you can emit from your code

```python
from nexaquant.ops.notify import templates as tmpl

n = tmpl.pipeline_success(pipeline="aegis_daily", duration_s=12.5,
                          stages_ok=9, stages_total=9, asof="2026-07-16")

n = tmpl.pipeline_failure(pipeline="aegis_daily",
                          failed_stage="recommendation_generator",
                          reason="ValueError: no rows",
                          stages_ok=2, stages_total=9, exit_code=1)

n = tmpl.mon001_halt(dimension="fingerprint_matches_seal",
                     detail="CONFIG_DRIFT: 64e747... != current abc123...",
                     fingerprint_hash="64e74483d9bd0444...")

n = tmpl.commissioning_failure(subsystem="SUB-17 health endpoint",
                               reason="MON001 worst_severity=HALT")

n = tmpl.daemon_restart(reason="operator", uptime_s=3600.5,
                        ops_version="0.1.0-ops001b")

n = tmpl.recovery_event(previous_phase="running", action="RESUME",
                        reason="mid-pipeline SIGTERM",
                        slot_name="primary_1615_ist")

n = tmpl.daily_summary(asof="2026-07-16", pipelines_ok=1, pipelines_total=1,
                       mon001_state="OK", alerts_last_24h=0)

n = tmpl.weekly_summary(week_ending_asof="2026-07-11", trading_days=5,
                        pipelines_ok=5, pipelines_total=5,
                        mon001_halts=0, critical_alerts=0)
```

All eight return a `Notification` with a consistent `context["kind"]` field
so downstream automations can filter without parsing the title.

## 5. Sending a notification

```python
from nexaquant.ops.notify.manager import NotificationManager
from nexaquant.ops.notify.file import FileChannel
from nexaquant.ops.notify.telegram import TelegramChannel
from nexaquant.ops.notify.email import EmailChannel
from nexaquant.ops.notify.slack import SlackChannel
from nexaquant.ops.notify.discord import DiscordChannel
from nexaquant.ops.notify.webhook import WebhookChannel
from pathlib import Path

mgr = NotificationManager(channels=[
    FileChannel(Path("reports/ops_alerts.jsonl")),
    TelegramChannel(),
    EmailChannel(),
    SlackChannel(),
    DiscordChannel(),
    WebhookChannel(),
])
results = mgr.emit(n)      # returns list[DeliveryResult]
```

If a `send()` call raises, the manager catches and continues — no channel
can block the others.

## 6. Retry queue

For channels that returned False on `send()`, enqueue for retry:

```python
from pathlib import Path
from nexaquant.ops.notify.retry_queue import RetryQueue

q = RetryQueue(queue_path=Path("reports/ops_notify_queue.jsonl"),
               dlq_path=Path("reports/ops_notify_dlq.jsonl"),
               delivered_path=Path("reports/ops_notify_delivered.jsonl"))

for r in results:
    if r.accepted and not r.ok:
        q.enqueue(n, channel=r.channel)
```

Drain the queue periodically:

```bash
python scripts/nexaquant_daemon.py notify retry
```

The daemon can call this automatically on each tick (future OPS002 wiring;
for now it's an operator-driven CLI call).

## 7. CLI recipes

```bash
# Send a canary notification through every configured channel.
python scripts/nexaquant_daemon.py notify test --severity CRITICAL --message "canary"

# Print subsystem health as JSON.
python scripts/nexaquant_daemon.py notify status

# Process retry queue once (up to 50 entries).
python scripts/nexaquant_daemon.py notify retry --max-dispatch 50

# Export last 24h as CSV.
python scripts/nexaquant_daemon.py notify history --format csv --since-hours 24

# Print a markdown summary of last week.
python scripts/nexaquant_daemon.py notify history --format markdown --since-hours 168

# Purge delivered ledger + DLQ (destructive; use --yes to confirm).
python scripts/nexaquant_daemon.py notify purge --yes
```

## 8. Symptom → move

| Symptom | Move |
|---|---|
| `notify status` shows `status: DEGRADED` and `dead_letter > 0` | Inspect DLQ: `cat reports/ops_notify_dlq.jsonl \| jq .`. Fix the failing channel, then `notify purge --yes` if the DLQ is stale. |
| Email never delivers, no error in logs | Check `NEXAQUANT_SMTP_*` are exported in the daemon's env. `EmailChannel.configured` must be True. |
| Slack posts arrive but Discord doesn't | Discord webhook URL invalid — regenerate and re-export `NEXAQUANT_DISCORD_WEBHOOK_URL`. |
| Retry queue grows unboundedly | A channel is returning False every time. Check `retry` output for `moved_to_dlq` counts; once at `max_attempts` the entry moves to DLQ. |
| `notify test` fails only on webhook | Check `NEXAQUANT_WEBHOOK_URL` scheme (must be http:// or https://) and auth header format. |

## 9. Retention

The audit log `ops_alerts.jsonl` is APPEND-ONLY and never pruned. Rotate
it yourself with `logrotate` if it grows too large:

```
# /etc/logrotate.d/nexaquant-alerts
/opt/nexaquant/reports/ops_alerts.jsonl {
    monthly
    rotate 24
    compress
    missingok
    notifempty
    copytruncate
}
```

The retry queue's delivered ledger and DLQ can be purged safely with
`notify purge --yes` — they exist for audit, not for functional retries.

## 10. What OPS001-C does NOT change

- No production strategy logic.
- No MON001 sealed file.
- No LAB artefact.
- No GitHub Actions workflow.
- No existing pipeline behaviour.
- `cumulative_strategy_search` is still 38.
