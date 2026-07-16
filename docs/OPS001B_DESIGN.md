# OPS001-B · Design

**Version:** 0.1.0-ops001b · **Status:** shipped · **Predecessor:** OPS001-A

## 1. Goal

Turn NexaQuant from a GitHub-Actions-cron script into a resilient always-on
service that a Linux systemd unit, Windows Task Scheduler task, or macOS
launchd agent can supervise.

## 2. Non-goals

- No production strategy behaviour change (HOLD, rebal, HRP, scoring, exits,
  portfolio construction, cumulative_strategy_search).
- No MON001 sealed file modification.
- No LAB artefact modification.
- No self-daemonization (`fork` + `setsid`). The daemon is a foreground
  process; the supervisor (systemd / Task Scheduler / launchd) provides
  restart-on-failure.

## 3. Modules

| Module | Purpose |
|---|---|
| `nexaquant/ops/logging_setup.py` | Structured JSON logs with size-based rotation + retention pruning |
| `nexaquant/ops/pidlock.py` | Daemon-scope PID lock with stale detection (dead pid + age) |
| `nexaquant/ops/monitoring.py` | Uptime / memory / CPU / open-files snapshot (psutil preferred, resource fallback, minimal fallback) |
| `nexaquant/ops/scheduler.py` | Slot-based schedule (hour/minute × weekday × tz-offset), fire-window + same-day deduplication |
| `nexaquant/ops/recovery.py` | Interrupted-pipeline recovery (`RunState` + `RecoveryDecision`) |
| `nexaquant/ops/daemon.py` | Main polling loop, signal handling, per-slot execution wiring |
| `nexaquant/ops/cli.py` | `start` / `stop` / `restart` / `status` / `health` subcommands |
| `scripts/nexaquant_daemon.py` | Thin entrypoint invoked by supervisors |

## 4. Lifecycle

```
supervisor           daemon                        pipeline (OPS001-A)
─────────────────────────────────────────────────────────────────────
systemd start  ─▶   PidLock.acquire()  ─▶   (nothing until slot due)
                    handle_recovery()       (inspect prior RunState)
                    while not stop:
                       tick(now_utc)
                         due = Scheduler.due()
                         for slot in due:
                            mark_starting(RunState)
                            svc.run_once()  ────▶  Pipeline.run()
                            mark_completed/failed()
                            scheduler.mark_fired()
                       stop_event.wait(poll_interval)
SIGTERM       ─▶   stop_event.set()
                    (loop exits, mark_aborted if mid-pipeline)
                    PidLock.release()
```

## 5. Scheduling

Slots are tuples of (name, hour, minute, weekdays, fire_window, tz_offset).
Defaults mirror the existing GitHub-Actions cron in
[.github/workflows/aegis-daily.yml](../.github/workflows/aegis-daily.yml):

- `primary_1615_ist` — 16:15 IST Mon–Fri (post-close + settle buffer)
- `backup_1830_ist` — 18:30 IST Mon–Fri
- `backup_2100_ist` — 21:00 IST Mon–Fri

**Same-day deduplication:** each slot records its most recent fire in
`reports/ops_schedule_state.json`. A slot fires at most once per calendar day
in its own timezone.

**Fire window:** `default 5 min`. A slot is due iff `now ∈ [scheduled, scheduled + 5min]`
AND `last_fire.date != now.date` (in the slot's timezone).

## 6. Recovery model

`reports/ops_run_state.json` records the phase of the current or most-recent
run. On daemon startup:

| Previous phase | Recovery action | Emitted event |
|---|---|---|
| IDLE / COMPLETED | `NONE` | none |
| STARTING / RUNNING | `RESUME` | `WARN recovery_decision` |
| ABORTED | `RESUME` | `WARN recovery_decision` |
| FAILED | `ATTENTION` | `WARN recovery_decision` |

Recovery never re-executes a stage in place; when the daemon next hits a due
slot it fires a fresh pass through the whole pipeline. The MON001 and AEGIS
stages are all idempotent for a given `asof`, so re-firing is safe.

## 7. Log management

- **Format:** one JSON object per line (`ts`, `level`, `logger`, `msg`, `pid`, `event`, `slot`, plus caller-supplied `extra=` fields).
- **Rotation:** `RotatingFileHandler` with `max_bytes=5 MiB`, `backup_count=14`.
- **Retention:** `prune_old_logs()` deletes rotated backups older than
  `log_retention_days` (default 30). The active log file is never deleted.
- **stderr mirror:** enabled by default so systemd's `journalctl -u nexaquant`
  and Task Scheduler's task history capture the same JSON stream.

## 8. Runtime monitoring

`ProcessMonitor.snapshot()` returns a `ProcessSnapshot`:

| Field | Notes |
|---|---|
| `pid` | Daemon process id |
| `uptime_s` | Seconds since `ProcessMonitor()` was constructed |
| `memory_rss_mb`, `memory_vms_mb` | Resident / virtual memory (0 when neither psutil nor resource is available) |
| `cpu_percent` | Instantaneous CPU% (psutil), or accumulated user+sys seconds (resource) |
| `num_threads`, `open_files` | psutil only |
| `source` | `"psutil"` \| `"resource"` \| `"minimal"` |
| `read_at_utc` | ISO timestamp |

`ExecutionTimings` aggregates counters across pipeline passes:
`total_runs`, `total_stage_runs`, `total_stage_retries`, `total_stage_failures`,
`last_run_duration_s`, `last_stage_duration_s`. The daemon exposes both via
`snapshot()` (used by CLI `status`).

## 9. Signals

| Signal | Handled? | Behaviour |
|---|:-:|---|
| `SIGTERM` | ✅ | Sets stop event → loop exits cleanly. If mid-pipeline, marks `ABORTED`. |
| `SIGINT` (Ctrl-C) | ✅ | Same as SIGTERM. |
| `SIGBREAK` (Windows) | ✅ | Same as SIGTERM. |
| `SIGKILL` | ❌ (can't) | Lock stays; next daemon breaks it on the age or dead-pid heuristic. |

## 10. Exit codes

| Code | Meaning |
|---|---|
| 0 | Clean shutdown (SIGTERM or normal exit) |
| 1 | Pipeline failure (surface from OPS001-A's `NexaQuantService.run_once()`) |
| 2 | Framework error (unexpected exception in daemon code) |
| 3 | Daemon lock already held — refused to start |
| 4 | Permission denied on stop (unable to signal owner pid) |

## 11. Governance invariants

Guarded by `test_ops_daemon.py`:

| Guard | How |
|---|---|
| MON001 fingerprint unchanged | Recomputes and compares to sealed |
| HOLD=63, rebal=63 | Reads production files |
| cumulative_strategy_search = 38 | Reads trial manifest |
| No sealed file modified | `git diff HEAD --name-only` scan |
| No LAB artefact modified | Same scan, path prefix check |

## 12. Backwards compatibility

- `NexaQuantService` (OPS001-A) is invoked unchanged.
- `Pipeline`, `MetricsLedger`, `StatusWriter`, `NotificationManager` untouched.
- `ops_status.json` schema unchanged (fields ADDED, none renamed or repurposed).
- The GitHub-Actions cron workflows continue to work as before; OPS001-B is an
  alternative deployment path, not a replacement.

## 13. Future (out of scope for OPS001-B)

- **OPS001-C:** dashboards + oncall paging integration.
- **OPS002:** high-availability (multiple daemons + leader election).
- **MON002:** drift-alarm calibration + regime overlays.
