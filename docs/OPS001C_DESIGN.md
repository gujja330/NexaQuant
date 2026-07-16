# OPS001-C · Design

**Version:** 0.1.0-ops001b (notify subsystem shipped as OPS001-C) · **Predecessor:** OPS001-B

## 1. Goal

Extend the notification bus from OPS001-A (Telegram + File) into an
enterprise-grade multi-channel notification manager with routing rules,
escalation policies, retry queue + DLQ, alert history, dashboard, and
health APIs. Add CLI subcommands so operators can drive the subsystem
without writing code.

## 2. Non-goals

- No production strategy behaviour change.
- No MON001 sealed file modification.
- No LAB artefact modification.
- No GitHub Actions workflow change.

## 3. New modules under `nexaquant/ops/notify/`

| Module | Role |
|---|---|
| `email.py` | SMTP channel (stdlib `smtplib`). Reads `NEXAQUANT_SMTP_*` env vars. |
| `slack.py` | Slack Incoming Webhook channel. Reads `NEXAQUANT_SLACK_WEBHOOK_URL`. |
| `discord.py` | Discord webhook channel. Reads `NEXAQUANT_DISCORD_WEBHOOK_URL`. |
| `webhook.py` | Generic HTTP POST channel. Reads `NEXAQUANT_WEBHOOK_URL` + headers. |
| `templates.py` | 8 canonical templates (pipeline success/failure, MON001 halt, commissioning failure, daemon restart, recovery event, daily / weekly summary). |
| `routing.py` | `RoutingPolicy` + escalation config. `INFO -> file`; `WARN -> telegram, file`; `ERROR -> telegram, email, file`; `CRITICAL -> telegram, email, slack, discord, webhook, file`. |
| `retry_queue.py` | Persistent JSONL queue + DLQ + exponential backoff. Public `RetryQueue` + `process_queue()`. |
| `history.py` | JSONL alert history reader + CSV export + markdown summary. |
| `dashboard.py` | Aggregates pending / delivered / DLQ into per-channel stats + markdown render. |
| `health.py` | `notification_status()`, `delivery_metrics()`, `channel_health()`. |

## 4. Severity ladder extension

`events.Severity` now includes `ERROR` between `WARN` and `CRITICAL`:

```
INFO (0) < WARN (1) < ERROR (2) < CRITICAL (3)
```

The `accepts()` order dict in `nexaquant/ops/notify/base.py` was updated
accordingly. Existing OPS001-A callers pass `INFO`, `WARN`, or `CRITICAL`;
the extension does not break them.

## 5. Channels

Every channel implements the OPS001-A `NotificationChannel` interface:

- `name` (property): stable string identifier for routing lookups.
- `min_severity` (property): filter threshold; below → `accepts()` returns False.
- `configured` (property): True iff env config is complete enough to send.
- `send(notification) -> bool`: attempt delivery. **Must not raise.** Return
  False on any failure; the manager and retry queue treat False identically.

Every remote channel (`email`, `slack`, `discord`, `webhook`) returns
`configured=False` when env config is absent and short-circuits `send()`
to `False`. The bus keeps working, falling through to `FileChannel`.

## 6. Routing policy

`RoutingPolicy` is a plain dict `{"SEVERITY": ["channel_name", ...]}`. Default:

| Severity | Channels |
|---|---|
| INFO | file |
| WARN | telegram, file |
| ERROR | telegram, email, file |
| CRITICAL | telegram, email, slack, discord, webhook, file |

Overrides via `RoutingPolicy.from_dict({...})`. `include_file_fallback=True`
(the default) guarantees `file` is always present — the durable audit
trail can never be routed away.

`resolve_channels(policy, available, severity)` intersects the policy with
the operator's actually-wired channels and returns an ORDERED list.

## 7. Escalation

Escalation is expressed as the same per-severity list. The default
semantics is `require_all=True` (fan-out), which matches the spec:
CRITICAL sends to every channel. Sequential-fallback escalation
(`stop after first success`) is available by setting `require_all=False`
on an `EscalationPolicy`.

The current implementation uses `require_all` semantics for OPS001-C.
Sequential fallback is reserved for OPS002.

## 8. Templates

Eight prebuilt templates in `templates.py`, all returning `Notification`
objects with a consistent context shape:

- `pipeline_success` — INFO
- `pipeline_failure` — ERROR
- `mon001_halt` — CRITICAL
- `commissioning_failure` — ERROR
- `daemon_restart` — WARN
- `recovery_event` — WARN
- `daily_summary` — INFO (escalates to WARN if any pipeline failed OR any alert in window)
- `weekly_summary` — INFO (escalates on halts / criticals)

Templates are pure — no network, no filesystem — so they are safe to unit-test.

## 9. Retry queue + DLQ

Persistent JSONL under `reports/`:

- `ops_notify_queue.jsonl` — pending retries
- `ops_notify_delivered.jsonl` — successfully delivered after retry
- `ops_notify_dlq.jsonl` — dead-letter (max_attempts exceeded)

Backoff (`QueueEntry.backoff_for_attempt(idx)`):

```
delay = min(initial_backoff_s * (multiplier ^ (idx-1)), max_backoff_s)
```

Defaults: `initial=30s`, `multiplier=2`, `max=1800s`, `max_attempts=5`.

`process_queue(queue, channels, max_dispatch=50)` drains ready entries.
For each: look up channel by name → `send()` → on True `mark_delivered()`,
on False `mark_failed()`, which either re-schedules or moves to DLQ.

**Concurrency model:** single-writer. The daemon owns the queue. If the
CLI's `notify retry` is invoked while the daemon is running, entries can
be processed twice. This is documented; OPS002 will add advisory locking.

## 10. Alert history

`history.py` reads the append-only `ops_alerts.jsonl` (already written by
`FileChannel` since OPS001-A). Provides:

- `load_history(path, HistoryFilter)` — filter by severity / source_prefix / time window
- `to_csv(rows)` — CSV export with fixed columns + JSON `context` column
- `markdown_summary(rows, title=...)` — counts by severity + top sources + recent CRITICAL events

## 11. Dashboard

`build_dashboard(alerts_jsonl, queue_path, dlq_path, delivered_path)`
returns a dict:

- `totals`: alerts_recorded, pending_retries, delivered_via_retry, dead_letter
- `alerts_by_severity`: INFO / WARN / ERROR / CRITICAL counts
- `per_channel`: rows with pending / delivered / failed_to_dlq / total_retry_attempts / last_success_utc / last_failure_utc

`dashboard_markdown(snapshot)` renders the dict as a markdown table
suitable for a daily ops digest.

## 12. Health APIs

- `notification_status(...)` → `{status: OK|DEGRADED, ...}` (DEGRADED iff any DLQ entry present).
- `delivery_metrics(..., window_hours=24)` → alerts count + per-severity breakdown for a rolling window.
- `channel_health(channels)` → per-channel `{name, configured, min_severity, class}` rows.

## 13. CLI extensions (`nexaquant/ops/cli.py`)

New subgroup `notify`:

```
nexaquant-ops notify test [--severity INFO|WARN|ERROR|CRITICAL] [--message ...]
nexaquant-ops notify status
nexaquant-ops notify retry [--max-dispatch N]
nexaquant-ops notify history [--format json|csv|markdown] [--since-hours N]
nexaquant-ops notify purge [--yes]
```

All commands return JSON (except `history --format=csv|markdown`).

## 14. Environment variables

Only used when the corresponding channel is desired:

| Channel | Env vars |
|---|---|
| email | `NEXAQUANT_SMTP_HOST`, `NEXAQUANT_SMTP_PORT`, `NEXAQUANT_SMTP_USER`, `NEXAQUANT_SMTP_PASSWORD`, `NEXAQUANT_SMTP_FROM`, `NEXAQUANT_SMTP_TO`, `NEXAQUANT_SMTP_USE_TLS` |
| slack | `NEXAQUANT_SLACK_WEBHOOK_URL` |
| discord | `NEXAQUANT_DISCORD_WEBHOOK_URL` |
| webhook | `NEXAQUANT_WEBHOOK_URL`, `NEXAQUANT_WEBHOOK_METHOD`, `NEXAQUANT_WEBHOOK_HEADERS`, `NEXAQUANT_WEBHOOK_AUTH_HEADER` |
| telegram | (already documented in OPS001-A) `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |

Every value is read at channel construction time.

## 15. Files touched (all additive)

- Added: `email.py`, `slack.py`, `discord.py`, `webhook.py`, `templates.py`,
  `routing.py`, `retry_queue.py`, `history.py`, `dashboard.py`, `health.py`
  under `nexaquant/ops/notify/`
- Added: `nexaquant/tests/test_ops_notify.py`
- Modified: `nexaquant/ops/events.py` (added `Severity.ERROR`)
- Modified: `nexaquant/ops/notify/base.py` (extended `accepts()` order dict)
- Modified: `nexaquant/ops/cli.py` (added `notify` subgroup)
- Modified: `nexaquant/tests/test_regression.py` (registered OPS001-C suite)

**No sealed file changed. No LAB file changed. MON001 fingerprint
`64e74483d9bd0444...` unchanged.**

## 16. Testing

`nexaquant/tests/test_ops_notify.py` — 32 scenarios:

- 6 tests: severity extension + channel wiring (email, slack, discord, webhook)
- 6 tests: templates (all 8 kinds exercised)
- 3 tests: routing policy + resolve_channels
- 5 tests: retry queue + DLQ + process_queue happy / unroutable paths
- 4 tests: history + dashboard + health APIs
- 1 test: manager severity gating with the new ERROR tier
- 2 tests: CLI dispatcher registers all 5 notify subcommands + integration
- 3 tests: governance (sealed / LAB / fingerprint / constants)

Registered as regression suite `OPS001-C notify`.

## 17. Backward compatibility

- OPS001-A callers keep working (they instantiate `FileChannel` +
  `TelegramChannel` explicitly; new channels are opt-in).
- OPS001-B daemon unchanged (does not consume the new subsystem yet;
  daemon integration will move via `OPS001-B` incremental update or
  explicit operator action).
- Existing tests continue to PASS.

## 18. Out of scope for OPS001-C

- Slack Bolt / OAuth-based Slack Apps (webhook only).
- PagerDuty / Opsgenie integrations (add via generic webhook for now).
- Multi-tenant routing (single deployment).
- Notification persistence guarantees beyond `flush`. If a `send()` returns
  True, the delivery is considered final. Retry only fires on `False`.
